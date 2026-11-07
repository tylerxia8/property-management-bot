from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from grok_bot.domain.money import allocate_by_weights, round_half_up_ratio
from tests.support import PROPERTY, bearer, login, seed_member


def test_cent_allocation_and_half_up_rounding():
    owner_a = UUID("00000000-0000-4000-8000-0000000000a1")
    owner_b = UUID("00000000-0000-4000-8000-0000000000b1")
    shares = allocate_by_weights(10001, [(owner_a, 600_000), (owner_b, 400_000)])
    assert shares[owner_a] == 6001
    assert shares[owner_b] == 4000
    assert round_half_up_ratio(400_000, 8, 100) == 32_000


def test_fin_01_unverified_check_is_not_distributable(client, migrator_engine):
    world = _world(client, migrator_engine)
    receipt = _receipt(client, world, 200_000)
    assert receipt["status"] == "RECORDED"
    assert receipt["available_cents"] == 0
    assert receipt["allocated_cents"] == 0
    _deposit(client, world, receipt["id"], 200_000)
    verified = client.post(
        f"/v1/receipts/{receipt['id']}/bank-verification",
        headers=world["accounting"],
        json={"amount_cents": 200_000},
    )
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["status"] == "BANK_VERIFIED"
    assert body["available_cents"] == 0
    balances = _balances(client, world)
    assert _owner_unrestricted(balances) == {}


def test_fin_02_worked_example_exact_cents(client, migrator_engine, simulator):
    world = _world(client, migrator_engine, fee_numerator=8, fee_denominator=100, reserve_target=80_000)
    for owner_id, amount in ((world["owner_a"], 30_000), (world["owner_b"], 20_000)):
        opened = client.post(
            "/v1/opening-entries/reserve-cash",
            headers={**world["accounting"], "Idempotency-Key": f"open-{owner_id}"},
            json={
                "property_id": world["property_id"],
                "bank_account_id": world["bank_id"],
                "owner_party_id": owner_id,
                "amount_cents": amount,
                "posting_date": "2026-11-01",
                "reason": "Illustrative opening reserve cash for FIN-02",
            },
        )
        assert opened.status_code == 201, opened.text
    receipt = _flow_available(client, world, 400_000)
    allocated = client.post(
        f"/v1/receipts/{receipt['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": "alloc-fin02"},
        json={"posting_date": "2026-11-15"},
    )
    assert allocated.status_code == 201, allocated.text
    invoice = _invoice(client, world, 45_000, "INV-1042")
    approved = client.post(
        f"/v1/invoices/{invoice['id']}/approve",
        headers=world["manager"],
        json={"posting_date": "2026-11-20"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["payable_journal_id"]
    top_up = client.post(
        f"/v1/properties/{world['property_id']}/reserve-top-ups",
        headers=world["accounting"],
        json={"posting_date": "2026-11-21"},
    )
    assert top_up.status_code == 200, top_up.text
    assert top_up.json()["top_up_cents"] == 30_000
    balances = _balances(client, world)
    owners = {item["owner_party_id"]: item for item in balances["owners"]}
    assert owners[world["owner_a"]]["unrestricted_cents"] == 175_800
    assert owners[world["owner_b"]]["unrestricted_cents"] == 117_200
    assert owners[world["owner_a"]]["reserve_cents"] == 48_000
    assert owners[world["owner_b"]]["reserve_cents"] == 32_000
    assert _code(balances, "2050") == 32_000
    assert _code(balances, "2040") == 45_000
    management = client.post(
        "/v1/parties",
        headers={**world["accounting"], "Idempotency-Key": "mgmt-fin02"},
        json={"display_name": "Management company", "kind": "company"},
    ).json()["id"]
    for party in (world["owner_a"], world["owner_b"], world["contractor_id"], management):
        assert client.post(
            "/v1/payee-destinations",
            headers=world["accounting"],
            json={"party_id": party, "masked_label": "****1000"},
        ).status_code == 201
    drafted = client.post(
        "/v1/distribution-batches",
        headers=world["accounting"],
        json={"property_id": world["property_id"], "as_of": "2026-11-22", "management_party_id": management},
    )
    assert drafted.status_code == 201, drafted.text
    owner_amounts = sorted(item["amount_cents"] for item in drafted.json()["items"] if item["kind"] == "OWNER")
    assert owner_amounts == [117_200, 175_800]
    validated = client.post(f"/v1/distribution-batches/{drafted.json()['id']}/validate", headers=world["accounting"])
    assert validated.status_code == 200, validated.text
    assert client.post(
        "/v1/auth/local/step-up",
        headers=world["manager"],
        json={"subject": world["manager_subject"], "password": world["manager_password"]},
    ).status_code == 200
    approved = client.post(
        f"/v1/distribution-batches/{drafted.json()['id']}/approve",
        headers=world["manager"],
        json={"snapshot_hash": validated.json()["snapshot_hash"], "reason": "Reviewed the worked example"},
    )
    assert approved.status_code == 200, approved.text
    settled = client.post(
        f"/v1/distribution-batches/{drafted.json()['id']}/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {}},
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["status"] == "SETTLED"
    assert settled.json()["simulator"] is True
    assert settled.json()["bank_contacted"] is False
    del invoice
    balances = _balances(client, world)
    assert _code(balances, "1030") == 80_000
    assert _code(balances, "2030") == 80_000
    assert _code(balances, "2020") == 0
    assert _code(balances, "2040") == 0
    assert _code(balances, "2050") == 0


def test_fin_12_partial_availability_limits_allocation(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0)
    receipt = _flow_available(client, world, 100_000, available=70_000, verified=100_000)
    assert receipt["status"] == "BANK_VERIFIED"
    assert receipt["available_cents"] == 70_000
    assert receipt["available_at"] is None
    too_much = client.post(
        f"/v1/receipts/{receipt['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": "too-much"},
        json={"amount_cents": 70_001, "posting_date": "2026-11-15"},
    )
    assert too_much.status_code == 409
    allocated = client.post(
        f"/v1/receipts/{receipt['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": "partial"},
        json={"amount_cents": 70_000, "posting_date": "2026-11-15"},
    )
    assert allocated.status_code == 201, allocated.text
    assert allocated.json()["allocated_cents"] == 70_000
    assert allocated.json()["status"] != "AVAILABLE"


def test_missing_fee_agreement_blocks_allocation(client, migrator_engine):
    world = _world(client, migrator_engine, with_agreement=False)
    receipt = _flow_available(client, world, 10_000)
    response = client.post(
        f"/v1/receipts/{receipt['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": "no-fee"},
        json={"posting_date": "2026-11-15"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFIGURATION_REQUIRED"


def test_direct_bank_and_csv_are_gated(client, migrator_engine):
    world = _world(client, migrator_engine, with_agreement=False)
    direct = client.post(
        "/v1/receipts",
        headers={**world["accounting"], "Idempotency-Key": "direct"},
        json=_receipt_body(world, 100, method="DIRECT_BANK"),
    )
    assert direct.status_code == 409
    assert direct.json()["error"]["code"] == "DIRECT_BANK_TEMPLATE_UNCONFIGURED"
    csv_import = client.post(
        "/v1/bank-imports",
        headers={**world["accounting"], "Idempotency-Key": "csv"},
        json={"format": "csv", "csv_text": "amount,date\n10,2026-11-01"},
    )
    assert csv_import.status_code == 409
    assert csv_import.json()["error"]["code"] == "BANK_IMPORT_FORMAT_UNCONFIGURED"
    first = client.post(
        "/v1/bank-imports",
        headers={**world["accounting"], "Idempotency-Key": "canon"},
        json={"transactions": [{"bank_account_id": world["bank_id"], "external_id": "txn-1", "amount_cents": 100, "posted_on": "2026-11-01"}]},
    )
    assert first.status_code == 201, first.text
    again = client.post(
        "/v1/bank-imports",
        headers={**world["accounting"], "Idempotency-Key": "canon-2"},
        json={"transactions": [{"bank_account_id": world["bank_id"], "external_id": "txn-1", "amount_cents": 100, "posted_on": "2026-11-01"}]},
    )
    assert again.json()["created"] == 0
    assert again.json()["existing"] == 1
    conflict = client.post(
        "/v1/bank-imports",
        headers={**world["accounting"], "Idempotency-Key": "canon"},
        json={"transactions": [{"bank_account_id": world["bank_id"], "external_id": "txn-2", "amount_cents": 5, "posted_on": "2026-11-02"}]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_security_deposit_cannot_fund_owner_or_fee(client, migrator_engine):
    world = _world(client, migrator_engine)
    receipt = _flow_available(client, world, 50_000, method="SECURITY_DEPOSIT_CHECK")
    blocked = client.post(
        f"/v1/receipts/{receipt['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": "deposit-alloc"},
        json={"posting_date": "2026-11-15"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "SECURITY_DEPOSIT_RESTRICTED"
    balances = _balances(client, world)
    assert _code(balances, "2070") == 50_000
    assert _owner_unrestricted(balances) == {}


def test_rent_charge_does_not_post_cash(client, migrator_engine):
    world = _world(client, migrator_engine, with_agreement=False)
    response = client.post(
        "/v1/rent-charges",
        headers={**world["accounting"], "Idempotency-Key": "charge"},
        json={"lease_id": world["lease_id"], "due_on": "2026-11-01", "amount_cents": 100_000, "description": "November rent"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["journal_posted"] is False
    balances = _balances(client, world)
    assert all(item["amount_cents"] == 0 for item in balances["accounts"])


def test_fin_11_database_rejects_bad_journals(client, migrator_engine, app):
    world = _world(client, migrator_engine, with_agreement=False)
    closed = client.post(
        "/v1/period-closes",
        headers=world["accounting"],
        json={"period_start": "2026-10-01", "period_end": "2026-10-31", "reason": "October close"},
    )
    assert closed.status_code == 200, closed.text
    with pytest.raises(DBAPIError):
        with app.state.engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.organization_id', :org, true)"), {"org": world["org_id"]})
            conn.execute(
                text(
                    """
                    SELECT app_post_journal(
                      :org, 'MANUAL', :source, '2026-10-15',
                      CAST(:lines AS jsonb), 'hash', NULL
                    )
                    """
                ),
                {
                    "org": world["org_id"],
                    "source": str(uuid4()),
                    "lines": '[{"account_code":"1010","side":"DEBIT","amount_cents":100,"property_id":"","owner_party_id":"","lease_id":"","bank_account_id":"","purpose":"RENT"},{"account_code":"2010","side":"CREDIT","amount_cents":100,"property_id":"","owner_party_id":"","lease_id":"","bank_account_id":"","purpose":"RENT"}]',
                },
            )
    with pytest.raises(DBAPIError):
        with app.state.engine.begin() as conn:
            conn.execute(text("INSERT INTO journal_lines (id, organization_id, journal_id, account_id, side, amount_cents, currency) VALUES (:id, :org, :id, :id, 'DEBIT', 1, 'USD')"), {"id": uuid4(), "org": world["org_id"]})


def test_fin_19_invoice_deficit_blocks_settlement_not_accrual(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0)
    invoice = _invoice(client, world, 20_000, "TOO-BIG")
    approved = client.post(
        f"/v1/invoices/{invoice['id']}/approve",
        headers=world["manager"],
        json={"posting_date": "2026-11-20"},
    )
    assert approved.status_code == 200, approved.text
    balances = _balances(client, world)
    assert _code(balances, "2040") == 20_000
    assert sum(item["unrestricted_cents"] for item in balances["owners"]) == -20_000
    assert client.post(
        "/v1/payee-destinations",
        headers=world["accounting"],
        json={"party_id": world["contractor_id"], "masked_label": "****1000"},
    ).status_code == 201
    drafted = client.post(
        "/v1/distribution-batches",
        headers=world["accounting"],
        json={"property_id": world["property_id"], "as_of": "2026-11-21", "management_party_id": None},
    )
    assert drafted.status_code == 201, drafted.text
    blocked = client.post(f"/v1/distribution-batches/{drafted.json()['id']}/validate", headers=world["accounting"])
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INSUFFICIENT_FUNDS"


def test_fin_06_other_property_cash_cannot_fund_payment(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0)
    _flow_available(client, world, 10_000)
    other = client.post(
        "/v1/properties",
        headers={**world["admin"], "Idempotency-Key": "other-property"},
        json={**PROPERTY, "name": "Other House"},
    )
    assert other.status_code == 201, other.text
    unit = client.post(
        f"/v1/properties/{other.json()['id']}/units",
        headers={**world["admin"], "Idempotency-Key": "other-unit"},
        json={"label": "B"},
    )
    other_world = dict(world)
    other_world["property_id"] = other.json()["id"]
    other_world["unit_id"] = unit.json()["id"]
    lease = client.post(
        "/v1/leases",
        headers={**world["accounting"], "Idempotency-Key": "other-lease"},
        json={"unit_id": other_world["unit_id"], "start_date": "2026-01-01", "end_date": "2027-01-01", "agreed_rent_cents": 1},
    )
    other_world["lease_id"] = lease.json()["id"]
    client.post(
        f"/v1/properties/{other_world['property_id']}/ownership-periods",
        headers={**world["accounting"], "Idempotency-Key": "other-own"},
        json={"start_date": "2026-01-01", "end_date": "2027-01-01", "shares": [{"owner_party_id": world["owner_a"], "weight": 1_000_000}]},
    )
    client.post(
        f"/v1/properties/{other_world['property_id']}/agreements",
        headers={**world["manager"], "Idempotency-Key": "other-agree"},
        json={"start_date": "2026-01-01", "end_date": "2027-01-01", "rate_numerator": 0, "rate_denominator": 1, "reserve_target_total_cents": 0},
    )
    _flow_available(client, other_world, 1_000_000)
    invoice = _invoice(client, world, 20_000, "CROSS")
    client.post(f"/v1/invoices/{invoice['id']}/approve", headers=world["manager"], json={"posting_date": "2026-11-20"})
    assert client.post(
        "/v1/payee-destinations",
        headers=world["accounting"],
        json={"party_id": world["contractor_id"], "masked_label": "****2000"},
    ).status_code == 201
    drafted = client.post(
        "/v1/distribution-batches",
        headers=world["accounting"],
        json={"property_id": world["property_id"], "as_of": "2026-11-21", "management_party_id": None},
    )
    assert drafted.status_code == 201, drafted.text
    blocked = client.post(f"/v1/distribution-batches/{drafted.json()['id']}/validate", headers=world["accounting"])
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    assert _code(_balances(client, other_world), "1030") == 1_000_000


def test_invoice_approval_posts_once_and_ai_cannot_post(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0)
    invoice = _invoice(client, world, 4_500, "ONCE")
    first = None
    for _ in range(5):
        response = client.post(
            f"/v1/invoices/{invoice['id']}/approve",
            headers=world["manager"],
            json={"posting_date": "2026-11-20"},
        )
        assert response.status_code == 200, response.text
        first = first or response.json()["payable_journal_id"]
        assert response.json()["payable_journal_id"] == first
    denied = client.post(
        "/v1/receipts",
        headers={**world["ai"], "Idempotency-Key": "ai"},
        json=_receipt_body(world, 100),
    )
    assert denied.status_code == 403
    submit = client.post(
        "/v1/distribution-batches/00000000-0000-4000-8000-00000000abcd/submit",
        headers=world["manager"],
        json={"posting_date": "2026-11-23", "scripts": {}},
    )
    assert submit.status_code == 409
    assert submit.json()["error"]["code"] == "PROVIDER_SUBMISSION_DISABLED"


def test_fin_17_later_ownership_does_not_rewrite_posted_allocation(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0)
    first = _flow_available(client, world, 10_001)
    allocated = client.post(
        f"/v1/receipts/{first['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": "hist"},
        json={"posting_date": "2026-11-15"},
    )
    assert allocated.status_code == 201, allocated.text
    before = _owner_unrestricted(_balances(client, world))
    assert before[world["owner_a"]] == 6_001
    later = client.post(
        f"/v1/properties/{world['property_id']}/ownership-periods",
        headers={**world["accounting"], "Idempotency-Key": "later-period"},
        json={
            "start_date": "2027-01-01",
            "end_date": "2028-01-01",
            "shares": [
                {"owner_party_id": world["owner_a"], "weight": 400_000},
                {"owner_party_id": world["owner_b"], "weight": 600_000},
            ],
        },
    )
    assert later.status_code == 201, later.text
    agreed = client.post(
        f"/v1/properties/{world['property_id']}/agreements",
        headers={**world["manager"], "Idempotency-Key": "later-fee"},
        json={
            "start_date": "2027-01-01",
            "end_date": "2028-01-01",
            "rate_numerator": 0,
            "rate_denominator": 1,
            "reserve_target_total_cents": 0,
        },
    )
    assert agreed.status_code == 201, agreed.text
    second = _flow_available(client, world, 10_001)
    follow = client.post(
        f"/v1/receipts/{second['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": "follow"},
        json={"posting_date": "2027-02-01"},
    )
    assert follow.status_code == 201, follow.text
    after = _owner_unrestricted(_balances(client, world))
    assert after[world["owner_a"]] - before[world["owner_a"]] == 4_000
    assert before[world["owner_a"]] == 6_001


def test_fin_13_deficit_limits_distribution_candidate(client, migrator_engine, app):
    world = _world(client, migrator_engine, fee_numerator=8, fee_denominator=100, reserve_target=10_000, single_owner=True)
    with app.state.engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.organization_id', :org, true), set_config('app.actor_id', :actor, true)"),
            {"org": world["org_id"], "actor": str(world["accounting_id"])},
        )
        conn.execute(
            text(
                """
                SELECT app_post_journal(
                  :org, 'OPENING_DEFICIT', :source, '2026-11-01',
                  CAST(:lines AS jsonb), :lines_hash, NULL
                )
                """
            ),
            {
                "org": world["org_id"],
                "source": str(uuid4()),
                "lines_hash": "fin13-opening-deficit",
                "lines": (
                    '[{"account_code":"2020","side":"DEBIT","amount_cents":10000,'
                    f'"property_id":"{world["property_id"]}","owner_party_id":"{world["owner_a"]}",'
                    '"lease_id":"","bank_account_id":"","purpose":"RENT"},'
                    '{"account_code":"1040","side":"CREDIT","amount_cents":10000,'
                    f'"property_id":"{world["property_id"]}","owner_party_id":"",'
                    '"lease_id":"","bank_account_id":"","purpose":"RENT"}]'
                ),
            },
        )
    receipt = _flow_available(client, world, 100_000)
    allocated = client.post(
        f"/v1/receipts/{receipt['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": "deficit-alloc"},
        json={"posting_date": "2026-11-15"},
    )
    assert allocated.status_code == 201, allocated.text
    repair = _invoice(client, world, 20_000, "REPAIR")
    approved = client.post(
        f"/v1/invoices/{repair['id']}/approve",
        headers=world["manager"],
        json={"posting_date": "2026-11-16"},
    )
    assert approved.status_code == 200, approved.text
    top_up = client.post(
        f"/v1/properties/{world['property_id']}/reserve-top-ups",
        headers=world["accounting"],
        json={"posting_date": "2026-11-17"},
    )
    assert top_up.status_code == 200, top_up.text
    balances = _balances(client, world)
    assert balances["owners"][0]["unrestricted_cents"] == 52_000


def _world(client, migrator_engine, *, fee_numerator=0, fee_denominator=1, reserve_target=0, with_agreement=True, single_owner=False):
    org_id = uuid4()
    admin_id = uuid4()
    accounting_id = uuid4()
    manager_id = uuid4()
    ai_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(conn, org_id=org_id, user_id=admin_id, subject=f"admin-{admin_id.hex[:8]}@example.test", password="local-admin-password", roles=["organization_administrator"], org_name="Books")
        seed_member(conn, org_id=org_id, user_id=accounting_id, subject=f"acct-{accounting_id.hex[:8]}@example.test", password="local-accounting-password", roles=["accounting_staff"])
        seed_member(conn, org_id=org_id, user_id=manager_id, subject=f"mgr-{manager_id.hex[:8]}@example.test", password="local-manager-password", roles=["property_manager"])
        seed_member(conn, org_id=org_id, user_id=ai_id, subject=f"ai-{ai_id.hex[:8]}@example.test", password="local-ai-password-xx", roles=["ai_service"])
    admin = bearer(login(client, f"admin-{admin_id.hex[:8]}@example.test", "local-admin-password"))
    accounting = bearer(login(client, f"acct-{accounting_id.hex[:8]}@example.test", "local-accounting-password"))
    manager = bearer(login(client, f"mgr-{manager_id.hex[:8]}@example.test", "local-manager-password"))
    ai = bearer(login(client, f"ai-{ai_id.hex[:8]}@example.test", "local-ai-password-xx"))
    property_id = client.post("/v1/properties", headers={**admin, "Idempotency-Key": f"prop-{org_id}"}, json=PROPERTY).json()["id"]
    unit_id = client.post(f"/v1/properties/{property_id}/units", headers={**admin, "Idempotency-Key": f"unit-{org_id}"}, json={"label": "1"}).json()["id"]
    payer = client.post("/v1/parties", headers={**accounting, "Idempotency-Key": f"payer-{org_id}"}, json={"display_name": "Payer", "kind": "person"}).json()["id"]
    owner_a = client.post("/v1/parties", headers={**accounting, "Idempotency-Key": f"owna-{org_id}"}, json={"display_name": "Owner A", "kind": "person"}).json()["id"]
    owner_b = owner_a
    if not single_owner:
        owner_b = client.post("/v1/parties", headers={**accounting, "Idempotency-Key": f"ownb-{org_id}"}, json={"display_name": "Owner B", "kind": "person"}).json()["id"]
    bank_id = client.post("/v1/bank-accounts", headers={**accounting, "Idempotency-Key": f"bank-{org_id}"}, json={"display_name": "Trust", "masked_label": "****1000"}).json()["id"]
    contractor = client.post("/v1/parties", headers={**accounting, "Idempotency-Key": f"co-{org_id}"}, json={"display_name": "Plumber", "kind": "company"}).json()["id"]
    lease_id = client.post("/v1/leases", headers={**accounting, "Idempotency-Key": f"lease-{org_id}"}, json={"unit_id": unit_id, "start_date": "2026-01-01", "end_date": "2027-01-01", "agreed_rent_cents": 100_000}).json()["id"]
    shares = [{"owner_party_id": owner_a, "weight": 1_000_000}] if single_owner else [{"owner_party_id": owner_a, "weight": 600_000}, {"owner_party_id": owner_b, "weight": 400_000}]
    owned = client.post(
        f"/v1/properties/{property_id}/ownership-periods",
        headers={**accounting, "Idempotency-Key": f"own-{org_id}"},
        json={"start_date": "2026-01-01", "end_date": "2027-01-01", "shares": shares},
    )
    assert owned.status_code == 201, owned.text
    if with_agreement:
        agreed = client.post(
            f"/v1/properties/{property_id}/agreements",
            headers={**manager, "Idempotency-Key": f"agr-{org_id}"},
            json={
                "start_date": "2026-01-01",
                "end_date": "2027-01-01",
                "rate_numerator": fee_numerator,
                "rate_denominator": fee_denominator,
                "reserve_target_total_cents": reserve_target,
            },
        )
        assert agreed.status_code == 201, agreed.text
    return {
        "org_id": str(org_id),
        "admin": admin,
        "accounting": accounting,
        "manager": manager,
        "manager_subject": f"mgr-{manager_id.hex[:8]}@example.test",
        "manager_password": "local-manager-password",
        "accounting_id": accounting_id,
        "ai": ai,
        "property_id": property_id,
        "unit_id": unit_id,
        "payer_id": payer,
        "owner_a": owner_a,
        "owner_b": owner_b,
        "bank_id": bank_id,
        "contractor_id": contractor,
        "lease_id": lease_id,
        "manager_id": manager_id,
    }


def _receipt_body(world, amount, method="CHECK"):
    return {
        "property_id": world["property_id"],
        "unit_id": world["unit_id"],
        "lease_id": world["lease_id"],
        "payer_party_id": world["payer_id"],
        "method": method,
        "amount_cents": amount,
        "received_at": "2026-11-06T15:00:00Z",
        "posting_date": "2026-11-06",
        "reference": "masked-ref",
        "service_period": "2026-11",
    }


def _receipt(client, world, amount, method="CHECK"):
    response = client.post(
        "/v1/receipts",
        headers={**world["accounting"], "Idempotency-Key": f"rcpt-{uuid4()}"},
        json=_receipt_body(world, amount, method),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _deposit(client, world, receipt_id, amount):
    response = client.post(
        "/v1/deposit-batches",
        headers={**world["accounting"], "Idempotency-Key": f"dep-{uuid4()}"},
        json={
            "property_id": world["property_id"],
            "bank_account_id": world["bank_id"],
            "slip_reference": "slip",
            "deposited_on": "2026-11-07",
            "items": [{"receipt_id": receipt_id, "amount_cents": amount}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _flow_available(client, world, amount, available=None, verified=None, method="CHECK"):
    receipt = _receipt(client, world, amount, method)
    _deposit(client, world, receipt["id"], amount)
    verified_amount = amount if verified is None else verified
    available_amount = amount if available is None else available
    assert client.post(
        f"/v1/receipts/{receipt['id']}/bank-verification",
        headers=world["accounting"],
        json={"amount_cents": verified_amount},
    ).status_code == 200
    response = client.post(
        f"/v1/receipts/{receipt['id']}/availability",
        headers=world["accounting"],
        json={"amount_cents": available_amount, "posting_date": "2026-11-08"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _invoice(client, world, amount, number):
    response = client.post(
        "/v1/invoices",
        headers={**world["accounting"], "Idempotency-Key": f"inv-{number}-{uuid4()}"},
        json={
            "property_id": world["property_id"],
            "contractor_party_id": world["contractor_id"],
            "invoice_number": number,
            "tax_cents": 0,
            "total_cents": amount,
            "lines": [{"description": "Repair", "quantity": 1, "unit_price_cents": amount, "line_total_cents": amount}],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["payable_journal_id"] is None
    return response.json()


def _balances(client, world):
    response = client.get(f"/v1/properties/{world['property_id']}/balances", headers=world["accounting"])
    assert response.status_code == 200, response.text
    return response.json()


def _code(balances, code):
    return next(item["amount_cents"] for item in balances["accounts"] if item["code"] == code)


def _owner_unrestricted(balances):
    return {item["owner_party_id"]: item["unrestricted_cents"] for item in balances["owners"] if item["unrestricted_cents"]}
