"""Wait for Postgres, migrate, seed an empty demo database, then serve the API."""

import os
import subprocess
import sys
import time

from sqlalchemy import create_engine, text

from grok_bot.seed import seed_demo


def _wait() -> None:
    url = os.environ["MIGRATION_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    import psycopg

    for _ in range(60):
        try:
            psycopg.connect(url, connect_timeout=3).close()
            return
        except Exception:
            time.sleep(1)
    raise SystemExit("grok_demo_sample did not become ready")


def main() -> None:
    _wait()
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd="/app")
    url = os.environ["MIGRATION_DATABASE_URL"]
    engine = create_engine(url)
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT count(*) FROM organizations")).scalar()
    engine.dispose()
    if int(existing or 0) == 0:
        seed_demo(url, os.environ.get("APP_ENV", "production"), os.environ["SESSION_SECRET"])
    os.execvp(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "grok_bot.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
