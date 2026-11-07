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
| Named approvers, recipient verification, dual control | No payment approval endpoint |
| Close calendar and retention matrix | No deletion job and no official statement |
| Reviewed screening and accommodation policy | No automatic preliminary qualification |
| Post-tour application vendor and adverse action | No consumer-report integration |
| Marketplace access and communication consent | No external intake or outbound send |
| Staffed emergency coverage | No unattended maintenance intake |
| Approved contractors and access rules | No assignment execution |
| Languages and accommodation operations | English-preference capture only, later |
| Media retention and sensitive-access map | No production media store |

## Pending deviations left unimplemented

| Topic | Why it is pending | M0 behavior |
| --- | --- | --- |
| Direct-bank receipt journal legs | §4.2 requires a template and does not specify the debit and credit accounts or status mapping | `DIRECT_BANK` returns `DIRECT_BANK_TEMPLATE_UNCONFIGURED` |
| Expense splits other than ownership weights | §4.4 mentions agreement responsibility rules and does not define a DSL | No allocator |
| Bank CSV column layout | §9.2 requires an import and does not define columns | CSV returns `BANK_IMPORT_FORMAT_UNCONFIGURED`. Canonical JSON import is implemented |
| Outbound-clearing account | §4.3 mentions it and assigns no code | No payment submission |
| Idempotency retention period | Not specified | Rows are kept; nothing expires them |
| Step-up freshness window | §3 says “recent” without a duration | No step-up endpoint |
| Statutory North Carolina timing, notice, or deposit administration | §12 says the legal summary is not a legal opinion | No statutory encoder |
| Unit-command policy if it should differ from properties | Not specified. ADR 0004 records a reversible analogy so the API exists | Analogy only; not described as a confirmed policy |
| Production malware scanning and KMS | Providers unselected | No media pipeline in M0 |
| Cookie session and CSRF | Needs the OIDC/session decision | Bearer dev token only, and only in dev/test |

## M0 items explicitly incomplete

| Item | Evidence status |
| --- | --- |
| OIDC login and MFA/step-up | Not implemented. Local auth is refused outside dev/test. |
| Celery/Redis dispatcher | Outbox rows are durable and tested. No worker is started, and `grok_app` cannot mark an outbox row dispatched. |
| Backup restore drill | Not run. |
| Owner, tenant, and resource-scoped visibility | Portal and resource-scoped grants get no property capability. Relationship tables are not in M0. |
| Contact and organization HTTP APIs | Tables and encryption exist. §9.2 does not name the routes, so they were not added. |
| Financial commands and housing decisions | Not implemented. |
