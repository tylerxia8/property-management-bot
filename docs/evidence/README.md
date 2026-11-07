# Milestone evidence

Latest command: `scripts/run_m0_evidence.sh` on 2026-11-07, after phase 4 prospects and tours.

| Check | Result | Log |
| --- | --- | --- |
| pytest against PostgreSQL 16.15 | 74 passed, 1 warning, 15.89s | `m0-pytest.txt` |
| Alembic upgrade through phase 4 and e2e seed | completed, including `0004_phase4_prospects` | `m0-e2e-seed.txt` |
| `GET /v1/health` | `local_auth_enabled` true | `m0-health.txt` |
| Web unit check | 1 passed | `m0-web.txt` |
| `next build` (Next.js 16.4.5) | compiled, including `/accounting`, `/maintenance`, `/prequalification`, and `/reviews` | `m0-web.txt` |
| Playwright Chromium | 4 passed, 2.7s | `m0-web.txt` |

The warning is Starlette’s deprecation notice that `httpx` with `starlette.testclient` prefers `httpx2`. It is not a failed test.

`prequalification-hold.png` is the prospect shell after a missing-period question, a human-review result, a manager exception, and a local hold. The page shows `Hold HELD in America/New_York` and says the external calendar event was not created. `maintenance-intake.png` is the earlier gas follow-up. `recorded-check.png` shows a recorded check still at available cents 0. `manager-property.png` is the manager rename screen.

Acceptance assertions are in `docs/TRACEABILITY.md`. The evidence script does not enable fixture settlement, the fixture media scanner, a calendar provider, or a consumer-report provider. The seeded screening policy and tour schedule are labeled `fixture:`.
