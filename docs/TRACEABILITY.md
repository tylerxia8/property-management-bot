# M0 requirement traceability

PRD references are the contract. Tests below are the M0 checks. “Not this milestone” means the requirement stays in a later phase or behind a gate, not that it was dropped.

| Requirement | M0 implementation | Test |
| --- | --- | --- |
| §7.1 API does not let the web open the database | Next.js has no database client; browser calls `/v1` | `apps/web/tests/no-database.test.mjs`, Playwright shell |
| §7.2 state change and outbox commit together; Redis is not the only record | Property and unit writes insert the outbox in the same transaction | `test_audit_outbox.py` |
| §7.2 rollback leaves no outbox | Service transaction raises before commit | `test_audit_outbox.py` |
| §8.1 UUID, `organization_id`, timestamps, composite uniqueness | Revision `0001_m0_foundation` | `test_migration_cycle.py`, `test_rls_and_fks.py` |
| §8.1 integer money, no binary float | No float columns in the M0 schema | `test_migration_cycle.py` |
| §8.3 RLS and non-owner runtime role | `grok_app` is `NOSUPERUSER NOBYPASSRLS` and does not own tables | `test_rls_and_fks.py` |
| §8.3 composite foreign keys | Named constraints | `test_rls_and_fks.py` |
| §8.3 pool context must not leak | Checkout clears GUCs; writes use `SET LOCAL` | `test_rls_and_fks.py` |
| §3 server-side roles; UI is not the control | Capabilities enforced in FastAPI | `test_api_authz.py`, Playwright |
| §3 one user, several roles | Capability union of org-wide grants | `test_api_authz.py` |
| §3 active dates on grants | Expired grants do not authenticate | `test_api_authz.py` |
| §3 MFA for financial approval and role changes | No such route in M0 | Incomplete; see `DEPENDENCY_GATES.md` |
| §9.1 error envelope and `request_id` | Shared handlers | API tests |
| §9.1 cursor pagination, default 50, max 200 | Property and unit lists | `test_api_authz.py` |
| §9.1 idempotency replay and `409 IDEMPOTENCY_CONFLICT` | Property and unit creates | `test_api_authz.py`, `test_api_concurrency.py` |
| §9.1 `If-Match` optimistic concurrency | Property and unit patch | `test_api_authz.py`, `test_api_concurrency.py` |
| §9.2 `GET /me`, property list/create/read/patch | ADR 0004 | `test_api_authz.py` |
| §9.2 organization comes from auth context | Body `organization_id` rejected; cross-org id returns 404 | `test_api_authz.py` |
| §12.2 audit before/after with sensitive values redacted | App redaction plus insert trigger | `test_audit_outbox.py` |
| §12.2 append-only audit | Privilege and trigger | `test_audit_outbox.py` |
| §8.2 encrypted contact values | AES-GCM, no plaintext column | `test_inbox_and_contacts.py` |
| §7.2 inbox stores provider event id and encrypted payload; unique provider id | `inbox_events` | `test_inbox_and_contacts.py` |
| §11 OIDC | Not selected | ADR 0002 fail-closed test |
| §4 through §6 financial, prospect, and maintenance behavior | Not in M0 | Later phases |
| §16 staging acceptance | Not claimed | Local tests only |

Playwright covers the dev/test shell: local-auth disclosure, accounting read without create, tenant forbidden state, administrator create, manager rename and unit add. It does not claim WCAG certification.
