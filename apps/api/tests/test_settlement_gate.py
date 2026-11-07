from fastapi.testclient import TestClient

from grok_bot.api.app import create_app
from grok_bot.settings import Settings
from tests.support import CONTACT_KEY, SESSION_SECRET, database_url
from tests.test_accounting_core import _balances, _code, _invoice, _world


def test_manager_cannot_clear_payable_without_approval_contract(client, migrator_engine, fixture_settlement):
    world = _world(client, migrator_engine, fee_numerator=0, fee_denominator=1, reserve_target=0)
    invoice = _invoice(client, world, 4_000, "GATE")
    approved = client.post(
        f"/v1/invoices/{invoice['id']}/approve",
        headers=world["manager"],
        json={"posting_date": "2026-11-20"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["payable_journal_id"]
    blocked = client.post(
        f"/v1/invoices/{invoice['id']}/simulated-settlement",
        headers=world["manager"],
        json={"posting_date": "2026-11-21"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "APPROVAL_CONTRACT_REQUIRED"
    balances = _balances(client, world)
    assert _code(balances, "2040") == 4_000
    assert _code(balances, "1030") == 0
    declared = client.post(
        f"/v1/properties/{world['property_id']}/distribution-declarations",
        headers=world["manager"],
        json={"posting_date": "2026-11-22"},
    )
    assert declared.status_code == 409
    assert declared.json()["error"]["code"] == "APPROVAL_CONTRACT_REQUIRED"
    assert _code(_balances(client, world), "2060") == 0


def test_production_flag_does_not_enable_fixture_settlement():
    settings = Settings(
        app_env="production",
        allow_fixture_ledger_settlement=True,
        database_url=database_url("grok_app", "grok_m0_test"),
        migration_database_url=database_url("grok_migrator", "grok_m0_test"),
        session_secret=SESSION_SECRET,
        contact_encryption_key=CONTACT_KEY,
    )
    assert settings.fixture_ledger_settlement_allowed is False
    app = create_app(settings)
    with TestClient(app) as production:
        response = production.post(
            "/v1/invoices/00000000-0000-4000-8000-000000000099/simulated-settlement",
            json={"posting_date": "2026-11-21"},
        )
    app.state.engine.dispose()
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"

