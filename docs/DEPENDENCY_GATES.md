# Dependency gates and unimplemented decisions

Date: 2026-11-07

A gate means the affected capability stays off until the named decision or credential exists. A pending deviation means the specification does not define the behavior, so this repository does not invent it.

## Production gates already in PRD §18

These are not PRD contradictions. M0 does not enable the capability.

| Gate | What stays off |
| --- | --- |
| Portfolio, leases, reconciled opening balances | No production import |
| Entity, license, and trust-accounting review | No real-money handling |
| Bank accounts, pooling model, payment provider, availability rules | No live deposit or payout adapter |
| Signed fee terms | No fee accrual |
| Ownership shares and responsibility language | No beneficial allocation |
| Reserves, spending authority, shortfall priority | No reserve or creditor-priority engine |
| Named approvers, recipient verification, dual control | Dev/test approval stores a manager, a snapshot hash, and an explicit lifetime after a local password step-up. Production MFA is not configured. The fixture settlement flag does not clear cash. Provider submit stays `PROVIDER_SUBMISSION_DISABLED` unless the dev/test simulator is enabled, and that simulator is not a bank. |
| Close calendar and retention matrix | Period close can be recorded. There is no deletion job. Owner statements are ledger snapshots, not an official package. |
| Reviewed screening and accommodation policy | No production ratio is seeded. A missing policy returns human review and `CONFIGURATION_REQUIRED`. Fixture policies are labeled `fixture:`. Assistance-animal notes are private. No consumer report is ordered. |
| Post-tour application vendor and adverse action | No consumer-report integration |
| Marketplace access and communication consent | No external intake or outbound send |
| Staffed emergency coverage | Escalation rows can be stored. Without a configured destination the job is `DESTINATION_UNCONFIGURED` and `delivered_at` stays null. Nothing is sent. |
| Approved contractors and access rules | A manager can assign an approved local profile. There is no external contractor network, and availability does not grant entry. |
| Languages and accommodation operations | English-preference capture only, later |
| Media retention and sensitive-access map | No production media store |

## Pending deviations left unimplemented

| Topic | Why it is pending | M0 behavior |
| --- | --- | --- |
| Direct-bank receipt journal legs | §4.2 requires a template and does not specify the debit and credit accounts or status mapping | `DIRECT_BANK` returns `DIRECT_BANK_TEMPLATE_UNCONFIGURED` |
| Expense splits other than ownership weights | §4.4 mentions agreement responsibility rules and does not define a DSL | No allocator |
| Bank CSV column layout | §9.2 requires an import and does not define columns | CSV returns `BANK_IMPORT_FORMAT_UNCONFIGURED`. Canonical JSON import is implemented |
| Outbound-clearing account | §4.3 mentions it and assigns no code | No live payment submission. Simulator settlement uses the existing bank and payable accounts and is labeled simulator. |
| Idempotency retention period | Not specified | Rows are kept; nothing expires them |
| Step-up freshness window | §3 says “recent” without a duration | No default age. `step_up_max_age_seconds` of 0 refuses approval. `APPROVAL_TTL_HOURS` of 0 refuses approval. The client cannot send a lifetime. The local step-up route exists only with dev/test login. |
| Statutory North Carolina timing, notice, or deposit administration | §12 says the legal summary is not a legal opinion | No statutory encoder |
| Unit-command policy if it should differ from properties | Not specified. ADR 0004 records a reversible analogy so the API exists | Analogy only; not described as a confirmed policy |
| Production malware scanning and KMS | Providers unselected | Local JPEG/PNG/MP4 checks run only when `APP_ENV` is development or test and `MEDIA_SCANNER=fixture`. The scanner name is `fixture-byte-scanner`. Production cannot mark an upload ready with it. HEIC stays unready. |
| Cookie session and CSRF | Needs the OIDC/session decision | Bearer dev token only, and only in dev/test |

## M0 items explicitly incomplete

| Item | Evidence status |
| --- | --- |
| OIDC login and MFA/step-up | Not implemented. Local auth is refused outside dev/test. |
| Celery/Redis dispatcher | Outbox rows are durable and tested. No worker is started, and `grok_app` cannot mark an outbox row dispatched. |
| Backup restore drill | Not run. |
| Owner, tenant, and resource-scoped visibility | Owners read linked statements only. A missing actor reads no organization rows. Production OIDC is still absent. |
| Contact and organization HTTP APIs | Tables and encryption exist. §9.2 does not name the routes, so they were not added. |
| Financial commands and housing decisions | Phase 2 posts simulated journals. Phase 3 approves a maintenance invoice through that same payable command. No live payment, and no automated housing decision. |
