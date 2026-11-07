from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from grok_bot.api.app import create_app
from grok_bot.db import set_tenant
from tests.support import seed_member, settings_for


def test_runtime_role_is_not_owner_and_cannot_bypass(client, app):
    with app.state.engine.connect() as conn:
        role = conn.execute(
            text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        owner = conn.execute(
            text(
                """
                SELECT pg_get_userbyid(c.relowner)
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = 'properties'
                """
            )
        ).scalar()
        member_auth = conn.execute(text("SELECT pg_has_role(current_user, 'grok_auth', 'member')")).scalar()
    assert role.current_user == "grok_app"
    assert role.rolsuper is False
    assert role.rolbypassrls is False
    assert owner == "grok_owner"
    assert member_auth is False


def test_rls_hides_other_organization_and_empty_context(migrator_engine, app):
    org_a = uuid4()
    org_b = uuid4()
    with migrator_engine.begin() as conn:
        for org_id, name in ((org_a, "A"), (org_b, "B")):
            conn.execute(
                text("INSERT INTO organizations (id, organization_id, name) VALUES (:id, :id, :name)"),
                {"id": org_id, "name": name},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO properties (
                      id, organization_id, name, address_line1, city, region, postal_code, country_code, timezone
                    ) VALUES (
                      :id, :organization_id, :name, '1 Main', 'Raleigh', 'NC', '27601', 'US', 'America/New_York'
                    )
                    """
                ),
                {"id": uuid4(), "organization_id": org_id, "name": name},
            )
    user_a = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(conn, org_id=org_a, user_id=user_a, subject="staff-a@example.test", password="local-admin-password", roles=["property_manager"])
    with app.state.engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0
        set_tenant(conn, org_a, None)
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0
        set_tenant(conn, org_a, uuid4())
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0
        set_tenant(conn, org_a, user_a)
        names = {row[0] for row in conn.execute(text("SELECT name FROM properties"))}
        assert names == {"A"}


def test_checkout_clears_session_tenant(app, migrator_engine):
    narrow = create_app(settings_for("grok_m0_test"), pool_size=1, max_overflow=0)
    org_id = uuid4()
    property_id = uuid4()
    with migrator_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO organizations (id, organization_id, name) VALUES (:id, :id, 'Leak')"),
            {"id": org_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO properties (
                  id, organization_id, name, address_line1, city, region, postal_code, country_code, timezone
                ) VALUES (
                  :id, :organization_id, 'Hidden', '1 Main', 'Raleigh', 'NC', '27601', 'US', 'America/New_York'
                )
                """
            ),
            {"id": property_id, "organization_id": org_id},
        )
    engine = narrow.state.engine
    with engine.connect() as conn:
        raw = conn.connection.driver_connection
        previous = raw.autocommit
        raw.autocommit = True
        cursor = raw.cursor()
        cursor.execute("SELECT set_config('app.organization_id', %s, false)", (str(org_id),))
        cursor.close()
        raw.autocommit = previous
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0
    engine.dispose()


def test_row_security_off_does_not_reveal_rows(app, migrator_engine):
    org_id = uuid4()
    with migrator_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO organizations (id, organization_id, name) VALUES (:id, :id, 'Force')"),
            {"id": org_id},
        )
    with app.state.engine.begin() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text("SET row_security = off"))
            conn.execute(text("SELECT count(*) FROM organizations")).scalar()


def test_cross_org_foreign_keys_reject(migrator_engine):
    org_a = uuid4()
    org_b = uuid4()
    user_b = uuid4()
    property_b = uuid4()
    party_b = uuid4()
    with migrator_engine.begin() as conn:
        for org_id, name in ((org_a, "A"), (org_b, "B")):
            conn.execute(
                text("INSERT INTO organizations (id, organization_id, name) VALUES (:id, :id, :name)"),
                {"id": org_id, "name": name},
            )
        conn.execute(
            text(
                """
                INSERT INTO users (id, organization_id, issuer, subject, display_name)
                VALUES (:id, :organization_id, 'https://local.invalid/dev-auth', 'other', 'Other')
                """
            ),
            {"id": user_b, "organization_id": org_b},
        )
        conn.execute(
            text(
                """
                INSERT INTO properties (
                  id, organization_id, name, address_line1, city, region, postal_code, country_code, timezone
                ) VALUES (
                  :id, :organization_id, 'B', '1 Main', 'Raleigh', 'NC', '27601', 'US', 'America/New_York'
                )
                """
            ),
            {"id": property_b, "organization_id": org_b},
        )
        conn.execute(
            text(
                """
                INSERT INTO parties (id, organization_id, display_name, kind)
                VALUES (:id, :organization_id, 'Party', 'person')
                """
            ),
            {"id": party_b, "organization_id": org_b},
        )
    with pytest.raises(IntegrityError) as unit_error:
        with migrator_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO units (id, organization_id, property_id, label)
                    VALUES (:id, :organization_id, :property_id, '1')
                    """
                ),
                {"id": uuid4(), "organization_id": org_a, "property_id": property_b},
            )
    with pytest.raises(IntegrityError):
        with migrator_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO role_grants (id, organization_id, user_id, role, active_from)
                    VALUES (:id, :organization_id, :user_id, 'tenant', clock_timestamp())
                    """
                ),
                {"id": uuid4(), "organization_id": org_a, "user_id": user_b},
            )
    with pytest.raises(IntegrityError):
        with migrator_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO contacts (
                      id, organization_id, party_id, kind, ciphertext, nonce, key_version
                    ) VALUES (
                      :id, :organization_id, :party_id, 'email', '\\x00', '\\x01', 1
                    )
                    """
                ),
                {"id": uuid4(), "organization_id": org_a, "party_id": party_b},
            )
    assert "units_property_same_org_fkey" in str(unit_error.value)


def test_app_cannot_read_password_hash_or_create_tables(app):
    with pytest.raises(DBAPIError):
        with app.state.engine.begin() as conn:
            conn.execute(text("SELECT dev_password_hash FROM users"))
    with pytest.raises(DBAPIError):
        with app.state.engine.begin() as conn:
            conn.execute(text("CREATE TABLE public.evil (id integer)"))
    with pytest.raises(DBAPIError):
        with app.state.engine.begin() as conn:
            conn.execute(text("SET ROLE grok_auth"))
