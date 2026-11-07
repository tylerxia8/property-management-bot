#!/usr/bin/env bash
# Run the M0 checks and save their output. This does not deploy or merge.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="$ROOT/apps/api"
WEB="$ROOT/apps/web"
EVIDENCE="$ROOT/docs/evidence"
mkdir -p "$EVIDENCE"

export APP_ENV=test
export DATABASE_URL="postgresql+psycopg://grok_app:grok_m0_app_local_only@127.0.0.1:5432/grok_m0_e2e"
export MIGRATION_DATABASE_URL="postgresql+psycopg://grok_migrator:grok_m0_migrator_local_only@127.0.0.1:5432/grok_m0_e2e"
export SESSION_SECRET="local-only-session-secret-at-least-32-chars"
export CONTACT_ENCRYPTION_KEY="$(python3 -c 'import base64; print(base64.b64encode(b"m0-contact-key-32-bytes-exactly!").decode())')"
export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"

sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -f "$API/scripts/bootstrap_roles.sql" >"$EVIDENCE/m0-bootstrap.txt"

(
  cd "$API"
  .venv/bin/pytest -ra
) | tee "$EVIDENCE/m0-pytest.txt"

(
  cd "$API"
  MIGRATION_DATABASE_URL="$MIGRATION_DATABASE_URL" .venv/bin/alembic upgrade head
  APP_ENV=test MIGRATION_DATABASE_URL="$MIGRATION_DATABASE_URL" .venv/bin/python -m grok_bot.seed
  echo "alembic upgrade head and grok_bot.seed exited 0"
) 2>&1 | tee "$EVIDENCE/m0-e2e-seed.txt"

(
  cd "$API"
  .venv/bin/uvicorn grok_bot.main:app --host 127.0.0.1 --port 8000
) >"$EVIDENCE/m0-api-server.txt" 2>&1 &
API_PID=$!
cleanup() {
  if kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" || true
    wait "$API_PID" || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 50); do
  if curl -sf "http://127.0.0.1:8000/v1/health" >/dev/null; then
    break
  fi
  sleep 0.2
done
curl -sf "http://127.0.0.1:8000/v1/health" | tee "$EVIDENCE/m0-health.txt"
echo

(
  cd "$WEB"
  npm install
  npm run test:unit
  npm run build
  npx playwright install chromium
  npm run test:e2e
) | tee "$EVIDENCE/m0-web.txt"

if [[ -f "$WEB/test-results/manager-property.png" ]]; then
  cp "$WEB/test-results/manager-property.png" "$EVIDENCE/manager-property.png"
fi
if [[ -f "$WEB/test-results/maintenance-intake.png" ]]; then
  cp "$WEB/test-results/maintenance-intake.png" "$EVIDENCE/maintenance-intake.png"
fi
if [[ -f "$WEB/test-results/recorded-check.png" ]]; then
  cp "$WEB/test-results/recorded-check.png" "$EVIDENCE/recorded-check.png"
fi
