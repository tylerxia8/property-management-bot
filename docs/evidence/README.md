# Milestone evidence

Latest command: `scripts/run_m0_evidence.sh` on 2026-11-07, after phase 2 accounting core.

| Check | Result | Log |
| --- | --- | --- |
| pytest against PostgreSQL 16.15 | 42 passed, 1 warning, 5.15s | `m0-pytest.txt` |
| Alembic upgrade through phase 2 and e2e seed | completed | `m0-e2e-seed.txt` |
| `GET /v1/health` | `local_auth_enabled` true | `m0-health.txt` |
| Web unit check | 1 passed | `m0-web.txt` |
| `next build` (Next.js 16.4.5) | compiled, including `/accounting` | `m0-web.txt` |
| Playwright Chromium | 2 passed, 2.1s | `m0-web.txt` |

The warning is Starlette’s deprecation notice that `httpx` with `starlette.testclient` prefers `httpx2`. It is not a failed test.

`recorded-check.png` shows a recorded check still at available cents 0. `manager-property.png` is the earlier manager rename screen.

Phase 2 acceptance IDs are mapped in `docs/TRACEABILITY.md`. FIN-05, FIN-07, FIN-08’s provider timeout, FIN-10, FIN-15, and FIN-18 were not run. They belong to later phases.
