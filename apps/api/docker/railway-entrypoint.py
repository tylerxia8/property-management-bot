"""Bootstrap the dedicated Railway fictional demo, then use the usual launcher."""

import os
import subprocess
import sys


def main():
    if os.environ.get("APP_ENV") != "test" or os.environ.get("DEMO_FIXTURE") != "sample":
        raise SystemExit("Railway demo bootstrap requires APP_ENV=test and DEMO_FIXTURE=sample")
    env = os.environ.copy()
    # psql accepts the URL through its environment; never print credentials.
    env["PGDATABASE"] = env.pop("DEMO_BOOTSTRAP_DATABASE_URL")
    subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-v", "app_password=" + env["GROK_APP_PASSWORD"],
         "-v", "migrator_password=" + env["GROK_MIGRATOR_PASSWORD"],
         "-f", "/app/scripts/bootstrap_demo_sample.sql"],
        env=env, check=True,
    )
    os.execv(sys.executable, [sys.executable, "/app/docker/entrypoint.py"])


if __name__ == "__main__":
    main()
