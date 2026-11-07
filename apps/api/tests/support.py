import subprocess
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from grok_bot.auth.constants import LOCAL_DEV_ISSUER
from grok_bot.settings import Settings

API_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = API_ROOT / "scripts" / "bootstrap_roles.sql"
APP_PASSWORD = "grok_m0_app_local_only"
MIGRATOR_PASSWORD = "grok_m0_migrator_local_only"
SESSION_SECRET = "local-only-session-secret-at-least-32-chars"
CONTACT_KEY_RAW = b"m0-contact-key-32-bytes-exactly!"
CONTACT_KEY = __import__("base64").b64encode(CONTACT_KEY_RAW).decode("ascii")
PROPERTY = {
    "name": "Elm Street House",
    "address_line1": "10 Elm Street",
    "address_line2": None,
    "city": "Raleigh",
    "region": "NC",
    "postal_code": "27601",
    "country_code": "US",
    "timezone": "America/New_York",
}


def database_url(role: str, database: str) -> str:
    password = APP_PASSWORD if role == "grok_app" else MIGRATOR_PASSWORD
    return f"postgresql+psycopg://{role}:{password}@127.0.0.1:5432/{database}"


def psql(sql: str, database: str = "postgres") -> None:
    subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", database, "-v", "ON_ERROR_STOP=1", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )


def recreate_database(name: str) -> None:
    psql(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{name}' AND pid <> pg_backend_pid()"
    )
    psql(f"DROP DATABASE IF EXISTS {name}")
    psql(f"CREATE DATABASE {name} OWNER grok_owner")
    psql(f"GRANT CONNECT ON DATABASE {name} TO grok_app")


def settings_for(database: str, app_env: str = "test") -> Settings:
    return Settings(
        app_env=app_env,
        database_url=database_url("grok_app", database),
        migration_database_url=database_url("grok_migrator", database),
        session_secret=SESSION_SECRET,
        contact_encryption_key=CONTACT_KEY,
    )


def seed_member(
    conn,
    *,
    org_id: UUID,
    user_id: UUID,
    subject: str,
    password: str,
    roles: list[str],
    org_name: str | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    active_until: str | None = None,
    active_from: str | None = None,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO organizations (id, organization_id, name)
            VALUES (:id, :id, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": org_id, "name": org_name or f"Org {org_id.hex[:8]}"},
    )
    conn.execute(
        text(
            """
            INSERT INTO users (
              id, organization_id, issuer, subject, display_name, dev_password_hash
            ) VALUES (
              :id, :organization_id, :issuer, :subject, :display_name, crypt(:password, gen_salt('bf'))
            )
            """
        ),
        {
            "id": user_id,
            "organization_id": org_id,
            "issuer": LOCAL_DEV_ISSUER,
            "subject": subject,
            "display_name": subject,
            "password": password,
        },
    )
    for role in roles:
        conn.execute(
            text(
                """
                INSERT INTO role_grants (
                  id, organization_id, user_id, role, resource_type, resource_id, active_from, active_until
                ) VALUES (
                  :id, :organization_id, :user_id, :role, :resource_type, :resource_id,
                  COALESCE(CAST(:active_from AS timestamptz), clock_timestamp() - interval '1 minute'),
                  CAST(:active_until AS timestamptz)
                )
                """
            ),
            {
                "id": uuid4(),
                "organization_id": org_id,
                "user_id": user_id,
                "role": role,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "active_until": active_until,
                "active_from": active_from,
            },
        )


def login(client: TestClient, subject: str, password: str) -> str:
    response = client.post("/v1/auth/local/login", json={"subject": subject, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
