"""Bootstrap the dedicated Railway fictional demo, then use the usual launcher."""

import os
import subprocess
import sys
from urllib.parse import unquote, urlparse


def main():
    if os.environ.get("APP_ENV") != "test" or os.environ.get("DEMO_FIXTURE") != "sample":
        raise SystemExit("Railway demo bootstrap requires APP_ENV=test and DEMO_FIXTURE=sample")
    env = os.environ.copy()
    # Pass libpq fields in the environment; never print a connection URL.
    url = urlparse(env.pop("DEMO_BOOTSTRAP_DATABASE_URL"))
    if url.scheme not in {"postgres", "postgresql"} or not url.hostname:
        raise SystemExit("Invalid demo bootstrap database configuration")
    env.update(PGHOST=url.hostname, PGPORT=str(url.port or 5432),
               PGUSER=unquote(url.username or "postgres"),
               PGPASSWORD=unquote(url.password or ""),
               PGDATABASE=unquote(url.path.lstrip("/")))
    result = subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-v", "app_password=" + env["GROK_APP_PASSWORD"],
         "-v", "migrator_password=" + env["GROK_MIGRATOR_PASSWORD"],
         "-f", "/app/scripts/bootstrap_demo_sample.sql"],
        env=env, check=False,
    )
    if result.returncode:
        # CalledProcessError would include the command's password arguments.
        raise SystemExit("Railway demo database bootstrap failed")
    os.execv(sys.executable, [sys.executable, "/app/docker/entrypoint.py"])


if __name__ == "__main__":
    main()
