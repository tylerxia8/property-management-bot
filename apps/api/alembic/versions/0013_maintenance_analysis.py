from pathlib import Path

from alembic import op
from psycopg import ClientCursor

revision = "0013_maintenance_analysis"
down_revision = "0012_stripe_sandbox"
branch_labels = None
depends_on = None


def upgrade():
    with ClientCursor(op.get_bind().connection.driver_connection) as cursor:
        cursor.execute((Path(__file__).resolve().parents[1] / "sql" / "0013_maintenance_analysis_up.sql").read_text(encoding="utf-8-sig"))


def downgrade():
    op.execute("DROP TABLE public.maintenance_analyses")
