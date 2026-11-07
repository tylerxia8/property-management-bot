import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.db import set_tenant
from grok_bot.domain.alerts import dispatch_alerts
from tests.support import bearer, login, seed_member
from tests.test_accounting_core import _flow_available, _invoice, _receipt, _world
from tests.test_distributions import _approved, _destination, _enable_payment


def test_scoped_grant_does_not_open_another_property_or_the_bank(client, migrator_engine, app):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    other = client.post(
        "/v1/properties",
        headers={**world["admin"], "Idempotency-Key": f"other-{uuid4()}"},
        json={
            "name": "Other House",
            "address_line1": "2 Side",
            "address_line2": None,
            "city": "Raleigh",
            "region": "NC",
            "postal_code": "27601",
            "country_code": "US",
            "timezone": "America/New_York",
        },
    )
    assert other.status_code == 201, other.text
    user_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=UUID(world["org_id"]),
            user_id=user_id,
            subject="scoped-only@example.test",
            password="local-manager-password",
            roles=["property_manager"],
            resource_type="property",
            resource_id=UUID(world["property_id"]),
        )
    token = bearer(login(client, "scoped-only@example.test", "local-manager-password"))
    me = client.get("/v1/me", headers=token)
    assert me.status_code == 200, me.text
    assert me.json()["roles"] == []
    assert "properties.update" not in me.json()["capabilities"]
    assert me.json()["grants"][0]["resource_id"] == world["property_id"]
    listing = client.get("/v1/properties", headers=token)
    assert listing.status_code == 200, listing.text
    assert [item["id"] for item in listing.json()["items"]] == [world["property_id"]]
    assert client.get(f"/v1/properties/{other.json()['id']}", headers=token).status_code == 403
    assert client.get("/v1/bank-transactions", headers=token).status_code == 403
    with app.state.engine.connect() as conn:
        set_tenant(conn, UUID(world["org_id"]), user_id)
        visible = conn.execute(text("SELECT id FROM properties")).scalars().all()
        banks = conn.execute(text("SELECT count(*) FROM bank_accounts")).scalar()
    assert [str(item) for item in visible] == [world["property_id"]]
    assert banks == 0


def test_reversal_credit_note_and_receipt_return_keep_the_original(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    receipt = _flow_available(client, world, 4_000)
    returned = client.post(
        f"/v1/receipts/{receipt['id']}/returns",
        headers={**world["accounting"], "Idempotency-Key": "return-once"},
        json={"amount_cents": 1_000, "posting_date": "2026-11-12", "reason": "Check short"},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["returned_cents"] == 1_000
    replay = client.post(
        f"/v1/receipts/{receipt['id']}/returns",
        headers={**world["accounting"], "Idempotency-Key": "return-once"},
        json={"amount_cents": 1_000, "posting_date": "2026-11-12", "reason": "Check short"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["return_journal_id"] == returned.json()["return_journal_id"]
    journal_id = returned.json()["return_journal_id"]
    reversed_journal = client.post(
        f"/v1/journals/{journal_id}/reversals",
        headers={**world["accounting"], "Idempotency-Key": "reverse-once"},
        json={"amount_cents": 1, "posting_date": "2026-11-13", "reason": "Correct the return"},
    )
    assert reversed_journal.status_code == 200, reversed_journal.text
    again = client.post(
        f"/v1/journals/{journal_id}/reversals",
        headers={**world["accounting"], "Idempotency-Key": "reverse-twice"},
        json={"amount_cents": 1, "posting_date": "2026-11-13", "reason": "Correct the return"},
    )
    assert again.json()["id"] == reversed_journal.json()["id"]
    with migrator_engine.connect() as conn:
        originals = conn.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :org AND id = :id"),
            {"org": world["org_id"], "id": journal_id},
        ).scalar()
    assert originals == 1
    invoice = _invoice(client, world, 5_000, "CREDIT-1")
    approved = client.post(f"/v1/invoices/{invoice['id']}/approve", headers=world["manager"], json={"posting_date": "2026-11-20"})
    assert approved.status_code == 200, approved.text
    current = client.get(f"/v1/invoices/{invoice['id']}", headers=world["accounting"])
    assert current.status_code == 200, current.text
    noted = client.post(
        f"/v1/invoices/{invoice['id']}/credit-notes",
        headers={**world["accounting"], "Idempotency-Key": "credit-once", "If-Match": "2"},
        json={"amount_cents": 1_500, "posting_date": "2026-11-21", "reason": "Vendor adjustment"},
    )
    assert noted.status_code == 200, noted.text
    assert noted.json()["credited_cents"] == 1_500
    assert noted.json()["original_payable_journal_id"] == approved.json()["payable_journal_id"]
    assert noted.json()["payable_journal_id"] == approved.json()["payable_journal_id"]
    ledger = client.get(f"/v1/properties/{world['property_id']}/ledger", headers=world["accounting"])
    assert ledger.status_code == 200, ledger.text
    assert ledger.json()["currency"] == "USD"
    assert any(item["source_type"] == "CREDIT_NOTE" for item in ledger.json()["items"])


def test_manual_evidence_is_not_a_simulator_event(client, migrator_engine, simulator):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    _flow_available(client, world, 3_000)
    _destination(client, world, world["contractor_id"])
    invoice = _invoice(client, world, 3_000, "EVIDENCE")
    assert client.post(f"/v1/invoices/{invoice['id']}/approve", headers=world["manager"], json={"posting_date": "2026-11-20"}).status_code == 200
    blocked = client.post(
        "/v1/distribution-batches/00000000-0000-4000-8000-000000000001/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {}},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "KILL_SWITCH"
    batch = _approved(client, world)
    assert client.put(
        "/v1/kill-switches",
        headers=world["manager"],
        json={"messaging_enabled": False, "calendar_enabled": False, "payment_enabled": False},
    ).status_code == 200
    submitted = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {}},
    )
    assert submitted.status_code == 409
    assert submitted.json()["error"]["code"] == "KILL_SWITCH"
    _enable_payment(client, world)
    item = batch["items"][0]
    item_id = item["id"]
    denied = client.post(
        f"/v1/payment-items/{item_id}/submission-evidence",
        headers={**world["accounting"], "Idempotency-Key": "evidence-staff"},
        json={"reference": "bank-ref-1"},
    )
    assert denied.status_code == 403
    missing = client.post(
        f"/v1/payment-items/{item_id}/submission-evidence",
        headers=world["manager"],
        json={"reference": "bank-ref-1"},
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    evidence = client.post(
        f"/v1/payment-items/{item_id}/submission-evidence",
        headers={**world["manager"], "Idempotency-Key": "evidence-submit"},
        json={"reference": "bank-ref-1"},
    )
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["simulator"] is False
    assert evidence.json()["settled"] is False
    assert evidence.json()["bank_contacted"] is False
    assert evidence.json()["amount_cents"] == item["amount_cents"]
    assert evidence.json()["currency"] == "USD"
    replayed = client.post(
        f"/v1/payment-items/{item_id}/submission-evidence",
        headers={**world["manager"], "Idempotency-Key": "evidence-submit"},
        json={"reference": "bank-ref-1"},
    )
    assert replayed.status_code == 200, replayed.text
    duplicate = client.post(
        f"/v1/payment-items/{item_id}/submission-evidence",
        headers={**world["manager"], "Idempotency-Key": "evidence-submit-again"},
        json={"reference": "bank-ref-2"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_EVIDENCE"
    settled = client.post(
        f"/v1/payment-items/{item_id}/settlement-evidence",
        headers={**world["manager"], "Idempotency-Key": "evidence-settle"},
        json={"reference": "bank-ref-1-settled", "posting_date": "2026-11-23"},
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["simulator"] is False
    assert settled.json()["bank_contacted"] is False
    assert settled.json()["amount_cents"] == item["amount_cents"]
    again = client.post(
        f"/v1/payment-items/{item_id}/settlement-evidence",
        headers={**world["manager"], "Idempotency-Key": "evidence-settle"},
        json={"reference": "bank-ref-1-settled", "posting_date": "2026-11-23"},
    )
    assert again.status_code == 200, again.text
    second = client.post(
        f"/v1/payment-items/{item_id}/settlement-evidence",
        headers={**world["manager"], "Idempotency-Key": "evidence-settle-again"},
        json={"reference": "bank-ref-1-settled", "posting_date": "2026-11-23"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "EVIDENCE_STATE"
    with migrator_engine.connect() as conn:
        kinds = conn.execute(
            text("SELECT kind, simulator FROM payment_events WHERE organization_id = :org ORDER BY kind"),
            {"org": world["org_id"]},
        ).all()
        journals = conn.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :org AND source_type = 'INVOICE_SETTLEMENT'"),
            {"org": world["org_id"]},
        ).scalar()
        audits = conn.execute(
            text(
                """
                SELECT action FROM audit_events
                WHERE organization_id = :org AND action IN ('distribution.submission_evidence', 'distribution.settlement_evidence')
                """
            ),
            {"org": world["org_id"]},
        ).scalars().all()
    assert ("MANUAL_SETTLEMENT", False) in [(row.kind, row.simulator) for row in kinds]
    assert ("MANUAL_SUBMISSION", False) in [(row.kind, row.simulator) for row in kinds]
    assert journals == 1
    assert set(audits) == {"distribution.submission_evidence", "distribution.settlement_evidence"}


def test_bank_match_does_not_post_and_cannot_exceed(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    receipt = _receipt(client, world, 2_000)
    deposited = client.post(
        "/v1/deposit-batches",
        headers={**world["accounting"], "Idempotency-Key": "dep-match"},
        json={
            "property_id": world["property_id"],
            "bank_account_id": world["bank_id"],
            "slip_reference": "slip-match",
            "deposited_on": "2026-11-07",
            "items": [{"receipt_id": receipt["id"], "amount_cents": 2_000}],
        },
    )
    assert deposited.status_code == 201, deposited.text
    imported = client.post(
        "/v1/bank-imports",
        headers={**world["accounting"], "Idempotency-Key": "imp-match"},
        json={"transactions": [{"bank_account_id": world["bank_id"], "external_id": "txn-match", "amount_cents": 2_000, "posted_on": "2026-11-07"}]},
    )
    assert imported.status_code == 201, imported.text
    listed = client.get("/v1/bank-transactions", headers=world["accounting"])
    assert listed.status_code == 200, listed.text
    transaction_id = listed.json()["items"][0]["id"]
    matched = client.post(
        "/v1/bank-matches",
        headers={**world["accounting"], "Idempotency-Key": "match-once"},
        json={"bank_transaction_id": transaction_id, "deposit_batch_id": deposited.json()["id"], "amount_cents": 2_000},
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["posted_journal"] is False
    over = client.post(
        "/v1/bank-matches",
        headers={**world["accounting"], "Idempotency-Key": "match-over"},
        json={"bank_transaction_id": transaction_id, "deposit_batch_id": deposited.json()["id"], "amount_cents": 1},
    )
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "BANK_MISMATCH"


def test_alerts_retry_without_delivery_and_calendar_switch(client, migrator_engine, app):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    assert client.put(
        "/v1/kill-switches",
        headers=world["manager"],
        json={"messaging_enabled": True, "calendar_enabled": False, "payment_enabled": False},
    ).status_code == 200
    created = client.post("/v1/alerts", headers=world["manager"], json={"kind": "webhook_lag", "fail": True})
    assert created.status_code == 200, created.text
    assert created.json()["delivered"] is False
    assert created.json()["delivered_at"] is None
    now = datetime.now(timezone.utc)
    with Session(app.state.engine) as session:
        set_tenant(session, UUID(world["org_id"]), world["manager_id"])
        cursor = now + timedelta(hours=1)
        for _ in range(4):
            dispatch_alerts(session, UUID(world["org_id"]), cursor, fail=True)
            session.commit()
            set_tenant(session, UUID(world["org_id"]), world["manager_id"])
            cursor += timedelta(seconds=2)
        rows = session.execute(
            text("SELECT status, delivered_at, attempt_count, available_at FROM alert_events WHERE organization_id = :org"),
            {"org": world["org_id"]},
        ).all()
    assert rows, rows
    assert all(row.delivered_at is None for row in rows)
    assert any(row.status == "FAILED" for row in rows), rows


def test_local_read_load(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    durations = []
    errors = []

    def hit():
        started = time.perf_counter()
        response = client.get("/v1/properties", headers=world["admin"])
        durations.append(time.perf_counter() - started)
        if response.status_code != 200:
            errors.append(response.status_code)

    threads = [threading.Thread(target=hit) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [], errors
    durations.sort()
    p95 = durations[max(0, int(len(durations) * 0.95) - 1)]
    assert p95 < 2
    assert len(durations) == 20
