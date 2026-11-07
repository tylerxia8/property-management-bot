# Milestone evidence

Latest command: `scripts/run_m0_evidence.sh` on 2026-11-07, after phase 3 maintenance.

| Check | Result | Log |
| --- | --- | --- |
| pytest against PostgreSQL 16.15 | 59 passed, 1 warning, 9.45s | `m0-pytest.txt` |
| Alembic upgrade through phase 3 and e2e seed | completed, including `0003_phase3_maintenance` | `m0-e2e-seed.txt` |
| `GET /v1/health` | `local_auth_enabled` true | `m0-health.txt` |
| Web unit check | 1 passed | `m0-web.txt` |
| `next build` (Next.js 16.4.5) | compiled, including `/accounting` and `/maintenance` | `m0-web.txt` |
| Playwright Chromium | 3 passed, 2.6s | `m0-web.txt` |

The warning is Starlette’s deprecation notice that `httpx` with `starlette.testclient` prefers `httpx2`. It is not a failed test.

`maintenance-intake.png` is the tenant shell after “The kitchen sink leaks” and a follow-up “I smell gas”: ticket 1, the reviewed safety sentence, “Do not operate electrical switches,” and the statement that this screen does not contact emergency services. `recorded-check.png` shows a recorded check still at available cents 0. `manager-property.png` is the manager rename screen.

Phase 2 and phase 3 acceptance IDs are mapped in `docs/TRACEABILITY.md`. FIN-05, FIN-07, FIN-08’s provider timeout, FIN-10, FIN-15, and FIN-18 were not run. Prospect cases were not run. The evidence script does not enable fixture settlement or the fixture media scanner.
