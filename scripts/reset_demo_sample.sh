#!/usr/bin/env bash
# Recreate only grok_demo_sample. Does not drop grok_m0_test, grok_m0_e2e, or grok_m0_migration.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="$ROOT/apps/api"
NAME="grok_demo_sample"

if [[ "${APP_ENV:-test}" == "production" ]]; then
  echo "demo reset refuses APP_ENV=production" >&2
  exit 1
fi

sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${NAME}' AND pid <> pg_backend_pid()" >/dev/null
sudo -u postgres dropdb --if-exists "$NAME"
sudo -u postgres createdb "$NAME" --owner grok_owner
sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "GRANT CONNECT ON DATABASE ${NAME} TO grok_app"

export APP_ENV="${APP_ENV:-test}"
export MIGRATION_DATABASE_URL="postgresql+psycopg://grok_migrator:grok_m0_migrator_local_only@127.0.0.1:5432/${NAME}"
export DATABASE_URL="postgresql+psycopg://grok_app:grok_m0_app_local_only@127.0.0.1:5432/${NAME}"
export SESSION_SECRET="${SESSION_SECRET:-local-only-session-secret-at-least-32-chars}"
export CONTACT_ENCRYPTION_KEY="${CONTACT_ENCRYPTION_KEY:-$(python3 -c 'import base64; print(base64.b64encode(b"m0-contact-key-32-bytes-exactly!").decode())')}"

(
  cd "$API"
  .venv/bin/alembic upgrade head
  .venv/bin/python -m grok_bot.demo_seed
)
echo "reset grok_demo_sample only"
