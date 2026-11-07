# Milestone evidence

Latest command: `scripts/run_m0_evidence.sh` on 2026-11-07, after declared success schemas.

| Check | Result | Log |
| --- | --- | --- |
| pytest against PostgreSQL 16.15 | 109 passed, 1 warning, 35.83s | `m0-pytest.txt` |
| Alembic upgrade through `0008_success_contracts` and e2e seed | exited 0 | `m0-e2e-seed.txt` |
| `pip check` | No broken requirements found | `m0-e2e-seed.txt` |
| `npm audit` | 0 vulnerabilities | `m0-web.txt` |
| Local `pg_dump` / `pg_restore` into `grok_m0_restore` | properties 1, journal_entries 1, owner_statements 1 | `backup-restore.txt` |
| `GET /v1/health` | `local_auth_enabled` true | `m0-health.txt` |
| Web unit check | 1 passed | `m0-web.txt` |
| `next build` (Next.js 16.4.5) | compiled, including `/distributions` and `/statements` | `m0-web.txt` |
| Playwright Chromium | 6 passed, 5.4s, including the axe scan | `m0-web.txt` |
| `tsc` via `next build` | Finished TypeScript with no errors | `m0-web.txt` |

The warning is Starlette’s deprecation notice that `httpx` with `starlette.testclient` prefers `httpx2`. It is not a failed test.

`distribution-export.png` shows export settled false, export submitted false, a duplicate download, and `PROVIDER_SUBMISSION_DISABLED`. `owner-statement.png` is the linked owner’s fixture snapshot. The axe scan reported no serious or critical violations on login, properties, distributions, and statements. That scan is not a WCAG certification.

This run does not enable the payment simulator, fixture settlement, or the fixture media scanner. The API process sets `STEP_UP_MAX_AGE_SECONDS=900` and `APPROVAL_TTL_HOURS=24` for the browser only. Those are dev/test fixtures. Pytest does not inherit them. The seeded 25,000-cent row and statement reason are labeled fixture.

This evidence is local. It is not PRD §16 staging acceptance. See `docs/ACCEPTANCE.md`.

Success schemas are declared for every mounted JSON response. The generator reports 111 typed success responses and 0 undeclared across 115 mounted operations. A manual screen-reader pass was not run; this environment has no screen reader. The axe scan is the automated check. After this evidence run, `test_proposed_portfolio_read_load -s` printed 500 reads, 0 errors, p50 210.7 ms, p95 403.7 ms, ledger p95 425.0 ms, and 87.0 requests/second. The full pytest run passed the same 500 ms and 1 second assertions without printing the percentiles. That measurement is local TestClient traffic on the isolated test database. It is not a staging or 10× result.
