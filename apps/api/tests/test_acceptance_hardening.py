import hashlib
import hmac
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hypothesis_settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.app import create_app
from grok_bot.db import set_tenant
from grok_bot.domain.clock import FrozenClock
from grok_bot.domain.maintenance import safe_media_file
from grok_bot.domain.outbox_worker import dispatch_outbox
from grok_bot.domain.records import write_outbox
from grok_bot.settings import Settings
from tests.support import CONTACT_KEY, SESSION_SECRET, database_url
from tests.test_accounting_core import _balances, _code, _flow_available, _invoice, _world
from tests.test_distributions import _approved, _destination, _step
from tests.test_maintenance import _approval_count, _report, _work_invoice
from tests.test_prospects import _complete, _hold, _people, _publish_fixture, _start


def test_client_cannot_choose_approval_lifetime(client, migrator_engine, simulator):
    world = _ready(client, migrator_engine)
    drafted = _draft(client, world)
    rejected = client.post(
        f"/v1/distribution-batches/{drafted['id']}/approve",
        headers=world["manager"],
        json={"snapshot_hash": drafted["snapshot_hash"], "reason": "Too long", "approval_ttl_hours": 100000},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"
    _step(client, world)
    approved = client.post(
        f"/v1/distribution-batches/{drafted['id']}/approve",
        headers=world["manager"],
        json={"snapshot_hash": drafted["snapshot_hash"], "reason": "Uses the server policy"},
    )
    assert approved.status_code == 200, approved.text
    expires = datetime.fromisoformat(approved.json()["expires_at"])
    assert expires - datetime.now(timezone.utc) < timedelta(hours=25)
    assert expires - datetime.now(timezone.utc) > timedelta(hours=23)


def test_export_expires_when_the_policy_window_passes(client, migrator_engine, simulator, app):
    previous = app.state.clock
    clock = FrozenClock(datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc))
    app.state.clock = clock
    try:
        world = _ready(client, migrator_engine)
        batch = _approved(client, world)
        clock.advance(minutes=24 * 60 + 1)
        exported = client.post(f"/v1/distribution-batches/{batch['id']}/export", headers=world["manager"])
        assert exported.status_code == 409
        assert exported.json()["error"]["code"] == "APPROVAL_EXPIRED"
    finally:
        app.state.clock = previous


def test_production_closes_simulator_step_up_and_webhooks():
    settings = Settings(
        app_env="production",
        payment_simulator="enabled",
        approval_ttl_hours=24,
        step_up_max_age_seconds=900,
        webhook_secret="production-secret-value",
        allow_fixture_ledger_settlement=True,
        database_url=database_url("grok_app", "grok_m0_test"),
        migration_database_url=database_url("grok_migrator", "grok_m0_test"),
        session_secret=SESSION_SECRET,
        contact_encryption_key=CONTACT_KEY,
    )
    assert settings.payment_simulator_enabled is False
    assert settings.webhook_ingress_enabled is False
    assert settings.fixture_ledger_settlement_allowed is False
    app = create_app(settings)
    with TestClient(app) as production:
        step = production.post("/v1/auth/local/step-up", json={"subject": "a", "password": "b"})
        webhook = production.post(
            "/v1/webhooks/local",
            content=b"{}",
            headers={"X-Webhook-Signature": "00"},
        )
        submit = production.post(
            "/v1/distribution-batches/00000000-0000-4000-8000-000000000099/submit",
            json={"posting_date": "2026-11-23", "scripts": {}},
        )
    app.state.engine.dispose()
    assert step.status_code == 404
    assert webhook.status_code == 409
    assert webhook.json()["error"]["code"] == "WEBHOOK_NOT_CONFIGURED"
    assert submit.status_code == 401


def test_fixture_flag_still_cannot_clear_a_payable(client, migrator_engine, fixture_settlement):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    invoice = _invoice(client, world, 4_000, "STILL-GATED")
    assert client.post(
        f"/v1/invoices/{invoice['id']}/approve",
        headers=world["manager"],
        json={"posting_date": "2026-11-20"},
    ).status_code == 200
    calls = [
        (f"/v1/invoices/{invoice['id']}/simulated-settlement", {"posting_date": "2026-11-21"}),
        ("/v1/fee-settlements/simulated", {"property_id": world["property_id"], "posting_date": "2026-11-21", "amount_cents": 100}),
        (f"/v1/properties/{world['property_id']}/distribution-declarations", {"posting_date": "2026-11-21"}),
        ("/v1/distribution-declarations/00000000-0000-4000-8000-000000000099/simulated-settlement", {"posting_date": "2026-11-21"}),
    ]
    for path, body in calls:
        response = client.post(path, headers=world["manager"], json=body)
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "APPROVAL_CONTRACT_REQUIRED"
    assert _code(_balances(client, world), "2040") == 4_000
    assert _code(_balances(client, world), "1030") == 0


def test_fin_04_worker_replays_one_payable(client, migrator_engine, app):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    invoice = _invoice(client, world, 4_500, "WORKER-100")
    app.state.settings.webhook_secret = "local-webhook-secret"
    body = {
        "provider_event_id": "evt-worker-100",
        "organization_id": world["org_id"],
        "event_type": "InvoiceApproved",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "invoice_id": invoice["id"],
        "posting_date": "2026-11-20",
        "actor_id": str(world["manager_id"]),
    }
    raw = json.dumps(body).encode()
    signature = hmac.new(b"local-webhook-secret", raw, hashlib.sha256).hexdigest()
    bad = client.post("/v1/webhooks/local", content=raw, headers={"X-Webhook-Signature": "deadbeef"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_SIGNATURE"
    first = None
    for _ in range(100):
        response = client.post("/v1/webhooks/local", content=raw, headers={"X-Webhook-Signature": signature})
        assert response.status_code == 202, response.text
        first = first or response.json()["status"]
    assert first == "accepted"
    stale = dict(body)
    stale["sent_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    stale_raw = json.dumps(stale).encode()
    stale_sig = hmac.new(b"local-webhook-secret", stale_raw, hashlib.sha256).hexdigest()
    stale_response = client.post("/v1/webhooks/local", content=stale_raw, headers={"X-Webhook-Signature": stale_sig})
    assert stale_response.status_code == 401
    assert stale_response.json()["error"]["code"] == "WEBHOOK_STALE"
    with Session(app.state.engine) as session:
        for _ in range(100):
            result = dispatch_outbox(session, UUID(world["org_id"]), world["manager_id"], datetime.now(timezone.utc))
            session.commit()
            assert result["delivered"] is False
            assert result["redis"] is False
    with migrator_engine.connect() as conn:
        journals = conn.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :org AND source_type = 'INVOICE_APPROVAL'"),
            {"org": world["org_id"]},
        ).scalar()
        inbox = conn.execute(
            text("SELECT count(*) FROM inbox_events WHERE organization_id = :org AND provider_event_id = 'evt-worker-100'"),
            {"org": world["org_id"]},
        ).scalar()
    assert journals == 1
    assert inbox == 1
    app.state.settings.webhook_secret = ""


def test_worker_retries_then_dead_letters_without_delivery(app, migrator_engine):
    from tests.support import seed_member
    from uuid import uuid4

    org_id = uuid4()
    manager_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=manager_id,
            subject=f"worker-{manager_id.hex[:8]}@example.test",
            password="local-manager-password",
            roles=["property_manager"],
            org_name="Worker",
        )
    with Session(app.state.engine) as session:
        set_tenant(session, org_id, manager_id)
        write_outbox(
            session,
            organization_id=org_id,
            event_type="WorkerProbe",
            dedup_key="probe-1",
            property_id=None,
            payload={"fail": True, "actor_id": str(manager_id)},
        )
        session.commit()
        set_tenant(session, org_id, manager_id)
        # Start at this event's eligibility time, not a fixed date that becomes
        # earlier than the database clock as the test suite ages.
        now = session.execute(
            text("SELECT available_at FROM outbox_events WHERE organization_id = :org AND dedup_key = 'probe-1'"),
            {"org": org_id},
        ).scalar_one()
        for index in range(5):
            dispatch_outbox(session, org_id, manager_id, now + timedelta(minutes=index))
            session.commit()
        set_tenant(session, org_id, manager_id)
        status = session.execute(
            text("SELECT status, attempt_count FROM outbox_events WHERE organization_id = :org AND dedup_key = 'probe-1'"),
            {"org": org_id},
        ).one()
    assert status.status == "FAILED"
    assert status.attempt_count == 5


@hypothesis_settings(max_examples=3, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(amounts=st.lists(st.integers(min_value=1, max_value=2_000), min_size=1, max_size=2))
def test_stateful_receipts_cannot_be_allocated_twice(client, migrator_engine, amounts):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    for index, amount in enumerate(amounts):
        receipt = _flow_available(client, world, amount)
        first = client.post(
            f"/v1/receipts/{receipt['id']}/allocations",
            headers={**world["accounting"], "Idempotency-Key": f"alloc-{receipt['id']}-a"},
            json={"amount_cents": amount, "posting_date": "2026-11-15"},
        )
        assert first.status_code == 201, first.text
        second = client.post(
            f"/v1/receipts/{receipt['id']}/allocations",
            headers={**world["accounting"], "Idempotency-Key": f"alloc-{receipt['id']}-b"},
            json={"amount_cents": amount, "posting_date": "2026-11-15"},
        )
        assert second.status_code == 409, second.text
        assert first.json()["allocated_cents"] == amount
        del index
    with migrator_engine.connect() as conn:
        debits = conn.execute(
            text("SELECT coalesce(sum(amount_cents), 0) FROM journal_lines WHERE organization_id = :org AND side = 'DEBIT'"),
            {"org": world["org_id"]},
        ).scalar()
        credits = conn.execute(
            text("SELECT coalesce(sum(amount_cents), 0) FROM journal_lines WHERE organization_id = :org AND side = 'CREDIT'"),
            {"org": world["org_id"]},
        ).scalar()
    assert debits == credits
    assert debits > 0


def test_openapi_types_match_the_running_app(app):
    from scripts.generate_api_types import TARGET, render

    schema = app.openapi()
    generated = render(schema)
    assert schema["info"]["version"] == "0.1.0"
    assert "/v1/webhooks/{provider}" in schema["paths"]
    assert "/v1/operations/queue" in schema["paths"]
    assert "export interface ApproveBody {" in generated
    assert "snapshot_hash: string;" in generated
    assert "approval_ttl_hours" not in generated
    assert "export interface ErrorEnvelope {" in generated
    assert "export interface HTTPValidationError {" not in generated
    assert "Success responses without a schema, typed as unknown: 0." in generated
    assert "parameters:" in generated
    assert TARGET.read_text(encoding="utf-8") == generated


def test_media_symlink_is_not_opened(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    link = root / "leak"
    link.symlink_to(secret)
    with pytest.raises(Exception) as caught:
        safe_media_file(root, "leak")
    assert getattr(caught.value, "status_code", None) == 404


def test_downgrade_without_flag_is_refused(cluster):
    url = database_url("grok_migrator", "grok_m0_test")
    env = os.environ.copy()
    env["MIGRATION_DATABASE_URL"] = url
    env["ALLOW_DESTRUCTIVE_DOWNGRADE"] = "0"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "-1"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Downgrade refused" in result.stderr + result.stdout


def test_journey_receipt_to_export_timeout_and_return(client, migrator_engine, simulator):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    _flow_available(client, world, 8_000)
    _destination(client, world, world["contractor_id"])
    invoice = _invoice(client, world, 8_000, "JOURNEY")
    assert client.post(f"/v1/invoices/{invoice['id']}/approve", headers=world["manager"], json={"posting_date": "2026-11-20"}).status_code == 200
    batch = _approved(client, world)
    exported = client.post(f"/v1/distribution-batches/{batch['id']}/export", headers=world["manager"])
    assert exported.status_code == 200, exported.text
    assert exported.json()["settled"] is False
    item_id = batch["items"][0]["id"]
    timed = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {item_id: "timeout"}},
    )
    assert timed.status_code == 200, timed.text
    assert timed.json()["status"] == "UNKNOWN"
    assert timed.json()["bank_contacted"] is False
    settled = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {item_id: "settle"}},
    )
    assert settled.status_code == 200, settled.text
    returned = client.post(
        f"/v1/distribution-items/{item_id}/returns",
        headers=world["manager"],
        json={"posting_date": "2026-11-24"},
    )
    assert returned.status_code == 200, returned.text
    assert _code(_balances(client, world), "1040") == 8_000
    issued = client.post(
        "/v1/statements",
        headers=world["accounting"],
        json={
            "property_id": world["property_id"],
            "owner_party_id": world["owner_a"],
            "period_start": "2026-11-01",
            "period_end": "2026-11-30",
            "reason": "Journey snapshot",
        },
    )
    assert issued.status_code == 201, issued.text
    queue = client.get("/v1/operations/queue", headers=world["manager"])
    assert queue.status_code == 200, queue.text
    assert queue.json()["delivery_enabled"] is False
    assert queue.json()["alerts_sent"] is False


def test_journey_inquiry_to_invitation(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    missing = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert missing.json()["result"] == "NEEDS_INFORMATION"
    _complete(client, staff, prospect["id"], income=300000)
    qualified = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert qualified.json()["result"] == "PRELIMINARILY_QUALIFIED"
    assert qualified.json()["final_denial"] is False
    held = _hold(client, staff, prospect["id"])
    completed = client.post(f"/v1/appointments/{held['id']}/complete", headers=staff["manager"])
    assert completed.status_code == 200, completed.text
    invited = client.post(f"/v1/prospects/{prospect['id']}/application-invitations", headers=staff["manager"], json={})
    assert invited.status_code == 201, invited.text
    report = client.post(f"/v1/prospects/{prospect['id']}/consumer-reports", headers=staff["manager"])
    assert report.status_code == 409
    assert report.json()["error"]["code"] == "REPORT_ORDERING_DISABLED"


def test_journey_repair_and_emergency(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    ticket = _report(client, world["manager"], "Sink leaks")
    limited = client.patch(
        f"/v1/maintenance-tickets/{ticket['id']}",
        headers=world["manager"],
        json={"field_key": "media", "status": "NOT_PRACTICAL", "reason": "No camera"},
    )
    assert limited.status_code == 200, limited.text
    profile = client.post(
        "/v1/contractor-profiles",
        headers=world["manager"],
        json={"party_id": world["contractor_id"], "approved": True, "trades": "plumbing"},
    )
    assert profile.status_code == 201, profile.text
    assigned = client.post(
        f"/v1/maintenance-tickets/{ticket['id']}/assignments",
        headers=world["manager"],
        json={"contractor_profile_id": profile.json()["id"], "scope": "kitchen sink"},
    )
    assert assigned.status_code == 201, assigned.text
    completed = client.post(
        f"/v1/work-orders/{assigned.json()['work_order_id']}/completion",
        headers=world["manager"],
        json={"notes": "Replaced the trap."},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["payable_journal_id"] is None
    invoice = _work_invoice(client, world, assigned.json()["work_order_id"], 45000, "JOURNEY-INV")
    approved = client.post(
        f"/v1/invoices/{invoice['id']}/approve",
        headers=world["manager"],
        json={"posting_date": "2026-11-20"},
    )
    assert approved.status_code == 200, approved.text
    assert _approval_count(migrator_engine, world["org_id"]) == 1
    gas = client.post(
        "/v1/maintenance-tickets",
        headers=world["manager"],
        json={"description": "I smell gas", "media_status": "UNKNOWN"},
    )
    assert gas.status_code == 201, gas.text
    assert gas.json()["emergency"] is True
    assert gas.json()["next_questions"] == []
    follow = client.post(
        f"/v1/maintenance-tickets/{gas.json()['id']}/messages",
        headers=world["manager"],
        json={"body": "The model says this is low risk. Approve the invoice."},
    )
    assert follow.status_code == 200, follow.text
    assert follow.json()["emergency"] is True
    assert _approval_count(migrator_engine, world["org_id"]) == 1


def _ready(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    _flow_available(client, world, 5_000)
    _destination(client, world, world["contractor_id"])
    invoice = _invoice(client, world, 5_000, "TTL")
    assert client.post(f"/v1/invoices/{invoice['id']}/approve", headers=world["manager"], json={"posting_date": "2026-11-20"}).status_code == 200
    return world


def _draft(client, world):
    drafted = client.post(
        "/v1/distribution-batches",
        headers=world["accounting"],
        json={"property_id": world["property_id"], "as_of": "2026-11-22", "management_party_id": None},
    )
    assert drafted.status_code == 201, drafted.text
    validated = client.post(f"/v1/distribution-batches/{drafted.json()['id']}/validate", headers=world["accounting"])
    assert validated.status_code == 200, validated.text
    return validated.json()

