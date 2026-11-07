# M0 evidence

Command: `scripts/run_m0_evidence.sh`, run on 2026-11-07 after the unit-add browser step.

| Check | Result | Log |
| --- | --- | --- |
| pytest against PostgreSQL 16.15 | 28 passed, 1 warning, 1.50s | `m0-pytest.txt` |
| Alembic upgrade and e2e seed | completed | `m0-e2e-seed.txt` |
| `GET /v1/health` | `local_auth_enabled` true | `m0-health.txt` |
| `node --test` web source check | 1 passed | `m0-web.txt` |
| `next build` (Next.js 16.4.5) | compiled and typechecked | `m0-web.txt` |
| Playwright Chromium shell | 1 passed, 2.1s | `m0-web.txt` |

The warning is Starlette’s deprecation notice that `httpx` with `starlette.testclient` prefers `httpx2`. The tests still passed. It is not a failed check.

`m0-bootstrap.txt` records PostgreSQL notices from `REVOKE` when `grok_app` is already not a member of the owner, auth, or migrator roles.

`manager-property.png` is the manager detail screen after an administrator created the property and unit and the manager renamed it. The shell states that local sign-in is not production OIDC or MFA.

Not run: production deployment, backup restore, load test, OIDC, MFA step-up, Celery dispatch, and every later PRD phase. This log is not a staging or production acceptance.
