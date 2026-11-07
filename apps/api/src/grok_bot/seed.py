"""Seed a local dev or e2e database. Refuses production and unfamiliar database names."""

import os
from uuid import UUID
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

from grok_bot.auth.constants import LOCAL_DEV_ISSUER

E2E_ORG = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
E2E_ADMIN = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")
E2E_MANAGER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3")
E2E_ACCOUNTING = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4")
E2E_TENANT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa5")
E2E_PROPERTY = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa6")
E2E_UNIT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa7")
E2E_PAYER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa8")
E2E_LEASE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa9")


def seed_e2e(migration_database_url: str, app_env: str) -> None:
    if app_env not in {"development", "test"}:
        raise SystemExit("seed refuses to run unless APP_ENV is development or test")
    name = urlparse(migration_database_url).path.rsplit("/", 1)[-1]
    if not name.endswith(("_dev", "_test", "_e2e")):
        raise SystemExit("seed refuses this database name")
    engine = create_engine(migration_database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                TRUNCATE idempotency_records, inbox_events, outbox_events, audit_events,
                         contacts, units, properties, role_grants, users, parties, organizations
                CASCADE
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO organizations (id, organization_id, name, settings)
                VALUES (:id, :id, 'Harbor North', '{}'::jsonb)
                """
            ),
            {"id": E2E_ORG},
        )
        _user(conn, E2E_ADMIN, "Ada Admin", "admin@example.test", "local-admin-password")
        _user(conn, E2E_MANAGER, "Morgan Manager", "manager@example.test", "local-manager-password")
        _user(conn, E2E_ACCOUNTING, "Casey Accounting", "accounting@example.test", "local-accounting-password")
        _user(conn, E2E_TENANT, "Taylor Tenant", "tenant@example.test", "local-tenant-password")
        _grant(conn, E2E_ADMIN, "organization_administrator")
        _grant(conn, E2E_MANAGER, "property_manager")
        _grant(conn, E2E_ACCOUNTING, "accounting_staff")
        _grant(conn, E2E_TENANT, "tenant")
        conn.execute(
            text(
                """
                INSERT INTO properties (
                  id, organization_id, name, address_line1, city, region, postal_code,
                  country_code, timezone, created_by
                ) VALUES (
                  :id, :organization_id, 'Elm Street House', '10 Elm Street', 'Raleigh', 'NC',
                  '27601', 'US', 'America/New_York', :created_by
                )
                """
            ),
            {"id": E2E_PROPERTY, "organization_id": E2E_ORG, "created_by": E2E_ADMIN},
        )
        conn.execute(
            text(
                """
                INSERT INTO units (id, organization_id, property_id, label)
                VALUES (:id, :organization_id, :property_id, '1')
                """
            ),
            {"id": E2E_UNIT, "organization_id": E2E_ORG, "property_id": E2E_PROPERTY},
        )
        conn.execute(
            text(
                """
                INSERT INTO parties (id, organization_id, display_name, kind)
                VALUES (:id, :organization_id, 'Elm Tenant', 'person')
                """
            ),
            {"id": E2E_PAYER, "organization_id": E2E_ORG},
        )
        conn.execute(
            text(
                """
                INSERT INTO leases (
                  id, organization_id, unit_id, start_date, end_date, agreed_rent_cents
                ) VALUES (
                  :id, :organization_id, :unit_id, '2026-01-01', '2027-01-01', 150000
                )
                """
            ),
            {"id": E2E_LEASE, "organization_id": E2E_ORG, "unit_id": E2E_UNIT},
        )
        conn.execute(
            text(
                """
                INSERT INTO lease_parties (id, organization_id, lease_id, user_id)
                VALUES (:id, :organization_id, :lease_id, :user_id)
                """
            ),
            {
                "id": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab"),
                "organization_id": E2E_ORG,
                "lease_id": E2E_LEASE,
                "user_id": E2E_TENANT,
            },
        )
    engine.dispose()


def _user(conn, user_id: UUID, display_name: str, subject: str, password: str) -> None:
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
            "organization_id": E2E_ORG,
            "issuer": LOCAL_DEV_ISSUER,
            "subject": subject,
            "display_name": display_name,
            "password": password,
        },
    )


def _grant(conn, user_id: UUID, role: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO role_grants (id, organization_id, user_id, role, active_from)
            VALUES (gen_random_uuid(), :organization_id, :user_id, :role, clock_timestamp())
            """
        ),
        {"organization_id": E2E_ORG, "user_id": user_id, "role": role},
    )


if __name__ == "__main__":
    seed_e2e(os.environ["MIGRATION_DATABASE_URL"], os.environ.get("APP_ENV", "production"))
