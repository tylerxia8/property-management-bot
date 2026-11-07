#!/bin/bash
# Starts only the grok-property-sample compose project. Does not install runtimes,
# change Docker contexts, delete unrelated images, or reset other projects.
set -euo pipefail
umask 077
cd "$(dirname "$0")"

if [[ ! -x /usr/bin/python3 ]]; then
  echo "This launcher needs /usr/bin/python3. It does not install Python." >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker was not found. Install Docker Desktop for Apple silicon, start it, and run this script again." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop's Linux engine is not running. Start Docker Desktop and wait until it is running. This script does not change Docker contexts, other projects, or other databases." >&2
  exit 1
fi

env_file="${PWD}/.env"
if [[ -e "${env_file}" ]]; then
  echo "Keeping the existing .env. It was not overwritten."
else
  ENV_FILE="${env_file}" /usr/bin/python3 - << 'PY'
import base64
import os
import secrets

alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

def token(length: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(length))

path = os.environ["ENV_FILE"]
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="ascii") as handle:
    handle.write(
        "\n".join(
            [
                f"POSTGRES_PASSWORD={token(32)}",
                f"GROK_APP_PASSWORD={token(32)}",
                f"GROK_MIGRATOR_PASSWORD={token(32)}",
                f"SESSION_SECRET={token(48)}",
                f"CONTACT_ENCRYPTION_KEY={base64.b64encode(secrets.token_bytes(32)).decode()}",
            ]
        )
        + "\n"
    )
PY
fi

docker compose --env-file "${env_file}" --project-name grok-property-sample -f "${PWD}/compose.yaml" up --build -d

ready=0
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:3000/v1/health" >/dev/null; then
    ready=1
    break
  fi
  sleep 5
done
if [[ "${ready}" -ne 1 ]]; then
  echo "http://127.0.0.1:3000/v1/health did not succeed. Run: docker compose --project-name grok-property-sample logs" >&2
  exit 1
fi
echo "Open http://127.0.0.1:3000/"
