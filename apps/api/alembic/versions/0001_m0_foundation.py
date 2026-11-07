"""M0 foundation schema, RLS, and composite foreign keys."""

from pathlib import Path

from alembic import op
from psycopg import ClientCursor

revision = "0001_m0_foundation"
down_revision = None
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _execute_script(filename: str) -> None:
    connection = op.get_bind()
    raw = connection.connection.driver_connection
    script = (SQL_DIR / filename).read_text(encoding="utf-8")
    with ClientCursor(raw) as cursor:
        cursor.execute(script)


def upgrade() -> None:
    _execute_script("0001_m0_up.sql")


def downgrade() -> None:
    _execute_script("0001_m0_down.sql")
