"""Resident maintenance workspace persistence and narrowly scoped home labels."""

from pathlib import Path
from alembic import op
from psycopg import ClientCursor

revision = "0010_maintenance_workspace"
down_revision = "0009_demo_sample"
branch_labels = None
depends_on = None


def upgrade():
    with ClientCursor(op.get_bind().connection.driver_connection) as cursor:
        cursor.execute(
            (
                Path(__file__).resolve().parents[1] / "sql" / "0010_maintenance_up.sql"
            ).read_text(encoding="utf-8-sig")
        )


def downgrade():
    op.execute(
        "DROP TABLE public.maintenance_status_updates; DROP TABLE public.maintenance_report_keys; DROP FUNCTION public.app_maintenance_homes()"
    )
    op.execute(
        "REVOKE SELECT ON public.leases, public.units, public.properties, public.lease_parties FROM grok_auth"
    )
