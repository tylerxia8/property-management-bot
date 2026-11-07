from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from grok_bot.auth.permissions import Principal
import json

from grok_bot.db import set_tenant
from grok_bot.domain.portfolio import create_property
from grok_bot.redaction import SENSITIVE_KEYS, redact
from tests.support import PROPERTY, bearer, login, seed_member


def test_trigger_redacts_sensitive_keys_and_audit_is_append_only(client, app, migrator_engine):
    org_id = uuid4()
    user_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=user_id,
            subject="audit@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
        )
    payload = {key: "raw-value" for key in SENSITIVE_KEYS}
    payload["name"] = "kept"
    payload["nested"] = {"phone": "555", "city": "Raleigh"}
    assert redact({"email": "a@b.test", "name": "kept"}) == {"email": "[REDACTED]", "name": "kept"}
    session = Session(app.state.engine)
    with session.begin():
        set_tenant(session, org_id, user_id)
        session.execute(
            text(
                """
                INSERT INTO audit_events (
                  id, organization_id, actor_type, action, target_type, request_id, after_state
                ) VALUES (
                  :id, :organization_id, 'system', 'fixture.redaction', 'fixture', 'req_redact',
                  CAST(:after_state AS jsonb)
                )
                """
            ),
            {"id": uuid4(), "organization_id": org_id, "after_state": json.dumps(payload)},
        )
    with app.state.engine.begin() as conn:
        set_local = conn.execute(
            text("SELECT set_config('app.organization_id', :org, true), set_config('app.actor_id', :actor, true)"),
            {"org": str(org_id), "actor": str(user_id)},
        )
        assert set_local is not None
        stored = conn.execute(text("SELECT after_state FROM audit_events")).scalar()
    assert stored["name"] == "kept"
    assert stored["nested"]["city"] == "Raleigh"
    assert stored["nested"]["phone"] == "[REDACTED]"
    for key in SENSITIVE_KEYS:
        assert stored[key] == "[REDACTED]"
    assert "raw-value" not in str(stored)
    with pytest.raises(DBAPIError, match="append-only"):
        with migrator_engine.begin() as conn:
            conn.execute(text("UPDATE audit_events SET action = 'tamper'"))
    with pytest.raises(DBAPIError, match="append-only"):
        with migrator_engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_events"))
    with pytest.raises(DBAPIError):
        with app.state.engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.organization_id', :org, true), set_config('app.actor_id', :actor, true)"),
                {"org": str(org_id), "actor": str(user_id)},
            )
            conn.execute(text("UPDATE audit_events SET reason = 'no'"))


def test_outbox_rolls_back_with_property(app, migrator_engine):
    org_id = uuid4()
    user_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=user_id,
            subject="rollback@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
        )
    principal = Principal(user_id, org_id, "rollback", ("organization_administrator",), "local_dev")
    session = Session(app.state.engine)
    with pytest.raises(RuntimeError):
        with session.begin():
            set_tenant(session, org_id, user_id)
            create_property(session, principal, SimpleNamespace(**PROPERTY), "req_rollback")
            raise RuntimeError("boom")
    with migrator_engine.begin() as conn:
        assert conn.execute(
            text("SELECT count(*) FROM properties WHERE organization_id = :org"),
            {"org": org_id},
        ).scalar() == 0
        assert conn.execute(
            text("SELECT count(*) FROM outbox_events WHERE organization_id = :org"),
            {"org": org_id},
        ).scalar() == 0
        assert conn.execute(
            text("SELECT count(*) FROM audit_events WHERE organization_id = :org"),
            {"org": org_id},
        ).scalar() == 0


def test_api_commit_writes_one_audit_and_pending_outbox(client, migrator_engine):
    org_id = uuid4()
    user_id = uuid4()
    subject = "writer@example.test"
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=user_id,
            subject=subject,
            password="local-admin-password",
            roles=["organization_administrator"],
        )
    token = login(client, subject, "local-admin-password")
    created = client.post(
        "/v1/properties",
        headers={**bearer(token), "Idempotency-Key": "property-once"},
        json=PROPERTY,
    )
    assert created.status_code == 201, created.text
    replay = client.post(
        "/v1/properties",
        headers={**bearer(token), "Idempotency-Key": "property-once"},
        json=PROPERTY,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    assert replay.headers["Idempotency-Status"] == "replayed"
    with migrator_engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM audit_events")).scalar() == 1
        status = conn.execute(text("SELECT status FROM outbox_events")).scalar()
        assert status == "PENDING"
        assert conn.execute(text("SELECT count(*) FROM outbox_events")).scalar() == 1
