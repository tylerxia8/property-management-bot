# Milestone evidence

Latest command: `scripts/run_m0_evidence.sh` on 2026-11-07, after phase 5 distribution controls and owner statements.

| Check | Result | Log |
| --- | --- | --- |
| pytest against PostgreSQL 16.15 | 86 passed, 1 warning, 20.33s | `m0-pytest.txt` |
| Alembic upgrade through phase 5 and e2e seed | completed, including `0005_phase5_distributions` | `m0-e2e-seed.txt` |
| `GET /v1/health` | `local_auth_enabled` true | `m0-health.txt` |
| Web unit check | 1 passed | `m0-web.txt` |
| `next build` (Next.js 16.4.5) | compiled, including `/accounting`, `/distributions`, `/maintenance`, `/prequalification`, `/reviews`, and `/statements` | `m0-web.txt` |
| Playwright Chromium | 5 passed, 3.7s | `m0-web.txt` |

The warning is Starlette’s deprecation notice that `httpx` with `starlette.testclient` prefers `httpx2`. It is not a failed test.

`distribution-export.png` is the manager export after approval. It shows export settled false, export submitted false, a duplicate download, and `PROVIDER_SUBMISSION_DISABLED`. `owner-statement.png` is the linked owner’s fixture snapshot. The other owner’s sign-in showed no statement. `prequalification-hold.png` is the earlier prospect hold. `maintenance-intake.png` is the gas follow-up. `recorded-check.png` shows a recorded check still at available cents 0. `manager-property.png` is the manager rename screen.

Acceptance assertions are in `docs/TRACEABILITY.md`. The evidence script does not enable the payment simulator, fixture settlement, the fixture media scanner, a calendar provider, or a consumer-report provider. The API process for the browser sets `STEP_UP_MAX_AGE_SECONDS=900`. The seeded screening policy, tour schedule, 25,000-cent cash row, and statement reason are labeled fixture. Pytest does not inherit that step-up setting.
