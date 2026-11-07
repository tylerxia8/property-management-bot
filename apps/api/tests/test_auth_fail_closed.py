import time

from fastapi.testclient import TestClient

from grok_bot.api.app import create_app
from grok_bot.auth.tokens import _sign, mint_local_token
from grok_bot.seed import seed_e2e
from grok_bot.settings import Settings
from tests.support import CONTACT_KEY, SESSION_SECRET, database_url, settings_for


def test_default_environment_is_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    settings = Settings(
        database_url="postgresql+psycopg://localhost/db",
        migration_database_url="postgresql+psycopg://localhost/db",
        session_secret=SESSION_SECRET,
        contact_encryption_key=CONTACT_KEY,
    )
    assert settings.app_env == "production"
    assert settings.allows_local_auth is False


def test_production_rejects_local_login_and_local_tokens(cluster):
    app = create_app(settings_for("grok_m0_test", "production"))
    with TestClient(app) as client:
        health = client.get("/v1/health", headers={"Origin": "http://127.0.0.1:3000"})
        assert health.status_code == 200
        assert health.json()["local_auth_enabled"] is False
        assert "access-control-allow-origin" not in health.headers
        missing = client.post(
            "/v1/auth/local/login",
            json={"subject": "admin@example.test", "password": "local-admin-password"},
        )
        assert missing.status_code == 404
        local_token = mint_local_token(
            secret=SESSION_SECRET,
            user_id=__import__("uuid").UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"),
            organization_id=__import__("uuid").UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"),
            environment="test",
            ttl_seconds=300,
        )
        assert client.get("/v1/me", headers={"Authorization": f"Bearer {local_token}"}).status_code == 401
        oidc = _sign(
            {
                "amr": "oidc",
                "env": "production",
                "exp": int(time.time()) + 300,
                "org": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                "sub": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
                "v": 1,
            },
            SESSION_SECRET,
        )
        assert client.get("/v1/me", headers={"Authorization": f"Bearer {oidc}"}).status_code == 401
    app.state.engine.dispose()


def test_seed_refuses_production():
    try:
        seed_e2e(database_url("grok_migrator", "grok_m0_e2e"), "production")
    except SystemExit as exc:
        assert "refuses" in str(exc)
    else:
        raise AssertionError("production seed was allowed")


def test_dev_cors_allows_local_web_only(client):
    response = client.get("/v1/health", headers={"Origin": "http://127.0.0.1:3000"})
    assert response.json()["local_auth_enabled"] is True
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
