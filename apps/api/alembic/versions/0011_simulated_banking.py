from pathlib import Path

from alembic import op
from psycopg import ClientCursor

revision = "0011_simulated_banking"
down_revision = "0010_maintenance_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    script = (Path(__file__).resolve().parents[1] / "sql" / "0011_simulated_banking_up.sql").read_text(encoding="utf-8")
    with ClientCursor(op.get_bind().connection.driver_connection) as cursor:
        cursor.execute(script)


def downgrade() -> None:
    script = (Path(__file__).resolve().parents[1] / "sql" / "0011_simulated_banking_down.sql").read_text(encoding="utf-8")
    with ClientCursor(op.get_bind().connection.driver_connection) as cursor:
        cursor.execute(script)
