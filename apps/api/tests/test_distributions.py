import random
import threading
from uuid import UUID, uuid4

from sqlalchemy import text

from grok_bot.db import set_tenant
from grok_bot.domain.money import allocate_by_weights
from tests.test_accounting_core import _balances, _code, _flow_available, _invoice, _world


def test_cent_sequences_conserve_and_journals_balance(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    random.seed(4)
    for _ in range(20):
        amount = random.randint(0, 50_000)
        weights = [(uuid4(), 600_000), (uuid4(), 400_000)]
        shares = allocate_by_weights(amount, weights)
        assert sum(shares.values()) == amount
    for amount in (1, 2, 3):
        _flow_available(client, world, amount)
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


def test_fin_04_hundred_replays_post_one_journal(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    invoice = _invoice(client, world, 4_500, "HUNDRED")
    first = None
    for _ in range(100):
        response = client.post(
            f"/v1/invoices/{invoice['id']}/approve",
            headers=world["manager"],
            json={"posting_date": "2026-11-20"},
        )
        assert response.status_code == 200, response.text
        first = first or response.json()["payable_journal_id"]
        assert response.json()["payable_journal_id"] == first
    with migrator_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :org AND source_type = 'INVOICE_APPROVAL'"),
            {"org": world["org_id"]},
        ).scalar()
    assert count == 1


def test_fin_05_concurrent_reservations_cannot_exceed_cash(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    _flow_available(client, world, 90_000)
    _destination(client, world, world["contractor_id"])
    first = _invoice(client, world, 70_000, "RACE-A")
    second = _invoice(client, world, 50_000, "RACE-B")
    for invoice in (first, second):
        assert client.post(f"/v1/invoices/{invoice['id']}/approve", headers=world["manager"], json={"posting_date": "2026-11-20"}).status_code == 200
    drafted = []
    for invoice in (first, second):
        response = client.post(
            "/v1/distribution-batches",
            headers=world["accounting"],
            json={
                "property_id": world["property_id"],
                "as_of": "2026-11-21",
                "management_party_id": None,
                "liability_ids": [invoice["id"]],
            },
        )
        assert response.status_code == 201, response.text
        drafted.append(response.json()["id"])
    barrier = threading.Barrier(2)
    results = []

    def reserve(batch_id):
        barrier.wait()
        response = client.post(f"/v1/distribution-batches/{batch_id}/validate", headers=world["accounting"])
        results.append(response.status_code)

    threads = [threading.Thread(target=reserve, args=(batch_id,)) for batch_id in drafted]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200, 409]
    with migrator_engine.connect() as conn:
        reserved = conn.execute(
            text("SELECT coalesce(sum(reserved_cents), 0) FROM funding_lots WHERE organization_id = :org"),
            {"org": world["org_id"]},
        ).scalar()
    assert reserved in (50_000, 70_000)
    assert reserved <= 90_000


def test_fin_07_destination_change_invalidates_approval(client, migrator_engine, simulator):
    world = _ready_payment(client, migrator_engine, 10_000)
    batch = _approved(client, world)
    changed = client.post(
        "/v1/payee-destinations",
        headers=world["accounting"],
        json={"party_id": world["contractor_id"], "masked_label": "****9999"},
    )
    assert changed.status_code == 201, changed.text
    submitted = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {}},
    )
    assert submitted.status_code == 409
    assert submitted.json()["error"]["code"] == "APPROVAL_INVALID"
    with migrator_engine.connect() as conn:
        events = conn.execute(
            text("SELECT count(*) FROM payment_events WHERE organization_id = :org"),
            {"org": world["org_id"]},
        ).scalar()
    assert events == 0
    del simulator


def test_fin_08_timeout_then_same_key_settles_once(client, migrator_engine, simulator):
    world = _ready_payment(client, migrator_engine, 8_000)
    batch = _approved(client, world)
    item_id = batch["items"][0]["id"]
    provider_key = batch["items"][0]["provider_key"]
    first = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {item_id: "timeout"}},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "UNKNOWN"
    assert first.json()["bank_contacted"] is False
    second = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {item_id: "settle"}},
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "SETTLED"
    assert second.json()["items"][0]["provider_key"] == provider_key
    third = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {item_id: "settle"}},
    )
    assert third.status_code == 200, third.text
    with migrator_engine.connect() as conn:
        settlements = conn.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :org AND source_type = 'INVOICE_SETTLEMENT'"),
            {"org": world["org_id"]},
        ).scalar()
        keys = conn.execute(
            text("SELECT count(DISTINCT provider_key) FROM payment_events WHERE organization_id = :org AND kind = 'SIMULATOR_SETTLED'"),
            {"org": world["org_id"]},
        ).scalar()
    assert settlements == 1
    assert keys == 1


def test_fin_10_return_books_recovery_and_freezes(client, migrator_engine, simulator):
    world = _ready_payment(client, migrator_engine, 6_000)
    batch = _approved(client, world)
    settled = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {}},
    )
    assert settled.status_code == 200, settled.text
    returned = client.post(
        f"/v1/distribution-items/{batch['items'][0]['id']}/returns",
        headers=world["manager"],
        json={"posting_date": "2026-11-24"},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["recovery_account"] == "1040"
    assert returned.json()["disbursements_frozen"] is True
    assert returned.json()["simulator"] is True
    balances = _balances(client, world)
    assert _code(balances, "1040") == 6_000
    with migrator_engine.connect() as conn:
        frozen = conn.execute(text("SELECT disbursements_frozen FROM properties WHERE id = :id"), {"id": world["property_id"]}).scalar()
        settlement = conn.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :org AND source_type = 'INVOICE_SETTLEMENT'"),
            {"org": world["org_id"]},
        ).scalar()
    assert frozen is True
    assert settlement == 1


def test_fin_15_partial_failure_is_not_replayed(client, migrator_engine, simulator):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    _flow_available(client, world, 40_000)
    _destination(client, world, world["contractor_id"])
    invoices = [_invoice(client, world, 10_000, f"PART-{index}") for index in range(4)]
    for invoice in invoices:
        assert client.post(f"/v1/invoices/{invoice['id']}/approve", headers=world["manager"], json={"posting_date": "2026-11-20"}).status_code == 200
    drafted = client.post(
        "/v1/distribution-batches",
        headers=world["accounting"],
        json={"property_id": world["property_id"], "as_of": "2026-11-22", "management_party_id": None},
    )
    assert drafted.status_code == 201, drafted.text
    assert len(drafted.json()["items"]) == 4
    validated = client.post(f"/v1/distribution-batches/{drafted.json()['id']}/validate", headers=world["accounting"])
    assert validated.status_code == 200, validated.text
    _step(client, world)
    approved = client.post(
        f"/v1/distribution-batches/{drafted.json()['id']}/approve",
        headers=world["manager"],
        json={"snapshot_hash": validated.json()["snapshot_hash"], "reason": "Partial simulator"},
    )
    assert approved.status_code == 200, approved.text
    _enable_payment(client, world)
    failed = approved.json()["items"][3]["id"]
    first = client.post(
        f"/v1/distribution-batches/{drafted.json()['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {failed: "fail"}},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PARTIALLY_SETTLED"
    assert sorted(item["status"] for item in first.json()["items"]) == ["FAILED", "SETTLED", "SETTLED", "SETTLED"]
    second = client.post(
        f"/v1/distribution-batches/{drafted.json()['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {failed: "fail"}},
    )
    assert second.status_code == 200, second.text
    with migrator_engine.connect() as conn:
        settlements = conn.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :org AND source_type = 'INVOICE_SETTLEMENT'"),
            {"org": world["org_id"]},
        ).scalar()
    assert settlements == 3
    del simulator


def test_fin_18_second_export_keeps_identity_and_does_not_settle(client, migrator_engine, simulator, app):
    world = _ready_payment(client, migrator_engine, 5_000)
    batch = _approved(client, world)
    first = client.post(f"/v1/distribution-batches/{batch['id']}/export", headers=world["manager"])
    second = client.post(f"/v1/distribution-batches/{batch['id']}/export", headers=world["manager"])
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["batch_id"] == second.json()["batch_id"]
    assert first.json()["artifact"]["items"][0]["id"] == second.json()["artifact"]["items"][0]["id"]
    assert first.json()["duplicate_download"] is False
    assert second.json()["duplicate_download"] is True
    assert second.json()["settled"] is False
    with migrator_engine.connect() as conn:
        settlements = conn.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :org AND source_type = 'INVOICE_SETTLEMENT'"),
            {"org": world["org_id"]},
        ).scalar()
        downloads = conn.execute(
            text("SELECT count(*) FROM audit_events WHERE organization_id = :org AND action = 'distribution.exported'"),
            {"org": world["org_id"]},
        ).scalar()
    assert settlements == 0
    assert downloads == 2
    app.state.settings.payment_simulator = "unset"
    disabled = client.post(
        f"/v1/distribution-batches/{batch['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {}},
    )
    assert disabled.status_code == 409
    assert disabled.json()["error"]["code"] == "PROVIDER_SUBMISSION_DISABLED"


def test_owner_statement_is_hidden_from_another_owner(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    owner_user = uuid4()
    other_user = uuid4()
    with migrator_engine.begin() as conn:
        from tests.support import seed_member

        seed_member(conn, org_id=UUID(world["org_id"]), user_id=owner_user, subject="owner-a@example.test", password="local-owner-password", roles=["owner"])
        seed_member(conn, org_id=UUID(world["org_id"]), user_id=other_user, subject="owner-b@example.test", password="local-owner-password", roles=["owner"])
    assert client.post(
        "/v1/owner-links",
        headers=world["accounting"],
        json={"user_id": str(owner_user), "party_id": world["owner_a"]},
    ).status_code == 201
    issued = client.post(
        "/v1/statements",
        headers=world["accounting"],
        json={
            "property_id": world["property_id"],
            "owner_party_id": world["owner_a"],
            "period_start": "2026-11-01",
            "period_end": "2026-11-30",
            "reason": "November snapshot",
        },
    )
    assert issued.status_code == 201, issued.text
    from tests.support import bearer, login

    owner = bearer(login(client, "owner-a@example.test", "local-owner-password"))
    other = bearer(login(client, "owner-b@example.test", "local-owner-password"))
    seen = client.get(f"/v1/statements/{issued.json()['id']}", headers=owner)
    hidden = client.get(f"/v1/statements/{issued.json()['id']}", headers=other)
    assert seen.status_code == 200, seen.text
    assert seen.json()["snapshot_hash"] == issued.json()["snapshot_hash"]
    assert hidden.status_code == 404
    listed = client.get("/v1/statements", headers=owner)
    hidden_list = client.get("/v1/statements", headers=other)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [issued.json()["id"]]
    assert hidden_list.status_code == 200, hidden_list.text
    assert hidden_list.json()["items"] == []
    with migrator_engine.begin() as conn:
        from sqlalchemy.exc import DBAPIError

        import pytest

        with pytest.raises(DBAPIError):
            conn.execute(text("UPDATE owner_statements SET reason = 'tamper'"))


def test_actor_unset_and_stale_pool_hide_rows(app, migrator_engine):
    from uuid import UUID
    from grok_bot.api.app import create_app
    from tests.support import seed_member, settings_for

    org_id = __import__("uuid").uuid4()
    user_id = __import__("uuid").uuid4()
    with migrator_engine.begin() as conn:
        seed_member(conn, org_id=org_id, user_id=user_id, subject="pool@example.test", password="local-admin-password", roles=["property_manager"])
        conn.execute(
            text(
                """
                INSERT INTO properties (
                  id, organization_id, name, address_line1, city, region, postal_code, country_code, timezone
                ) VALUES (
                  :id, :organization_id, 'Pooled', '1 Main', 'Raleigh', 'NC', '27601', 'US', 'America/New_York'
                )
                """
            ),
            {"id": __import__("uuid").uuid4(), "organization_id": org_id},
        )
    narrow = create_app(settings_for("grok_m0_test"), pool_size=1, max_overflow=0)
    engine = narrow.state.engine
    with engine.connect() as conn:
        raw = conn.connection.driver_connection
        raw.autocommit = True
        cursor = raw.cursor()
        cursor.execute("SELECT set_config('app.organization_id', %s, false)", (str(org_id),))
        cursor.execute("SELECT set_config('app.actor_id', %s, false)", (str(user_id),))
        cursor.close()
        raw.autocommit = False
    with engine.connect() as conn:
        set_tenant(conn, org_id, None)
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0
        set_tenant(conn, org_id, UUID(int=0))
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0
        set_tenant(conn, org_id, user_id)
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 1
    engine.dispose()
    del app


def _destination(client, world, party_id):
    response = client.post(
        "/v1/payee-destinations",
        headers=world["accounting"],
        json={"party_id": party_id, "masked_label": "****1000"},
    )
    assert response.status_code == 201, response.text


def _step(client, world):
    response = client.post(
        "/v1/auth/local/step-up",
        headers=world["manager"],
        json={"subject": world["manager_subject"], "password": world["manager_password"]},
    )
    assert response.status_code == 200, response.text


def _ready_payment(client, migrator_engine, amount):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    _flow_available(client, world, amount)
    _destination(client, world, world["contractor_id"])
    invoice = _invoice(client, world, amount, f"PAY-{amount}")
    assert client.post(f"/v1/invoices/{invoice['id']}/approve", headers=world["manager"], json={"posting_date": "2026-11-20"}).status_code == 200
    return world


def _enable_payment(client, world):
    response = client.put(
        "/v1/kill-switches",
        headers=world["manager"],
        json={"messaging_enabled": False, "calendar_enabled": False, "payment_enabled": True},
    )
    assert response.status_code == 200, response.text


def _approved(client, world):
    _enable_payment(client, world)
    drafted = client.post(
        "/v1/distribution-batches",
        headers=world["accounting"],
        json={"property_id": world["property_id"], "as_of": "2026-11-22", "management_party_id": None},
    )
    assert drafted.status_code == 201, drafted.text
    validated = client.post(f"/v1/distribution-batches/{drafted.json()['id']}/validate", headers=world["accounting"])
    assert validated.status_code == 200, validated.text
    _step(client, world)
    approved = client.post(
        f"/v1/distribution-batches/{drafted.json()['id']}/approve",
        headers=world["manager"],
        json={"snapshot_hash": validated.json()["snapshot_hash"], "reason": "Reviewed snapshot"},
    )
    assert approved.status_code == 200, approved.text
    return approved.json()
