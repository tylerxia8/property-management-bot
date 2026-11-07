# ADR 0001 — M0 stack, layout, and version pins

Date: 2026-11-07

Status: accepted as an implementer technical choice. This is not a product-owner approval of business rules, and it does not approve the earlier discovery proposals as a set.

## Context

PRD §7.1 proposes Next.js + TypeScript, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL, and generated OpenAPI types. It says to pin supported versions at implementation time. Redis and Celery are part of that proposed stack for later asynchronous work. §8 requires PostgreSQL as the system of record.

The discovery note suggested Python 3.12, PostgreSQL 16, and Node 22 before those versions were checked against current support. This ADR records what was verified on 2026-11-07 and what this repository pins.

## Decision

Repository layout:

- `apps/api` — FastAPI application, Alembic migration, pytest suite
- `apps/web` — Next.js shell that calls `/v1` only
- `docs` — ADRs, plan, gates, traceability, setup, and command evidence

Pinned and verified on 2026-11-07:

| Component | Pin | Why this pin |
| --- | --- | --- |
| PostgreSQL | 16.15, Ubuntu package `16.15-0ubuntu0.24.04.1` | Current 16 minor. PostgreSQL 16 is supported through 2028-11-09. PostgreSQL 17 and 18 are also supported; 16 is the current minor packaged for this OS. PostgreSQL 14’s final release is 2026-11-12, so it was not used. |
| CPython | 3.12.3 (`requires-python >=3.12,<3.13`) | Installed interpreter. 3.12 still receives security fixes through 2028-10. |
| Node.js | 22.23.4 | Installed runtime. Node 22 remains in maintenance LTS through 2027-04-30. |
| FastAPI | 0.162.0 | Current PyPI release checked 2026-11-07 |
| SQLAlchemy | 2.1.8 | Current 2.x release checked 2026-11-07. PRD asks for SQLAlchemy 2. |
| Alembic | 1.20.1 | Current PyPI release checked 2026-11-07 |
| Pydantic | 2.14.3 | Current PyPI release checked 2026-11-07 |
| pydantic-settings | 2.16.2 | Current PyPI release checked 2026-11-07 |
| psycopg | 3.3.8 | Current PyPI release checked 2026-11-07 |
| cryptography | 50.0.2 | Current PyPI release checked 2026-11-07 |
| uvicorn | 0.54.0 | Current PyPI release checked 2026-11-07 |
| httpx | 0.28.1 | Current PyPI release checked 2026-11-07 |
| pytest | 9.2.0 | Current PyPI release checked 2026-11-07 |
| Next.js | 16.4.5 | Current npm `latest` checked 2026-11-07 |
| React / React DOM | 19.3.1 | Current npm release; satisfies Next 16.4.5 peer range |
| TypeScript | 7.0.2 | npm `latest` dist-tag checked 2026-11-07 |
| Playwright test | 1.65.0 | Current npm release checked 2026-11-07; Next peer range allows `^1.51.1` |

Schema changes ship as Alembic revisions that run real PostgreSQL SQL. M0 is revision `0001_m0_foundation` only. Tests use PostgreSQL. SQLite is not a stand-in.

The web package does not depend on a database driver. The browser and the Next server call the HTTP API.

Redis and Celery are not installed or started in M0. The outbox rows are the durable record. A worker process is an explicit later item, not a claim that jobs are dispatched.

## Consequences

- Local setup follows `docs/SETUP.md`.
- Bumping a pin requires an ADR update and a fresh install, not a silent float.
- Phase 2 and later add their own migrations. They do not edit `0001` in place after it has shipped.
