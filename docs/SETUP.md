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

Two more flags fail closed the same way:

- `ALLOW_FIXTURE_LEDGER_SETTLEMENT` defaults to false. Even when true, production ignores it. The declaration and simulated-settlement routes then return `409 APPROVAL_CONTRACT_REQUIRED` and post nothing. See ADR 0007.
- `MEDIA_SCANNER=fixture` is the only local media checker, and only in development or test. It is not a malware product. Any other value, including in production, leaves uploads rejected with `SCANNER_NOT_CONFIGURED`. `MEDIA_ROOT` is the local quarantine directory. JPEG and PNG use Pillow. Short MP4 and MOV files use `ffmpeg` and `ffprobe` on this machine. HEIC is recognized and left unready.

The evidence script does not set either flag, so the browser path does not clear a payable and does not mark an upload ready.

Phase 5 adds two more settings:

- `PAYMENT_SIMULATOR=enabled` is accepted only when `APP_ENV` is development or test. It lets an approved distribution item post a simulator settlement journal. The payment event is marked simulator. It is not a bank transfer. Unset, including in the evidence script, `POST /distribution-batches/{id}/submit` returns `409 PROVIDER_SUBMISSION_DISABLED`.
- `STEP_UP_MAX_AGE_SECONDS` defaults to 0. Approval then returns `409 CONFIGURATION_REQUIRED`. The evidence API process sets it to 900 so the browser can record a dev/test password step-up. That step-up is not production MFA, and the route is not mounted when local auth is off.
- `APPROVAL_TTL_HOURS` defaults to 0. Approval then returns `CONFIGURATION_REQUIRED`. The client cannot send a lifetime. The evidence API process sets `24` only as a bounded fixture, not as a confirmed business rule. ADR 0011.
- `WEBHOOK_SECRET` empty disables ingress. A secret of at least 16 characters is accepted only in development or test. Production returns `WEBHOOK_NOT_CONFIGURED`.

Manual bank imports accept canonical JSON or the documented [`canonical_csv_v1` format](adr/0017-canonical-bank-csv-import.md). The accounting screen accepts a CSV file with the four exact columns in that contract. Imports record evidence for reconciliation; they do not verify availability or move money. Conflicting amount/date evidence for an existing bank transaction returns 409 and rolls back the batch.

`alembic downgrade` refuses to run unless `ALLOW_DESTRUCTIVE_DOWNGRADE=1`. Downgrade can drop ledger tables. The migration test sets the flag.

The outbox worker is `dispatch_outbox` in `grok_bot.domain.outbox_worker`. It reads PostgreSQL only, retries, and does not deliver. Redis is not used.

`apps/api/scripts/generate_api_types.py` writes `apps/web/lib/api-types.generated.ts` from the OpenAPI document. Every component schema becomes a TypeScript interface. Each operation includes its request body, parameter types, and success response types. A success response without a schema is `unknown`, and `test_every_mounted_success_response_has_a_schema` fails while any remain. Head revision `0008_success_contracts` is the current schema. `openapi-typescript` was not added because 7.13.0 requires TypeScript 5 and this app pins TypeScript 7.0.2.

Manual submission and settlement evidence require `Idempotency-Key`, `distributions.approve`, and a reference. They record the item amount in USD and set `bank_contacted` false. They do not call a bank and they do not read the fixture settlement flag. ADR 0013.

`scripts/backup_restore_drill.sh` dumps a local database and restores it into `grok_m0_restore`. That is a local drill, not encrypted point-in-time recovery.

`grok_app` with only `app.organization_id` set reads no tenant rows. Checkout clears `app.actor_id`. Journal posting still uses `grok_posting`. Alembic still uses `grok_migrator`.

The e2e seed adds two owner logins, `owner@example.test` and `other-owner@example.test`, both with password `local-owner-password`. It also posts a labeled 25,000-cent fixture so the distribution screen has one owner item. That amount is not an opening balance or a fee rule. The seeded statement reason starts with `Browser fixture snapshot`.

Phase 4 does not add a calendar or screening provider. Tour confirmation stays `CONFIRMATION_PENDING` unless a manager records `MANAGER_CONFIRMED`, and `external_event_created` cannot be set true. The e2e seed publishes a screening policy and a tour schedule whose labels start with `fixture:`. Those rows are not production rules. The illustrative income ratio is only inside that fixture policy.

## Web

```bash
cd apps/web
npm install
npm run build
npm run test:unit
```

The browser calls `http://127.0.0.1:8000` unless `NEXT_PUBLIC_API_BASE_URL` is set at build time. Start the API with `uvicorn grok_bot.main:app --host 127.0.0.1 --port 8000` from `apps/api` after exporting the variables above.

## Evidence command

From the repository root, `scripts/run_m0_evidence.sh` bootstraps roles, runs pytest, builds the web app, typechecks it, and runs Playwright against the API. It writes logs under `docs/evidence/`. The web install uses `npm ci` and `apps/web/package-lock.json`.

`compose.demo.yaml` and `scripts/package_demo_bundle.py` build a laptop zip that publishes only `127.0.0.1:3000`. Postgres stays on the compose network. Windows uses the PowerShell launchers. macOS uses `/bin/bash start-macos.sh`. ADR 0016.

`scripts/reset_demo_sample.sh` recreates only `grok_demo_sample`. It refuses production. The fixture organization is fictional, outbound switches stay off, and `POST /v1/demo/session` is mounted only for that database when `DEMO_FIXTURE=sample` and `APP_ENV` is development or test. ADR 0015.

GitHub Actions workflow `.github/workflows/ci.yml` runs that suite on pull requests and on pushes to `main`. It installs `apps/api/requirements.lock`, then the local package without fetching newer dependencies. The token permission is `contents: read`. The workflow does not use `pull_request_target`, repository secrets, or a deployment. ADR 0014.
