import os
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from uuid import uuid4

from grok_bot.api.app import create_app
from grok_bot.migrate import upgrade
from tests.support import (
    BOOTSTRAP,
    database_url,
    login,
    recreate_database,
    seed_member,
    settings_for,
)


@pytest.fixture(scope="session")
def cluster() -> None:
    subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-f", str(BOOTSTRAP)],
        check=True,
        capture_output=True,
        text=True,
    )
    recreate_database("grok_m0_test")
    os.environ["MIGRATION_DATABASE_URL"] = database_url("grok_migrator", "grok_m0_test")
    upgrade(database_url("grok_migrator", "grok_m0_test"))


@pytest.fixture(scope="session")
def migrator_engine(cluster):
    engine = create_engine(database_url("grok_migrator", "grok_m0_test"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app(cluster):
    application = create_app(settings_for("grok_m0_test"), pool_size=5, max_overflow=5)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def fixture_settlement(app):
    settings = app.state.settings
    previous = settings.allow_fixture_ledger_settlement
    settings.allow_fixture_ledger_settlement = True
    yield
    settings.allow_fixture_ledger_settlement = previous


@pytest.fixture
def fixture_scanner(app, tmp_path):
    settings = app.state.settings
    previous_scanner = settings.media_scanner
    previous_root = settings.media_root
    settings.media_scanner = "fixture"
    settings.media_root = str(tmp_path)
    yield
    settings.media_scanner = previous_scanner
    settings.media_root = previous_root


@pytest.fixture
def client(app, migrator_engine):
    with migrator_engine.begin() as conn:
        conn.execute(
            text(
                """
                TRUNCATE idempotency_records, inbox_events, outbox_events, audit_events,
                         contacts, units, properties, role_grants, users, parties, organizations
                CASCADE
                """
            )
        )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def member(client, migrator_engine):
    org_id = uuid4()
    user_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=user_id,
            subject=f"admin-{user_id.hex[:8]}@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
        )
    return {
        "org_id": org_id,
        "user_id": user_id,
        "subject": f"admin-{user_id.hex[:8]}@example.test",
        "password": "local-admin-password",
        "token": login(client, f"admin-{user_id.hex[:8]}@example.test", "local-admin-password"),
    }
