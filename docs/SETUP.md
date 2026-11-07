# Local setup

M0 runs on the developer machine. It does not deploy, and it does not call a bank, an identity provider, or an outbound messaging API.

Verified on 2026-11-07: PostgreSQL 16.15 (`16.15-0ubuntu0.24.04.1`), CPython 3.12.3, Node.js 22.23.4.

## PostgreSQL roles

`apps/api/scripts/bootstrap_roles.sql` creates local-only roles and three databases: `grok_m0_test`, `grok_m0_migration`, and `grok_m0_e2e`.

The passwords in that file are local bootstrap credentials. They are not production secrets. `grok_migrator` is a superuser used only for Alembic. The API connects as `grok_app`, which is not a superuser and does not bypass row-level security.

```bash
sudo -u postgres psql -v ON_ERROR_STOP=1 -f apps/api/scripts/bootstrap_roles.sql
```

## API

```bash
cd apps/api
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
export APP_ENV=test
export DATABASE_URL=postgresql+psycopg://grok_app:grok_m0_app_local_only@127.0.0.1:5432/grok_m0_test
export MIGRATION_DATABASE_URL=postgresql+psycopg://grok_migrator:grok_m0_migrator_local_only@127.0.0.1:5432/grok_m0_test
export SESSION_SECRET=local-only-session-secret-at-least-32-chars
export CONTACT_ENCRYPTION_KEY="$(python3 -c 'import os,base64; print(base64.b64encode(os.urandom(32)).decode())')"
.venv/bin/alembic upgrade head
.venv/bin/pytest
```

`APP_ENV=production` does not mount local login. Leave production processes without a dev password workflow.

## Web

```bash
cd apps/web
npm install
npm run build
npm run test:unit
```

The browser calls `http://127.0.0.1:8000` unless `NEXT_PUBLIC_API_BASE_URL` is set at build time. Start the API with `uvicorn grok_bot.main:app --host 127.0.0.1 --port 8000` from `apps/api` after exporting the variables above.

## Evidence command

From the repository root, `scripts/run_m0_evidence.sh` bootstraps roles, runs pytest, builds the web app, and runs Playwright against the API. It writes logs under `docs/evidence/`.
