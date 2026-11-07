"""Seed a local dev or e2e database. Refuses production and unfamiliar database names."""

import os
import secrets
from datetime import date, datetime, timezone
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
E2E_PROSPECT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaac")
E2E_VACANT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaad")
E2E_LISTING = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaae")
E2E_RESOURCE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaf")
E2E_POLICY = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab0")
E2E_SCHEDULE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab1")
E2E_OWNER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab2")
E2E_OTHER_OWNER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab3")
E2E_OWNER_PARTY = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab4")
E2E_OTHER_PARTY = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab5")
E2E_BANK = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab6")
E2E_LOT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab7")
E2E_FIXTURE_SOURCE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab8")
# Browser fixture only. Not an opening balance, a fee, or a production distribution rule.
E2E_FIXTURE_CENTS = 25_000


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
        _user(conn, E2E_PROSPECT, "Parker Prospect", "prospect@example.test", "local-prospect-password")
        _grant(conn, E2E_ADMIN, "organization_administrator")
        _grant(conn, E2E_MANAGER, "property_manager")
        _grant(conn, E2E_ACCOUNTING, "accounting_staff")
        _grant(conn, E2E_TENANT, "tenant")
        _grant(conn, E2E_PROSPECT, "prospect")
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
        conn.execute(
            text(
                """
                INSERT INTO units (id, organization_id, property_id, label)
                VALUES (:id, :organization_id, :property_id, 'Vacant')
                """
            ),
            {"id": E2E_VACANT, "organization_id": E2E_ORG, "property_id": E2E_PROPERTY},
        )
        conn.execute(
            text(
                """
                INSERT INTO listings (
                  id, organization_id, property_id, unit_id, external_source, external_listing_id,
                  display_label, asking_rent_cents
                ) VALUES (
                  :id, :organization_id, :property_id, :unit_id, 'zillow', 'zillow-elm',
                  'Elm Street listing', 100000
                )
                """
            ),
            {"id": E2E_LISTING, "organization_id": E2E_ORG, "property_id": E2E_PROPERTY, "unit_id": E2E_VACANT},
        )
        conn.execute(
            text(
                """
                INSERT INTO screening_policies (
                  id, organization_id, property_id, version, status, fixture, legal_review_reference,
                  review_reason, reviewed_by, effective_at, rules, missing_action, accommodation_action,
                  automatic_final_denial
                ) VALUES (
                  :id, :organization_id, :property_id, 1, 'REVIEWED_ACTIVE', true,
                  'fixture:illustrative-not-a-requirement',
                  'Browser fixture only. Not a real rental requirement.',
                  :reviewed_by, '2026-01-01T00:00:00Z',
                  CAST(:rules AS jsonb),
                  'NEEDS_INFORMATION', 'HUMAN_REVIEW', false
                )
                """
            ),
            {
                "id": E2E_POLICY,
                "organization_id": E2E_ORG,
                "property_id": E2E_PROPERTY,
                "reviewed_by": E2E_MANAGER,
                "rules": '[{"id":"income","field":"household_income_monthly_cents","operator":"gte_rent_multiple","ratio_numerator":3,"ratio_denominator":1,"failure_action":"HUMAN_REVIEW"}]',
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO schedule_configs (
                  id, organization_id, property_id, duration_minutes, buffer_minutes, hold_minutes,
                  min_notice_minutes, day_start, day_end, open_weekdays, timezone, fixture, label
                ) VALUES (
                  :id, :organization_id, :property_id, 30, 15, 5, 0, '09:00', '17:00',
                  '{1,2,3,4,5,6,7}', 'America/New_York', true, 'fixture:prd-proposed-30-15-5'
                )
                """
            ),
            {"id": E2E_SCHEDULE, "organization_id": E2E_ORG, "property_id": E2E_PROPERTY},
        )
        conn.execute(
            text(
                """
                INSERT INTO scheduling_resources (id, organization_id, property_id, kind, display_name)
                VALUES (:id, :organization_id, :property_id, 'AGENT', 'Tour agent')
                """
            ),
            {"id": E2E_RESOURCE, "organization_id": E2E_ORG, "property_id": E2E_PROPERTY},
        )
        _user(conn, E2E_OWNER, "Olive Owner", "owner@example.test", "local-owner-password")
        _user(conn, E2E_OTHER_OWNER, "Owen Other", "other-owner@example.test", "local-owner-password")
        _grant(conn, E2E_OWNER, "owner")
        _grant(conn, E2E_OTHER_OWNER, "owner")
        conn.execute(
            text(
                """
                INSERT INTO parties (id, organization_id, display_name, kind)
                VALUES (:owner_id, :organization_id, 'Elm Owner', 'person'),
                       (:other_id, :organization_id, 'Other Owner', 'person')
                """
            ),
            {"owner_id": E2E_OWNER_PARTY, "other_id": E2E_OTHER_PARTY, "organization_id": E2E_ORG},
        )
        conn.execute(
            text(
                """
                INSERT INTO owner_links (id, organization_id, user_id, party_id)
                VALUES (:owner_link, :organization_id, :owner_user, :owner_party),
                       (:other_link, :organization_id, :other_user, :other_party)
                """
            ),
            {
                "owner_link": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaab9"),
                "other_link": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaba"),
                "organization_id": E2E_ORG,
                "owner_user": E2E_OWNER,
                "owner_party": E2E_OWNER_PARTY,
                "other_user": E2E_OTHER_OWNER,
                "other_party": E2E_OTHER_PARTY,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO bank_accounts (id, organization_id, display_name, masked_label)
                VALUES (:id, :organization_id, 'Fixture trust', '****1000')
                """
            ),
            {"id": E2E_BANK, "organization_id": E2E_ORG},
        )
    _seed_browser_fixture(engine)
    engine.dispose()


def _seed_browser_fixture(engine) -> None:
    """Post one labeled cash-and-owner pair so the browser can draft a batch.

    The amount is a fixture for the approval and export screens. It is not an
    opening balance and it does not settle anything.
    """
    from datetime import date

    from sqlalchemy.orm import Session

    from grok_bot.db import set_tenant
    from grok_bot.domain.accounting import _line, _owner_line, _post
    from grok_bot.domain.distributions import issue_statement

    with Session(engine) as session:
        set_tenant(session, E2E_ORG, E2E_ACCOUNTING)
        session.execute(text("SELECT app_ensure_proposed_chart(:organization_id)"), {"organization_id": E2E_ORG})
        source = {"property_id": E2E_PROPERTY, "lease_id": None}
        _post(
            session,
            E2E_ORG,
            "FIXTURE_BROWSER_AVAILABLE",
            E2E_FIXTURE_SOURCE,
            date(2026, 11, 1),
            [
                _line("1030", "DEBIT", E2E_FIXTURE_CENTS, source, "RENT", E2E_BANK),
                _owner_line("2020", "CREDIT", E2E_FIXTURE_CENTS, source, E2E_OWNER_PARTY),
            ],
        )
        session.execute(
            text(
                """
                INSERT INTO funding_lots (
                  id, organization_id, property_id, bank_account_id, purpose,
                  amount_cents, source_type, source_id
                ) VALUES (
                  :id, :organization_id, :property_id, :bank_account_id, 'RENT',
                  :amount_cents, 'FIXTURE_BROWSER', :source_id
                )
                """
            ),
            {
                "id": E2E_LOT,
                "organization_id": E2E_ORG,
                "property_id": E2E_PROPERTY,
                "bank_account_id": E2E_BANK,
                "amount_cents": E2E_FIXTURE_CENTS,
                "source_id": E2E_FIXTURE_SOURCE,
            },
        )
        issue_statement(
            session,
            E2E_ORG,
            E2E_PROPERTY,
            E2E_OWNER_PARTY,
            date(2026, 11, 1),
            date(2026, 11, 30),
            "Browser fixture snapshot. Not a bank statement.",
        )
        session.commit()


def _user(conn, user_id: UUID, display_name: str, subject: str, password: str, organization_id: UUID = E2E_ORG) -> None:
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
            "organization_id": organization_id,
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


DEMO_ORG = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1")
DEMO_ADMIN = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
DEMO_MANAGER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb3")
DEMO_ACCOUNTING = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb4")
DEMO_TENANT = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb5")
DEMO_PROSPECT = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb6")
DEMO_OWNER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb7")
DEMO_PROPERTY = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb8")
DEMO_UNIT = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb9")
DEMO_VACANT = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbba")
DEMO_PAYER = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DEMO_LEASE = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbc")
DEMO_LISTING = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbd")
DEMO_OWNER_PARTY = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbe")
DEMO_BANK = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbf")
DEMO_DATABASE = "grok_demo_sample"


def seed_demo(migration_database_url: str, app_env: str, session_secret: str) -> None:
    """Load fictional fixture rows into grok_demo_sample only.

    Passwords are random and discarded. The demo session route does not use them.
    Rates, the screening ratio, and the tour schedule are fixture-labeled.
    """
    if app_env not in {"development", "test"}:
        raise SystemExit("demo seed refuses to run unless APP_ENV is development or test")
    name = urlparse(migration_database_url).path.rsplit("/", 1)[-1]
    if name != DEMO_DATABASE:
        raise SystemExit("demo seed refuses every database except grok_demo_sample")
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
                VALUES (
                  :id, :id, 'Fixture Sample Co',
                  CAST(:settings AS jsonb)
                )
                """
            ),
            {
                "id": DEMO_ORG,
                "settings": '{"demo":"fixture-sample","outbound":{"messaging_enabled":false,"calendar_enabled":false,"payment_enabled":false}}',
            },
        )
        _demo_user(conn, DEMO_ADMIN, "Fixture Admin", "fixture-admin@example.test")
        _demo_user(conn, DEMO_MANAGER, "Fixture Manager", "fixture-manager@example.test")
        _demo_user(conn, DEMO_ACCOUNTING, "Fixture Accounting", "fixture-accounting@example.test")
        _demo_user(conn, DEMO_TENANT, "Fixture Tenant", "fixture-tenant@example.test")
        _demo_user(conn, DEMO_PROSPECT, "Fixture Prospect", "fixture-prospect@example.test")
        _demo_user(conn, DEMO_OWNER, "Fixture Owner", "fixture-owner@example.test")
        for user_id, role in (
            (DEMO_ADMIN, "organization_administrator"),
            (DEMO_MANAGER, "property_manager"),
            (DEMO_ACCOUNTING, "accounting_staff"),
            (DEMO_TENANT, "tenant"),
            (DEMO_PROSPECT, "prospect"),
            (DEMO_OWNER, "owner"),
        ):
            _grant_org(conn, user_id, role)
        conn.execute(
            text(
                """
                INSERT INTO properties (
                  id, organization_id, name, address_line1, city, region, postal_code,
                  country_code, timezone, created_by
                ) VALUES (
                  :id, :organization_id, 'Cedar Fixture House', '100 Fixture Lane', 'Sampletown', 'NC',
                  '00000', 'US', 'America/New_York', :created_by
                )
                """
            ),
            {"id": DEMO_PROPERTY, "organization_id": DEMO_ORG, "created_by": DEMO_ADMIN},
        )
        conn.execute(
            text(
                """
                INSERT INTO units (id, organization_id, property_id, label)
                VALUES (:occupied, :organization_id, :property_id, 'Fixture A'),
                       (:vacant, :organization_id, :property_id, 'Fixture Vacant')
                """
            ),
            {
                "occupied": DEMO_UNIT,
                "vacant": DEMO_VACANT,
                "organization_id": DEMO_ORG,
                "property_id": DEMO_PROPERTY,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO parties (id, organization_id, display_name, kind)
                VALUES (:payer, :organization_id, 'Fixture Payer', 'person'),
                       (:owner, :organization_id, 'Fixture Owner Party', 'person')
                """
            ),
            {"payer": DEMO_PAYER, "owner": DEMO_OWNER_PARTY, "organization_id": DEMO_ORG},
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
            {"id": DEMO_LEASE, "organization_id": DEMO_ORG, "unit_id": DEMO_UNIT},
        )
        conn.execute(
            text(
                """
                INSERT INTO lease_parties (id, organization_id, lease_id, user_id)
                VALUES (gen_random_uuid(), :organization_id, :lease_id, :user_id)
                """
            ),
            {"organization_id": DEMO_ORG, "lease_id": DEMO_LEASE, "user_id": DEMO_TENANT},
        )
        conn.execute(
            text(
                """
                INSERT INTO listings (
                  id, organization_id, property_id, unit_id, external_source, external_listing_id,
                  display_label, asking_rent_cents
                ) VALUES (
                  :id, :organization_id, :property_id, :unit_id, 'fixture', 'fixture-cedar',
                  'fixture: Cedar vacant unit', 200000
                )
                """
            ),
            {
                "id": DEMO_LISTING,
                "organization_id": DEMO_ORG,
                "property_id": DEMO_PROPERTY,
                "unit_id": DEMO_VACANT,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO screening_policies (
                  id, organization_id, property_id, version, status, fixture, legal_review_reference,
                  review_reason, reviewed_by, effective_at, rules, missing_action, accommodation_action,
                  automatic_final_denial
                ) VALUES (
                  gen_random_uuid(), :organization_id, :property_id, 1, 'REVIEWED_ACTIVE', true,
                  'fixture:illustrative-3x-not-a-requirement',
                  'Fixture sample only. Not a rental requirement.',
                  :reviewed_by, '2026-01-01T00:00:00Z',
                  CAST(:rules AS jsonb),
                  'NEEDS_INFORMATION', 'HUMAN_REVIEW', false
                )
                """
            ),
            {
                "organization_id": DEMO_ORG,
                "property_id": DEMO_PROPERTY,
                "reviewed_by": DEMO_MANAGER,
                "rules": '[{"id":"fixture-income","field":"household_income_monthly_cents","operator":"gte_rent_multiple","ratio_numerator":3,"ratio_denominator":1,"failure_action":"HUMAN_REVIEW"}]',
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO schedule_configs (
                  id, organization_id, property_id, duration_minutes, buffer_minutes, hold_minutes,
                  min_notice_minutes, day_start, day_end, open_weekdays, timezone, fixture, label
                ) VALUES (
                  gen_random_uuid(), :organization_id, :property_id, 30, 15, 5, 0, '09:00', '17:00',
                  '{1,2,3,4,5,6,7}', 'America/New_York', true, 'fixture:sample-30-15-5'
                )
                """
            ),
            {"organization_id": DEMO_ORG, "property_id": DEMO_PROPERTY},
        )
        conn.execute(
            text(
                """
                INSERT INTO scheduling_resources (id, organization_id, property_id, kind, display_name)
                VALUES (gen_random_uuid(), :organization_id, :property_id, 'AGENT', 'Fixture tour agent')
                """
            ),
            {"organization_id": DEMO_ORG, "property_id": DEMO_PROPERTY},
        )
        conn.execute(
            text(
                """
                INSERT INTO owner_links (id, organization_id, user_id, party_id)
                VALUES (gen_random_uuid(), :organization_id, :user_id, :party_id)
                """
            ),
            {"organization_id": DEMO_ORG, "user_id": DEMO_OWNER, "party_id": DEMO_OWNER_PARTY},
        )
        conn.execute(
            text(
                """
                INSERT INTO bank_accounts (id, organization_id, display_name, masked_label)
                VALUES (:id, :organization_id, 'Fixture trust', '****0000')
                """
            ),
            {"id": DEMO_BANK, "organization_id": DEMO_ORG},
        )
    _seed_demo_activity(engine, session_secret)
    engine.dispose()


def _seed_demo_activity(engine, session_secret: str) -> None:
    from sqlalchemy.orm import Session

    from grok_bot.db import set_tenant
    from grok_bot.domain.accounting import create_receipt
    from grok_bot.domain.maintenance import create_verified_ticket
    from grok_bot.domain.screening import ensure_prospect

    when = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        set_tenant(session, DEMO_ORG, DEMO_ACCOUNTING)
        session.execute(text("SELECT app_ensure_proposed_chart(:organization_id)"), {"organization_id": DEMO_ORG})
        create_receipt(
            session,
            DEMO_ORG,
            DEMO_ACCOUNTING,
            {
                "property_id": DEMO_PROPERTY,
                "unit_id": DEMO_UNIT,
                "lease_id": DEMO_LEASE,
                "payer_party_id": DEMO_PAYER,
                "method": "CHECK",
                "amount_cents": 180_000,
                "currency": "USD",
                "received_at": when,
                "posting_date": date(2026, 11, 7),
                "reference": "fixture-check-not-available",
                "service_period": "2026-11",
            },
            "demo-seed",
        )
        set_tenant(session, DEMO_ORG, DEMO_TENANT)
        create_verified_ticket(
            session,
            DEMO_ORG,
            DEMO_TENANT,
            {"description": "Fixture drip under the sink. Location was not provided."},
            session_secret,
            when,
        )
        create_verified_ticket(
            session,
            DEMO_ORG,
            DEMO_TENANT,
            {"description": "Fixture sample: I smell gas near the stove."},
            session_secret,
            when,
        )
        set_tenant(session, DEMO_ORG, DEMO_PROSPECT)
        ensure_prospect(session, DEMO_ORG, DEMO_PROSPECT, DEMO_LISTING)
        session.commit()


def _demo_user(conn, user_id: UUID, display_name: str, subject: str) -> None:
    _user(conn, user_id, display_name, subject, secrets.token_urlsafe(24), DEMO_ORG)


def _grant_org(conn, user_id: UUID, role: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO role_grants (id, organization_id, user_id, role, active_from)
            VALUES (gen_random_uuid(), :organization_id, :user_id, :role, clock_timestamp())
            """
        ),
        {"organization_id": DEMO_ORG, "user_id": user_id, "role": role},
    )


if __name__ == "__main__":
    seed_e2e(os.environ["MIGRATION_DATABASE_URL"], os.environ.get("APP_ENV", "production"))
