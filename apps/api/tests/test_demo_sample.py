"""The fixture role switch exists only for grok_demo_sample."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from grok_bot.api.app import create_app
from grok_bot.migrate import upgrade
from grok_bot.seed import ensure_demo_statement, seed_demo
from grok_bot.settings import Settings
from tests.support import CONTACT_KEY, SESSION_SECRET, database_url, psql, recreate_database


def test_demo_route_is_absent_unless_the_sample_database_is_configured(client):
    assert client.post("/v1/demo/session", json={"role": "tenant"}).status_code == 404


def test_demo_session_refuses_other_databases_and_production(migrator_engine):
    with migrator_engine.connect() as conn:
        assert conn.execute(text("SELECT user_id FROM app_demo_sample_session('tenant')")).first() is None
    with pytest.raises(SystemExit, match="grok_demo_sample"):
        seed_demo(database_url("grok_migrator", "grok_m0_test"), "test", SESSION_SECRET)
    refused = Settings(
        app_env="production",
        database_url=database_url("grok_app", "grok_demo_sample"),
        migration_database_url=database_url("grok_migrator", "grok_demo_sample"),
        session_secret=SESSION_SECRET,
        contact_encryption_key=CONTACT_KEY,
        demo_fixture="sample",
    )
    assert refused.allows_demo_session is False
    other = Settings(
        app_env="test",
        database_url=database_url("grok_app", "grok_m0_test"),
        migration_database_url=database_url("grok_migrator", "grok_m0_test"),
        session_secret=SESSION_SECRET,
        contact_encryption_key=CONTACT_KEY,
        demo_fixture="sample",
    )
    assert other.allows_demo_session is False


def test_sample_database_can_switch_roles_without_a_password():
    psql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'grok_demo_sample' AND pid <> pg_backend_pid()")
    psql("DROP DATABASE IF EXISTS grok_demo_sample")
    recreate_database("grok_demo_sample")
    url = database_url("grok_migrator", "grok_demo_sample")
    upgrade(url)
    seed_demo(url, "test", SESSION_SECRET)
    settings = Settings(
        app_env="test",
        database_url=database_url("grok_app", "grok_demo_sample"),
        migration_database_url=url,
        session_secret=SESSION_SECRET,
        contact_encryption_key=CONTACT_KEY,
        demo_fixture="sample",
    )
    assert settings.allows_demo_session is True
    app = create_app(settings)
    try:
        with TestClient(app) as demo:
            accounting = demo.post("/v1/demo/session", json={"role": "accounting_staff"})
            assert accounting.status_code == 200, accounting.text
            assert "password" not in accounting.json()
            token = {"Authorization": f"Bearer {accounting.json()['token']}"}
            me = demo.get("/v1/me", headers=token)
            assert me.status_code == 200, me.text
            assert me.json()["display_name"] == "Fixture Accounting"
            assert me.json()["production_oidc"] is False
            balances = demo.get("/v1/properties", headers=token)
            assert balances.status_code == 200, balances.text
            property_id = balances.json()["items"][0]["id"]
            money = demo.get(f"/v1/properties/{property_id}/balances", headers=token)
            assert money.status_code == 200, money.text
            accounts = {item["code"]: item["amount_cents"] for item in money.json()["accounts"]}
            assert accounts["1010"] == 180_000
            assert accounts["1030"] == 0
            # Existing demo installs gain the owner walkthrough without a reset
            # or duplicate statements, and without changing available funds.
            from sqlalchemy import create_engine
            upgrade_engine = create_engine(url)
            ensure_demo_statement(upgrade_engine, "test")
            ensure_demo_statement(upgrade_engine, "test")
            with pytest.raises(SystemExit):
                ensure_demo_statement(upgrade_engine, "production")
            upgrade_engine.dispose()
            owner = demo.post("/v1/demo/session", json={"role": "owner"})
            statements = demo.get("/v1/statements", headers={"Authorization": f"Bearer {owner.json()['token']}"})
            assert statements.status_code == 200, statements.text
            assert len(statements.json()["items"]) == 1
            assert statements.json()["items"][0]["unrestricted_cents"] == 0
            manager = demo.post("/v1/demo/session", json={"role": "property_manager"})
            switches = demo.get("/v1/kill-switches", headers={"Authorization": f"Bearer {manager.json()['token']}"})
            assert switches.status_code == 200, switches.text
            assert switches.json() == {
                "messaging_enabled": False,
                "calendar_enabled": False,
                "payment_enabled": False,
            }
            unknown = demo.post("/v1/demo/session", json={"role": "ai_service"})
            assert unknown.status_code == 422
    finally:
        app.state.engine.dispose()
        psql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'grok_demo_sample' AND pid <> pg_backend_pid()")
        psql("DROP DATABASE IF EXISTS grok_demo_sample")
