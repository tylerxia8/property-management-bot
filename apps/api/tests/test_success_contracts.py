"""Declared success schemas and a local read of the proposed §14 portfolio size."""

import threading
import time
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import text

from grok_bot.api.success import LedgerOut, PropertyPageOut, ProspectOut, ReceiptOut, TicketOut
from tests.support import bearer, login, seed_member
from tests.test_accounting_core import _flow_available, _receipt, _world


def test_every_mounted_success_response_has_a_schema(app):
    schema = app.openapi()
    missing = []
    operations = 0
    typed = 0
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            operations += 1
            for code, response in operation.get("responses", {}).items():
                if not str(code).startswith("2"):
                    continue
                content = response.get("content") or {}
                if any(body.get("schema") for body in content.values()):
                    typed += 1
                else:
                    missing.append(f"{method.upper()} {path} {code}")
    no_success = []
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            codes = [code for code in operation.get("responses", {}) if str(code).startswith("2")]
            if not codes:
                no_success.append(f"{method.upper()} {path}")
    assert missing == []
    assert sorted(no_success) == [
        "POST /v1/distribution-declarations/{declaration_id}/simulated-settlement",
        "POST /v1/fee-settlements/simulated",
        "POST /v1/invoices/{invoice_id}/simulated-settlement",
        "POST /v1/properties/{property_id}/distribution-declarations",
        "POST /v1/prospects/{prospect_id}/consumer-reports",
    ]
    print(f"SCHEMA_COVERAGE operations={operations} typed_success={typed} undocumented={len(missing)}")
    assert typed == operations - len(no_success) + 1
    components = schema["components"]["schemas"]
    envelope = components["ErrorEnvelope"]
    assert set(envelope["properties"]) == {"error", "request_id"}
    assert "code" in components["ErrorBody"]["properties"]
    login_op = schema["paths"]["/v1/auth/local/login"]["post"]
    assert login_op["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/LoginBody")
    assert any(item["name"] == "limit" and item["schema"]["type"] == "integer" for item in schema["paths"]["/v1/properties"]["get"]["parameters"])
    media = schema["paths"]["/v1/media/{media_id}/content"]["get"]["responses"]["200"]["content"]
    assert media["application/octet-stream"]["schema"]["format"] == "binary"
    assert "application/json" not in media


def test_financial_prospect_and_maintenance_responses_match_their_models(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    listed = client.get("/v1/properties", headers=world["manager"])
    assert listed.status_code == 200, listed.text
    PropertyPageOut.model_validate(listed.json())
    ledger = client.get(f"/v1/properties/{world['property_id']}/ledger", headers=world["accounting"])
    assert ledger.status_code == 200, ledger.text
    LedgerOut.model_validate(ledger.json())
    receipt = _receipt(client, world, 1_500)
    fetched = client.get(f"/v1/receipts/{receipt['id']}", headers=world["accounting"])
    assert fetched.status_code == 200, fetched.text
    ReceiptOut.model_validate(fetched.json())
    ticket = client.post(
        "/v1/maintenance-tickets",
        headers=world["manager"],
        json={"description": "Water under the kitchen sink"},
    )
    assert ticket.status_code == 201, ticket.text
    TypeAdapter(TicketOut).validate_python(ticket.json())
    prospect_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=UUID(world["org_id"]),
            user_id=prospect_id,
            subject=f"prospect-{prospect_id.hex[:8]}@example.test",
            password="local-prospect-password",
            roles=["prospect"],
        )
    token = bearer(login(client, f"prospect-{prospect_id.hex[:8]}@example.test", "local-prospect-password"))
    created = client.post(
        "/v1/prospects",
        headers=token,
        json={"listing_id": None},
    )
    assert created.status_code == 201, created.text
    ProspectOut.model_validate(created.json())


def test_allocated_receipt_return_is_not_invented(client, migrator_engine):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0, single_owner=True)
    receipt = _flow_available(client, world, 2_000)
    allocated = client.post(
        f"/v1/receipts/{receipt['id']}/allocations",
        headers={**world["accounting"], "Idempotency-Key": f"alloc-{uuid4()}"},
        json={"amount_cents": 500, "posting_date": "2026-11-09"},
    )
    assert allocated.status_code == 201, allocated.text
    returned = client.post(
        f"/v1/receipts/{receipt['id']}/returns",
        headers={**world["accounting"], "Idempotency-Key": f"ret-{uuid4()}"},
        json={"amount_cents": 100, "posting_date": "2026-11-10", "reason": "After allocation"},
    )
    assert returned.status_code == 409
    assert returned.json()["error"]["code"] == "CONFIGURATION_REQUIRED"
    assert "§4.6" in returned.json()["error"]["message"]


def test_proposed_portfolio_read_load(client, migrator_engine):
    """Local measurement against PRD §14 proposed sizing, not a confirmed portfolio or a staging run.

    §14 calls 100 properties, 300 units, 1,000 contacts, 20 concurrent sessions, and
    10,000 messages a month planning assumptions. The ordinary API p95 of 500 ms and
    the paginated ledger p95 of 1 second are proposed targets under that sizing.
    """

    org_id = uuid4()
    user_id = uuid4()
    subject = f"load-{user_id.hex[:8]}@example.test"
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=user_id,
            subject=subject,
            password="local-manager-password",
            roles=["property_manager"],
            org_name="Proposed load",
        )
        conn.execute(
            text(
                """
                INSERT INTO properties (
                  id, organization_id, name, address_line1, city, region, postal_code, country_code, timezone, created_by
                )
                SELECT gen_random_uuid(), :org, 'House ' || g, '1 Main', 'Raleigh', 'NC', '27601', 'US', 'America/New_York', :user_id
                FROM generate_series(1, 100) AS g
                """
            ),
            {"org": org_id, "user_id": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO units (id, organization_id, property_id, label)
                SELECT gen_random_uuid(), p.organization_id, p.id, 'Unit ' || g
                FROM properties AS p
                CROSS JOIN generate_series(1, 3) AS g
                WHERE p.organization_id = :org
                """
            ),
            {"org": org_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO parties (id, organization_id, display_name, kind)
                SELECT gen_random_uuid(), :org, 'Contact ' || g, 'person'
                FROM generate_series(1, 1000) AS g
                """
            ),
            {"org": org_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO contacts (id, organization_id, party_id, kind, ciphertext, nonce, key_version)
                SELECT gen_random_uuid(), p.organization_id, p.id, 'other', '\\x00'::bytea, '\\x01'::bytea, 1
                FROM parties AS p
                WHERE p.organization_id = :org
                """
            ),
            {"org": org_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO maintenance_tickets (
                  id, organization_id, ticket_number, verification, status, category, description, reporter_user_id
                )
                SELECT gen_random_uuid(), :org, g, 'VERIFIED', 'INTAKE_OPEN', 'general', 'Fixture message thread', :user_id
                FROM generate_series(1, 200) AS g
                """
            ),
            {"org": org_id, "user_id": user_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO ticket_messages (id, organization_id, ticket_id, body)
                SELECT gen_random_uuid(), t.organization_id, t.id, 'Fixture message ' || g
                FROM maintenance_tickets AS t
                CROSS JOIN generate_series(1, 50) AS g
                WHERE t.organization_id = :org
                """
            ),
            {"org": org_id},
        )
        ticket_id = conn.execute(
            text("SELECT id FROM maintenance_tickets WHERE organization_id = :org ORDER BY ticket_number LIMIT 1"),
            {"org": org_id},
        ).scalar()
        property_id = conn.execute(
            text("SELECT id FROM properties WHERE organization_id = :org ORDER BY name LIMIT 1"),
            {"org": org_id},
        ).scalar()
        counts = conn.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM properties WHERE organization_id = :org),
                  (SELECT count(*) FROM units WHERE organization_id = :org),
                  (SELECT count(*) FROM contacts WHERE organization_id = :org),
                  (SELECT count(*) FROM ticket_messages WHERE organization_id = :org)
                """
            ),
            {"org": org_id},
        ).one()
    assert counts == (100, 300, 1000, 10000)
    token = bearer(login(client, subject, "local-manager-password"))
    paths = [
        "/v1/properties?limit=50",
        f"/v1/properties/{property_id}/ledger?limit=50",
        "/v1/parties",
        f"/v1/maintenance-tickets/{ticket_id}",
        "/v1/operations/queue",
    ]
    samples: list[tuple[str, float, int]] = []
    lock = threading.Lock()

    def worker() -> None:
        local = []
        for _ in range(5):
            for path in paths:
                started = time.perf_counter()
                response = client.get(path, headers=token)
                elapsed = time.perf_counter() - started
                local.append((path.split("?")[0], elapsed, response.status_code))
        with lock:
            samples.extend(local)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - started
    errors = [item for item in samples if item[2] != 200]
    durations = sorted(item[1] for item in samples)
    ledger = sorted(item[1] for item in samples if item[0].endswith("/ledger"))

    def pct(values: list[float], fraction: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, int(round(fraction * (len(values) - 1)))))
        return values[index]

    p50 = pct(durations, 0.50)
    p95 = pct(durations, 0.95)
    ledger_p95 = pct(ledger, 0.95)
    throughput = len(samples) / wall if wall else 0
    print(
        "LOAD_RESULT "
        f"requests={len(samples)} errors={len(errors)} wall_s={wall:.3f} "
        f"throughput_rps={throughput:.2f} p50_ms={p50 * 1000:.1f} p95_ms={p95 * 1000:.1f} "
        f"ledger_p95_ms={ledger_p95 * 1000:.1f} "
        f"proposed_api_p95_ms=500 achieved_api={str(p95 <= 0.5).lower()} "
        f"proposed_ledger_p95_ms=1000 achieved_ledger={str(ledger_p95 <= 1).lower()}"
    )
    assert errors == []
    assert len(samples) == 20 * 5 * len(paths)
    assert p95 <= 0.5
    assert ledger_p95 <= 1
