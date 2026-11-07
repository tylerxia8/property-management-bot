# Dependency gates and current gaps

Date: 2026-11-07, after local acceptance hardening on this branch.

A gate means a capability stays off until a named business decision or external account exists. A stack deviation means this repository chose different local software from a PRD proposal. A deviation does not need a vendor credential. A pending template means the specification does not define the behavior, so this repository does not invent it.

## Current status

This section is the status of the branch. The historical M0 table below is not.

| Item | Current status |
| --- | --- |
| PostgreSQL outbox worker | Implemented. `dispatch_outbox` claims rows with `app_outbox_progress`, retries, and marks `FAILED` after five attempts. Delivery stays off. Tested by `test_worker_retries_then_dead_letters_without_delivery` and `test_fin_04_worker_replays_one_payable`. `grok_app` still has no general `UPDATE` on `outbox_events`. |
| Backup restore | A local `pg_dump` / `pg_restore` into `grok_m0_restore` ran. The log is `docs/evidence/backup-restore.txt`: 1 property, 1 journal entry, 1 owner statement. Encrypted point-in-time recovery was not built. The PRD calls the 15-minute / 4-hour targets proposed. |
| Celery and Redis | Not installed. They are the dispatcher named in PRD §7.1 and §7.2. The implemented dispatcher is PostgreSQL. No Redis or Celery credential is missing; the packages were not adopted. Redis is not a source of truth. |
| OpenAPI TypeScript | `apps/api/scripts/generate_api_types.py` writes an interface for every component schema and a path map. Most success responses are `unknown` because the route does not declare a response schema. See `docs/ACCEPTANCE.md`. |
| Local login and step-up | Dev/test only. Production does not mount them. Production MFA is not configured. |

## Historical M0 record

This is what was true at the foundation milestone only. Later commits on this branch superseded the worker and backup rows.

| Item at M0 | Status then |
| --- | --- |
| Outbox worker | Not started. Rows were durable and undispatched. |
| Backup restore drill | Not run. |
| Ledger, maintenance, prospects, distributions | Not in that milestone. |

## Provider and business gates

These come from PRD §18 and §11. They stay off until the named decision or account exists. They are not the same thing as a missing local package.

| Gate | What stays off |
| --- | --- |
| Portfolio, leases, reconciled opening balances | No production import |
| Entity, license, and trust-accounting review | No real-money handling |
| Bank accounts, pooling model, payment provider, availability rules | No live deposit or payout adapter |
| Signed fee terms | No production fee rate. The 8% figure exists only in the FIN-02 test |
| Ownership shares and responsibility language beyond weights | No other expense split |
| Reserves, spending authority, shortfall priority | No reserve or creditor-priority engine |
| Named approvers, recipient verification, dual control | Production MFA and dual control are not configured. Dev/test approval uses a server lifetime and a local password step-up. The fixture settlement flag does not clear cash |
| Close calendar and retention matrix | Period close can be recorded. There is no deletion job. Statements are ledger snapshots, not an official package |
| Reviewed screening and accommodation policy | No production ratio is seeded. A missing policy returns human review. Fixture policies are labeled `fixture:` |
| Post-tour application vendor and adverse action | No consumer-report integration |
| Marketplace access and communication consent | No external intake or outbound send |
| Staffed emergency coverage | Escalation rows can be stored. Nothing is sent. A missing destination is `DESTINATION_UNCONFIGURED` |
| Approved contractors and access rules | A manager can assign an approved local profile. There is no external contractor network |
| Languages and accommodation operations | No production language pack |
| Media retention and sensitive-access map | No production object store or KMS |

## Confirmed behavior still missing without a vendor account

These do not wait on a bank, an identity vendor, or an API key.

| Gap | Current behavior |
| --- | --- |
| Celery and Redis | Not installed. PostgreSQL is the worker. Delivery is disabled. ADR 0011 |
| Success response schemas | 97 success responses in the OpenAPI document have no schema, so the generated TypeScript types them as `unknown` |
| Routes named in §9.2 and not mounted | `GET /properties/{id}/ledger`, `POST /journals/{id}/reversals`, `GET /bank-transactions`, `POST /bank-matches`, `GET /invoices/{id}`, `POST /invoices/{id}/credit-notes`, `POST /payment-items/{id}/submission-evidence`, `POST /payment-items/{id}/settlement-evidence` |
| Resource-scoped grants | Rows can store `resource_type`. Login and the worker ignore every grant whose `resource_type` is not null |
| §13 alert routing, runbooks, and independent kill switches | `GET /v1/operations/queue` returns counts. `alerts_sent` is false. Messaging, calendar, and payment are not separate organization switches. Payment submission is disabled for the whole process |
| §15.4 load test at the stated volume | Not run |
| §15.4 manual screen-reader pass | Not run. The axe scan is not that pass |
| Cookie session and CSRF | Not implemented. The session is a bearer token. ADR 0011 |
| §16 staging acceptance | Not run. There is no staging environment and no named reviewer sign-off |

## Unspecified templates left unimplemented

| Topic | Why it is pending | Current behavior |
| --- | --- | --- |
| Direct-bank receipt journal legs | §4.2 requires a template and does not specify the accounts | `DIRECT_BANK` returns `DIRECT_BANK_TEMPLATE_UNCONFIGURED` |
| Expense splits other than ownership weights | §4.4 does not define the other rules | No allocator |
| Bank CSV column layout | §9.2 requires an import and does not define columns | CSV returns `BANK_IMPORT_FORMAT_UNCONFIGURED`. Canonical JSON import is implemented |
| Outbound-clearing account | §4.3 assigns no code | No live payment submission. Simulator settlement uses the existing bank and payable accounts and is labeled simulator |
| Idempotency retention period | Not specified | Rows are kept |
| Step-up freshness and approval lifetime | §3 says “recent” and §4.7 proposes 24 hours | No default duration. Both settings at 0 refuse approval. The client cannot send a lifetime |
| Statutory North Carolina timing | §12 says the legal summary is not a legal opinion | No statutory encoder |
| Unit-command policy | Not specified. ADR 0004 records an analogy | Not described as a confirmed policy |
| Production malware scanning | No product is selected | Fixture scanner only in dev/test. HEIC stays unready |
