from pathlib import Path

from alembic import op
from psycopg import ClientCursor

revision = "0012_stripe_sandbox"
down_revision = "0011_simulated_banking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with ClientCursor(op.get_bind().connection.driver_connection) as cursor:
        cursor.execute((Path(__file__).resolve().parents[1] / "sql" / "0012_stripe_up.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    with ClientCursor(op.get_bind().connection.driver_connection) as cursor:
        cursor.execute((Path(__file__).resolve().parents[1] / "sql" / "0012_stripe_down.sql").read_text(encoding="utf-8"))
