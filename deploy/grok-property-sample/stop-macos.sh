#!/bin/bash
# Stops only grok-property-sample. Keeps its volume and does not delete .env.
set -euo pipefail
cd "$(dirname "$0")"
env_file="${PWD}/.env"
if [[ ! -f "${env_file}" ]]; then
  echo "No .env is present. Refusing to guess secrets or touch other Docker projects." >&2
  exit 1
fi
docker compose --env-file "${env_file}" --project-name grok-property-sample -f "${PWD}/compose.yaml" down
echo "Stopped grok-property-sample. The sample volume and .env were kept."
