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
| OpenAPI TypeScript | `apps/api/scripts/generate_api_types.py` writes every component schema, request body, parameter type, and success response type. Success responses without a schema: 0. File download is octet-stream. ADR 0013 |
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
| Success response schemas | Declared for every mounted JSON success response. ADR 0013. The generated file reports zero `unknown` success responses |
| Routes named in §9.2 and not mounted | Mounted in revision `0007_contract_routes`: ledger, journal reversal, bank transactions, bank matches, invoice read, credit notes, receipt return, and payment-item submission and settlement evidence. See ADR 0012 |
| Resource-scoped grants | A property grant authorizes that property only. It is not an organization-wide role. Bank queues stay organization-wide because those rows have no property |
| §13 alert routing and kill switches | Alerts are PostgreSQL rows. Dispatch can retry and record a fallback. `delivered_at` stays null. Three outbound switches default off |
| §14 local load at the proposed size | Measured in `test_proposed_portfolio_read_load` on the isolated test database: 100 properties, 300 units, 1,000 contacts, 10,000 stored messages, 20 in-process sessions, 500 reads, 0 errors. Latest printed sample: p50 210.7 ms, p95 403.7 ms, ledger p95 425.0 ms, 87.0 requests/second over 5.749 seconds. That sample met the proposed 500 ms and 1 second targets in this process. It is not a staging result. The 10× rollout check and the 1,000 maintenance files/month assumption were not run |
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
| Receipt return after allocation, before payout | §4.6 says to reverse allocations and fee accruals according to the agreement, and the agreement does not name the accounts | `CONFIGURATION_REQUIRED`. No reversal is posted. The pre-allocation custody reversal and the post-payout 1040 distribution return stay as specified |
| Step-up freshness and approval lifetime | §3 says “recent” and §4.7 proposes 24 hours | No default duration. Both settings at 0 refuse approval. The client cannot send a lifetime |
| Statutory North Carolina timing | §12 says the legal summary is not a legal opinion | No statutory encoder |
| Unit-command policy | Not specified. ADR 0004 records an analogy | Not described as a confirmed policy |
| Production malware scanning | No product is selected | Fixture scanner only in dev/test. HEIC stays unready |
