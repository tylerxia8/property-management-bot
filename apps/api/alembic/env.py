import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required for Alembic")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _refuse_unmarked_downgrade() -> None:
    # ``head`` is resolved to a revision id before this runs. ``base`` is None.
    destination = context.get_revision_argument()
    downgrading = "downgrade" in " ".join(sys.argv) or destination is None
    if downgrading and os.environ.get("ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Downgrade refused. Set ALLOW_DESTRUCTIVE_DOWNGRADE=1. "
            "Downgrade can drop ledger, distribution, and audit tables."
        )


def run_migrations_online() -> None:
    _refuse_unmarked_downgrade()
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
