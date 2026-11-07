from sqlalchemy import create_engine, text

from uuid import UUID, uuid4

from grok_bot.migrate import downgrade, upgrade
from tests.support import database_url, recreate_database, seed_member


def test_migration_up_down_up(cluster):
    recreate_database("grok_m0_migration")
    url = database_url("grok_migrator", "grok_m0_migration")
    app_url = database_url("grok_app", "grok_m0_migration")
    upgrade(url)
    migrator = create_engine(url)
    with migrator.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.properties')")).scalar() == "properties"
        floats = conn.execute(
            text(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_schema = 'public' AND data_type IN ('double precision', 'real')
                """
            )
        ).scalar()
        assert floats == 0
    downgrade(url)
    with migrator.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.properties')")).scalar() is None
    upgrade(url)
    with migrator.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.properties')")).scalar() == "properties"
        conn.commit()
        conn.execute(
            text(
                """
                INSERT INTO organizations (id, organization_id, name)
                VALUES ('11111111-1111-4111-8111-111111111111', '11111111-1111-4111-8111-111111111111', 'After upgrade')
                """
            )
        )
        conn.commit()
        user_id = uuid4()
        seed_member(
            conn,
            org_id=UUID("11111111-1111-4111-8111-111111111111"),
            user_id=user_id,
            subject="after@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
        )
        conn.commit()
    app = create_engine(app_url)
    with app.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.organization_id', '11111111-1111-4111-8111-111111111111', true)")
        )
        assert conn.execute(text("SELECT count(*) FROM organizations")).scalar() == 0
        conn.execute(
            text(
                "SELECT set_config('app.organization_id', '11111111-1111-4111-8111-111111111111', true), "
                "set_config('app.actor_id', :actor, true)"
            ),
            {"actor": str(user_id)},
        )
        seen = conn.execute(text("SELECT name FROM organizations")).scalar()
        assert seen == "After upgrade"
    app.dispose()
    migrator.dispose()
