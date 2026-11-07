# ADR 0003 — RLS roles and composite foreign keys

Date: 2026-11-07

Status: accepted as the M0 enforcement design for PRD §8.1 and §8.3.

## Context

PRD §8.1 requires `organization_id` on business tables, UUID keys, composite foreign keys on `(organization_id, id)`, and timestamps. §8.3 requires row-level security plus API authorization. Workers must set organization context per transaction and must not leak it through pooling. Superusers bypass RLS, so a test that connects as a superuser cannot prove the control.

`organizations` is the tenant root. The PRD also says every business table has `organization_id`. The root row stores `organization_id` equal to `id` so the same policy expression and composite uniqueness apply.

## Decision

Cluster roles, created by `apps/api/scripts/bootstrap_roles.sql` before migrations:

| Role | Attributes | Use |
| --- | --- | --- |
| `grok_migrator` | `LOGIN SUPERUSER` | Alembic only. Bypasses RLS because it is a superuser. Local password only. |
| `grok_owner` | `NOLOGIN NOSUPERUSER NOBYPASSRLS` | Owns application tables so the runtime role is not the owner. |
| `grok_app` | `LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT` | API and SQL isolation tests. |
| `grok_auth` | `NOLOGIN BYPASSRLS NOSUPERUSER` | Owns `app_local_login` only. Not granted to `grok_app`. |

`BYPASSRLS` on `grok_auth` exists because a login lookup has to resolve membership before an organization GUC is known. The function takes issuer, subject, and password, returns no password hash, and is not a general query API. `grok_app` cannot `SET ROLE grok_auth`.

Every M0 business table enables and forces row-level security. The policy compares `organization_id` to `NULLIF(current_setting('app.organization_id', true), '')::uuid`. An empty setting selects no rows.

The API sets that GUC with `set_config(..., true)` so it is local to the transaction. Pool checkout also clears `app.organization_id` and `app.actor_id` in autocommit, so a session-level value cannot survive to the next borrower.

Composite foreign keys, not application convention alone, reject cross-organization references:

- `role_grants (organization_id, user_id)` → `users (organization_id, id)`
- `contacts (organization_id, party_id)` → `parties (organization_id, id)`
- `properties (organization_id, created_by)` → `users (organization_id, id)`
- `units (organization_id, property_id)` → `properties (organization_id, id)`
- `audit_events (organization_id, actor_id)` → `users (organization_id, id)`
- `outbox_events (organization_id, property_id)` → `properties (organization_id, id)`

`grok_app` does not receive `UPDATE` or `DELETE` on `audit_events`, `inbox_events`, or `idempotency_records`. Triggers also reject those mutations. `grok_app` does not receive `DELETE` on portfolio tables and does not receive `UPDATE` on the outbox.

No M0 column uses PostgreSQL `real` or `double precision`.

## Consequences

- Tests that prove isolation connect as `grok_app` and assert `rolsuper = false`, `rolbypassrls = false`, and `relowner <> current_user`.
- Cross-organization foreign-key tests connect as `grok_migrator` so a failure is the constraint, not an RLS filter.
- Later migrations must grant privileges explicitly. Default public create on the schema is not how the API gains access.
