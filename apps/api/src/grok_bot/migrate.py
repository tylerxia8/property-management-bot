import os
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]


def upgrade(url: str) -> None:
    os.environ["MIGRATION_DATABASE_URL"] = url
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


def downgrade(url: str) -> None:
    os.environ["MIGRATION_DATABASE_URL"] = url
    os.environ["ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
    command.downgrade(Config(str(ROOT / "alembic.ini")), "base")
