from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from grok_bot.crypto import decrypt_text
from grok_bot.db import set_tenant
from grok_bot.domain.contacts import read_contact_value, store_contact, store_inbox_event
from tests.support import CONTACT_KEY_RAW, seed_member


def test_contact_ciphertext_is_not_plaintext_and_round_trips(app, migrator_engine):
    org_id = uuid4()
    party_id = uuid4()
    with migrator_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO organizations (id, organization_id, name) VALUES (:id, :id, 'Contacts')"),
            {"id": org_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO parties (id, organization_id, display_name, kind)
                VALUES (:id, :organization_id, 'Tenant', 'person')
                """
            ),
            {"id": party_id, "organization_id": org_id},
        )
    user_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(conn, org_id=org_id, user_id=user_id, subject="contact@example.test", password="local-admin-password", roles=["accounting_staff"])
    session = Session(app.state.engine)
    with session.begin():
        set_tenant(session, org_id, user_id)
        contact_id = store_contact(
            session,
            organization_id=org_id,
            party_id=party_id,
            kind="email",
            value="tenant@example.test",
            key=CONTACT_KEY_RAW,
        )
    with app.state.engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.organization_id', :org, true), set_config('app.actor_id', :actor, true)"),
            {"org": str(org_id), "actor": str(user_id)},
        )
        stored = conn.execute(text("SELECT encode(ciphertext, 'escape') FROM contacts")).scalar()
        assert "tenant@example.test" not in stored
        value = read_contact_value(conn, organization_id=org_id, contact_id=contact_id, key=CONTACT_KEY_RAW)
    assert value == "tenant@example.test"


def test_inbox_payload_is_encrypted_and_provider_event_is_unique(app, migrator_engine):
    org_id = uuid4()
    with migrator_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO organizations (id, organization_id, name) VALUES (:id, :id, 'Inbox')"),
            {"id": org_id},
        )
    raw = b'{"email":"tenant@example.test","event":"inquiry"}'
    user_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(conn, org_id=org_id, user_id=user_id, subject="inbox@example.test", password="local-admin-password", roles=["accounting_staff"])
    session = Session(app.state.engine)
    with session.begin():
        set_tenant(session, org_id, user_id)
        store_inbox_event(
            session,
            organization_id=org_id,
            provider="test-provider",
            provider_event_id="evt-1",
            payload=raw,
            key=CONTACT_KEY_RAW,
        )
    with app.state.engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.organization_id', :org, true), set_config('app.actor_id', :actor, true)"),
            {"org": str(org_id), "actor": str(user_id)},
        )
        row = conn.execute(
            text("SELECT payload_ciphertext, payload_nonce FROM inbox_events")
        ).one()
        assert b"tenant@example.test" not in bytes(row.payload_ciphertext)
        assert decrypt_text(bytes(row.payload_ciphertext), bytes(row.payload_nonce), CONTACT_KEY_RAW) == raw.decode()
    with pytest.raises(IntegrityError):
        with Session(app.state.engine) as session:
            with session.begin():
                set_tenant(session, org_id, user_id)
                store_inbox_event(
                    session,
                    organization_id=org_id,
                    provider="test-provider",
                    provider_event_id="evt-1",
                    payload=b"{}",
                    key=CONTACT_KEY_RAW,
                )
