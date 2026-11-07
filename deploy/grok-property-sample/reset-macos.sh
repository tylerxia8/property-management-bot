#!/bin/bash
# Destructive for this sample project only. Deletes grok-property-sample containers
# and the grok-property-sample-pg volume, then starts again. Does not prune Docker
# or change other projects. The existing .env is kept.
set -euo pipefail
cd "$(dirname "$0")"
env_file="${PWD}/.env"
if [[ ! -f "${env_file}" ]]; then
  echo "No .env is present. Refusing to reset without the local secret file." >&2
  exit 1
fi
echo "This deletes only the grok-property-sample containers and volume."
docker compose --env-file "${env_file}" --project-name grok-property-sample -f "${PWD}/compose.yaml" down -v --remove-orphans
exec /bin/bash "${PWD}/start-macos.sh"
