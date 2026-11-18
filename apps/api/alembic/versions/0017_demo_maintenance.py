from pathlib import Path

from alembic import op
from psycopg import ClientCursor

revision = "0017_demo_maintenance"
down_revision = "0016_maintenance_workflow"
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).resolve().parents[1] / "sql" / "0009_demo_sample_up.sql").read_text(encoding="utf-8-sig")
    sql = sql.replace("'prospect', 'owner'", "'prospect', 'owner', 'contractor'")
    with ClientCursor(op.get_bind().connection.driver_connection) as cursor:
        cursor.execute(sql)


def downgrade():
    with ClientCursor(op.get_bind().connection.driver_connection) as cursor:
        cursor.execute((Path(__file__).resolve().parents[1] / "sql" / "0009_demo_sample_up.sql").read_text(encoding="utf-8-sig"))
