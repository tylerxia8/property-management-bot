# Grok Bot — Engineering Product Requirements Document (Version 2.0)

**Status:** Engineering specification; no application has been implemented.

**Repository:** `tylerxia8/property-management-bot`

**Specification date:** November 6, 2026

**Audience:** Product owner, implementation agents (including Grok), engineers, accountants, and compliance reviewers.

## Contents

1. [Executive summary and business objectives](#1-executive-summary-and-business-objectives)
2. [Confirmed requirements, decisions, and assumptions](#2-confirmed-requirements-decisions-and-assumptions)
3. [Roles and permissions](#3-roles-and-permissions)
4. [Financial operations](#4-financial-operations)
5. [Prospect prequalification and tours](#5-prospect-prequalification-and-tours)
6. [Maintenance intake and coordination](#6-maintenance-intake-and-coordination)
7. [Architecture and technology](#7-architecture-and-technology)
8. [PostgreSQL schema and relationships](#8-postgresql-schema-and-relationships)
9. [REST API contracts](#9-rest-api-contracts)
10. [AI architecture and tool permissions](#10-ai-architecture-and-tool-permissions)
11. [Integrations](#11-integrations)
12. [Security, privacy, and regulatory considerations](#12-security-privacy-and-regulatory-considerations)
13. [Errors, exceptions, and operations](#13-errors-exceptions-and-operations)
14. [Performance and scalability](#14-performance-and-scalability)
15. [Verification and automated tests](#15-verification-and-automated-tests)
16. [MVP acceptance criteria](#16-mvp-acceptance-criteria)
17. [Implementation phases](#17-implementation-phases)
18. [Open questions and production gates](#18-open-questions-and-production-gates)

## 1. Executive summary and business objectives

Grok Bot supports a property manager overseeing **51–100 residential rental properties in North Carolina**. It reduces manual work in three connected operations: rent collection/accounting/distributions, preliminary tenant qualification before tours, and maintenance coordination. A property may contain multiple rental units; implementation must preserve that distinction.

The platform is a controlled operational assistant. A deterministic double-entry ledger determines financial amounts. AI gathers information, extracts draft document fields, asks follow-up questions, and explains approved calculations. Humans approve financial execution, screening exceptions, final housing decisions, and contractor assignments.

The highest-priority conversational capability is thorough maintenance intake: proactively ask issue-specific questions and request useful photos/videos so contractors can prepare. Missing media, incomplete availability, or an unanswered nonessential question must never prevent a legitimate repair request or delay emergency escalation.

### 1.1 Business outcomes and measurement

Proposed pilot targets, to be measured against an agreed baseline rather than represented as existing results:

| Outcome | Pilot measurement and target |
| --- | --- |
| Reliable owner distributions | Zero duplicate disbursements or payments exceeding eligible funds; every payment traces to approval and journal entries |
| Less bookkeeping effort | At least 50% reduction in manager time preparing monthly statements and payout proposals |
| More useful tours | At least 90% of automatically scheduled tours have complete preliminary intake and a recorded policy evaluation |
| Better repair preparation | At least 90% of nonemergency tickets include issue location, symptom detail, media or documented limitation, and availability or documented limitation |
| Fast emergency response | Emergency rule match creates an escalation event within 5 seconds of processing the message; external delivery measured separately |
| Human accountability | All privileged decisions include actor, reason, timestamp, and versioned inputs |

MVP includes a manager web console, prospect/tenant conversational intake, secure upload links, owner statements, contractor coordination, manual bank reconciliation/imports, and approved payment instruction export. Live payment execution is an adapter capability gated by provider selection and validation. A complete MVP must support approved export and recording execution evidence without claiming an export itself moved money.

Out of MVP scope: automated final tenant selection, automated formal screening/adverse action, payroll, tax filing/1099 submission, eviction workflows, mortgage servicing, security-deposit deductions/refunds, and guaranteed Zillow API access. Security deposits must be identified and segregated if encountered; full deposit administration is deferred.

## 2. Confirmed requirements, decisions, and assumptions

Labels used throughout this specification:

- **Confirmed:** Required by the product owner’s task.
- **Proposed:** An implementation default that engineers may implement unless replaced by a documented decision.
- **Illustrative:** Example numbers or policies used for explanation/tests only; never silently seeded into production.
- **Production gate:** A missing business, legal, or provider decision that must block the affected capability until resolved. Independent development can proceed using explicit test fixtures.

### 2.1 Confirmed operational requirements

- Portfolio of 51–100 residential rental properties in North Carolina.
- Rent arrives through checks, cash, and potentially other methods. Receipt, deposit, bank verification, and funds availability are distinct facts.
- Property-level finances must account for fees, owner shares, reserves, approved maintenance invoices, outstanding balances, and monthly statements.
- All payment execution requires explicit property manager approval. AI cannot set authoritative amounts or authorize transfers.
- Preliminary prequalification precedes tours. Formal credit/background screening and income/employment verification follow a completed tour during application processing.
- Protected characteristics and discriminatory proxies cannot determine screening outcomes. Reasonable accommodation requests require a private human review path.
- Maintenance intake includes identity/property, description, exact issue location, onset/frequency, media, contact details, three preferred access windows when practical, entry instructions, and safety concerns.
- Emergencies escalate immediately; contractors are assigned with approval; invoices flow to accounting only after approval.

### 2.2 Proposed defaults

- One management organization at launch, with `organization_id` isolation throughout for future expansion.
- USD only; integer cents for stored money; explicit currency on all financial records. Reject unsupported currencies.
- Display and scheduling timezone `America/New_York` for NC properties; store instants in UTC and keep each property’s IANA timezone. User display preferences may differ.
- Calendar month statements; configurable close dates. Fee accrual timing and agreement terms require explicit configuration.
- Manager controls property policies, listing mapping, approved contractors, fee agreements, reserves, and integrations. No production defaults for fee rates or screening thresholds.
- English conversational MVP with language preference capture and human language assistance; expand supported languages only with reviewed templates and evaluation coverage.
- The manager is the sole required payment approver in MVP. Optional two-person approval can be enabled; do not require a second employee without a business decision.
- Manual capture/import and secure web forms are first-class fallbacks for every external connector.

### 2.3 Blocking configuration behavior

An unconfigured fee agreement yields `CONFIGURATION_REQUIRED`, not a guessed fee or a zero-fee assumption. Missing verified recipient details blocks payment. Missing reviewed screening policy routes to human review. A missing calendar integration allows a requested appointment, but cannot produce a confirmed external booking. Emergency escalation always retains a configured manual fallback.

## 3. Roles and permissions

Authorize server-side by organization, resource relationship, role, and action. UI visibility alone is not authorization. One user may hold multiple scoped roles.

| Role | Allowed | Restricted |
| --- | --- | --- |
| Organization administrator | Manage users, integrations, reviewed policy versions, organizational settings | No implicit payment permission; separate manager capability required |
| Property manager / financial approver | Review receipts, approve invoices, assign approved contractors, approve distributions, review prospects and emergencies | Cannot edit posted journals or bypass cleared-fund checks |
| Accounting staff | Enter receipts, reconcile bank data, draft journals/statements/payout batches | Cannot execute payments unless explicitly assigned approver permission |
| Owner / landlord | Read statements and approved documents for their ownership periods; view payment status | No other owners’ bank details, tenant screening records, or organization-wide ledger |
| Tenant | Submit and view own unit’s maintenance tickets, upload media, provide access windows | Cannot assign contractors, approve expenses, or access other tenants’ data |
| Prospect | Manage own intake, consent and tour requests through scoped links/account | No property tenant data or access to other applicants |
| Contractor | View assigned ticket’s necessary scope/media/access instructions; offer windows, submit completion/invoices | No unrelated tickets, screening records, owner funds, or payment approval |
| AI service identity | Read minimum contextual data, create drafts, request clarification and escalation | No ledger posting, policy publication, assignment approval, payment approval/execution, or final housing decisions |
| Worker/integration identity | Perform narrowly scoped scheduled/provider operations with signed event context | No arbitrary interactive access or unrestricted administrator token |

Require MFA and recent step-up authentication for financial approval, recipient bank changes, and privileged role changes. Log before/after metadata with sensitive values redacted. A user must not approve their own newly changed payee destination in an organization configured for dual control; otherwise require separate out-of-band recipient verification and an explicit manager acknowledgment.

## 4. Financial operations

### 4.1 Domain boundaries and source of truth

The general ledger is an immutable **custodial/trust operations ledger**, distinct from the management company’s corporate accounting. Owner funds and management fees payable are liabilities of this ledger. A management fee is not corporate revenue until accounted for in the company’s separate books. Tenant rent charges/aging are an operational subledger in MVP; creating a rent charge does not also book cash revenue in the custodial ledger.

Every posted transaction has balanced entries, a source event, currency, posting date, property/unit where applicable, beneficial owner where applicable, and reversal linkage. Never edit/delete a posted journal. Corrections use compensating entries approved through accounting permissions. Financial authoritative calculations use Python integers/`Decimal`, never binary floating point or LLM arithmetic.

### 4.2 Receipt and reconciliation workflow

1. Staff records receipt method, amount, payer, property/unit, lease, effective date, reference, and evidence. Issue a numbered receipt, particularly for cash. Store check identifiers with access restrictions; do not expose full account/routing numbers.
2. Post receipt to cash/checks in custody against unapplied receipts. This records physical custody but creates no distributable owner funds.
3. Group receipts in a deposit batch, record deposit slip and destination account, and post custody cash to bank pending. Never label recording a deposit as bank verification.
4. Import/pull bank transactions. Suggest matches using account, amount, deposit reference, and date range; ambiguous matches require a reviewer. Support one deposit to many receipts and many bank events to one batch, with explicit allocation records.
5. Reconcile settled bank credit and establish provider/manager-supported availability evidence. A deposit may be verified yet still held; neither state alone is sufficient to distribute.
6. Move matched bank-pending funds to bank-available when eligibility conditions pass. Only then allocate the corresponding unapplied receipt to property/owner obligations and calculate any agreed fee.
7. Record discrepancies and returns through separate events. Reconciliation does not mutate raw imported bank records.

Receipt lifecycle: `RECORDED → DEPOSITED → BANK_VERIFIED → AVAILABLE → ALLOCATED`. A verified-but-held receipt remains at `BANK_VERIFIED` with `available_at` unset. Direct bank payments can skip physical custody steps using an explicit direct-bank posting template, but still require verification and availability. `VOIDED` is allowed before posting only; after posting use reversal. `RETURNED` references the original and its reversing event. Partial deposits, availability, allocations, and returns use amount-level child records; a header status is derived and must not imply the entire amount is available.

Daily reconciliation compares: (a) bank statement balance adjusted for identified timing items, (b) ledger cash by bank account, and (c) total custodial obligations less properly identified custodial receivables. Resolve differences rather than force-balancing. Every bank line is `UNMATCHED`, `PARTIALLY_MATCHED`, `MATCHED`, or `EXCEPTION`; uniqueness on provider account + external transaction ID prevents reimport duplication. A reconciliation close records statement period, opening/closing balances, outstanding items, reviewer, and evidence hash.

### 4.3 Accounts and posting templates

Proposed account classes (separate bank control accounts per real bank account):

| Code | Account | Normal balance |
| --- | --- | --- |
| 1010 | Cash/checks in custody | Debit asset |
| 1020 | Bank pending/unavailable | Debit asset |
| 1030 | Bank available | Debit asset |
| 1040 | Due from owner / returned-funds recovery | Debit asset |
| 2010 | Unapplied receipts | Credit liability |
| 2020 | Owner funds, unrestricted | Credit liability; debit balance indicates deficit |
| 2030 | Owner reserves, restricted | Credit liability |
| 2040 | Approved contractor payable | Credit liability |
| 2050 | Management company payable | Credit liability |
| 2060 | Declared owner distributions payable | Credit liability |
| 2070 | Security deposits, restricted | Credit liability |

Subledger dimensions include property, owner, lease when relevant, and bank pool. Codes are proposed, not regulatory prescribed chart-of-account numbers.

| Event | Debit | Credit |
| --- | --- | --- |
| Physical receipt recorded | 1010 | 2010 |
| Deposit submitted | 1020 | 1010 |
| Bank credit becomes available | 1030 | 1020 |
| Available rent allocated to owner shares | 2010 | 2020 for each owner |
| Approved fee accrued once | 2020 for responsible owners | 2050 |
| Approved maintenance invoice accrued once | 2020 for responsible owners | 2040 |
| Reserve top-up | 2020 | 2030 |
| Approved reserve release | 2030 | 2020 |
| Owner distribution declared and funds reserved | 2020 | 2060 |
| Provider-confirmed settled payment | 2040, 2050, or 2060 | 1030 |
| Canceled owner distribution before settlement | 2060 | 2020 |

Invoice accrual reduces owner funds even when the contractor has not yet been paid. Paying that invoice later reduces contractor payable and bank cash only; it must not subtract the expense a second time. Security deposits are never allocated as rent or used to fund fees/owner distributions. Accruing an invoice with insufficient owner funds creates an owner deficit and an unfunded payable; it does not authorize spending another property’s cash.

Bank pending and available are accounting buckets for the same physical account and reconcile in aggregate to its statement. Unsettled outbound payments remain in 1030 with immutable reservations until settlement; show a separate outstanding-payment reconciliation schedule. If a provider debits cash earlier than final settlement, use an outbound-clearing asset and a dedicated posting template so bank reconciliation reflects actual cash movement; never pretend the funds remain available.

### 4.4 Deterministic formulas and allocation

For each property and ownership-effective period, define:

- `R`: newly available and allocated rent receipts in cents, excluding refundable deposits and unmatched funds.
- `B_fee`: the agreement-defined fee base (for example collected rent excluding late fees). Membership in this base must be explicit and auditable.
- `r_num / r_den`: configured percentage as a rational value; `F_fixed`: configured fixed fee; use one or both only when the signed agreement permits it.
- `F = round_half_up(B_fee × r_num / r_den) + F_fixed`, subject to explicit agreement caps/minima/proration. Missing agreement blocks accrual. No illustrative percentage is a default.
- `I`: approved invoice amount minus approved credit notes minus already settled/applied amounts. Reject overpayments and duplicate accrual.
- `U_i`: posted unrestricted funds balance for owner `i`, after receipts, fees, invoice accruals, prior distributions, approved adjustments and reserve transfers. Deficits carry forward; do not reset at month-end.
- `T_i`: configured reserve target; `Q_i`: existing restricted reserve balance.
- `top_up_i = min(max(0, T_i - Q_i), max(0, U_i))`.
- `candidate_i = max(0, U_i - top_up_i - other_active_holds_i)`. Prior disbursement declarations already reduce `U_i`; do not subtract them again as holds.
- Final proposed payment is bounded by candidate funds, property beneficial cash backing, bank pool available balance after all active reservations, recipient eligibility, and unresolved reconciliation restrictions.

Allocate shared receipts/fees/expenses with the effective-dated ownership or responsibility rule in the agreement. Shares use integer weights totaling 1,000,000 (one million); allocate `floor(amount × weight / 1,000,000)` and distribute remaining cents by descending fractional remainder, ties by stable owner UUID. Preserve the allocation input/version. Do not round each share independently and lose cents. Ownership changes require a recorded effective-period allocation rule; blocked/ambiguous periods route to accounting review. Never rewrite historical ownership allocations.

Each cash allocation carries beneficial property/owner provenance and bank pool. Available-to-reserve checks occur atomically under property and bank-pool locks. A pooled positive bank balance is not evidence that a particular property has funds. Funds backing accrued fees and contractor liabilities are earmarked for those liabilities; reserves, security deposits, unapplied receipts, deficits and other owners’ balances cannot fund a payout. If liabilities exceed property cash, mark the proposal `INSUFFICIENT_FUNDS` and require an authorized funding/expense-priority decision; do not choose an implicit creditor priority.

### 4.5 Worked example: fully funded monthly close

**Illustrative only:** One property, owner A/B shares 60%/40%, opening available cash $500 represented entirely by restricted reserves ($300/$200). Available rent $4,000; signed illustrative fee 8% of collected rent; approved contractor invoice $450; reserve target $800 total allocated in ownership shares. There are no other balances/holds.

| Calculation | Total | Owner A | Owner B |
| --- | ---: | ---: | ---: |
| New available rent | $4,000.00 | $2,400.00 | $1,600.00 |
| Fee accrual | $320.00 | $192.00 | $128.00 |
| Invoice accrual | $450.00 | $270.00 | $180.00 |
| Unrestricted after accruals | $3,230.00 | $1,938.00 | $1,292.00 |
| Reserve top-up | $300.00 | $180.00 | $120.00 |
| Owner distribution | $2,930.00 | $1,758.00 | $1,172.00 |
| Closing restricted reserve | $800.00 | $480.00 | $320.00 |

Available bank cash before payments is $4,500. Obligations are $2,930 owner distributions + $450 contractor payable + $320 management payable + $800 reserves = $4,500. After all approved payments settle, bank cash and restricted reserves both equal $800. Paying the contractor does not reduce the $2,930 owner distribution again.

### 4.6 Worked exceptions

- **Unverified check:** A recorded $2,000 check creates custody assets and unapplied liability. It contributes $0 to available owner funds even if an AI extracted it correctly or a deposit slip exists.
- **Partial settlement:** A $1,000 deposit has only $700 confirmed available. Allocate at most $700; $300 remains pending/unapplied, with evidence linking each slice.
- **Deficit:** Opening unrestricted balance is −$100; $1,000 available rent, $80 fee, $200 approved invoice, and $100 reserve top-up yield at most $520 owner distribution. The deficit is carried into the calculation.
- **Cent rounding:** Allocate $100.01 at 60%/40%: $60.01 and $40.00 under largest remainder; sum remains $100.01.
- **Returned receipt before allocation:** Reverse the matching pending/custody bank event and unapplied liability, with amounts limited to the original receipt.
- **Returned rent after allocation, before payouts:** Reverse source allocations/fee accruals according to the agreement, cancel affected proposals, reduce property cash, and recalculate. Do not silently release reserves.
- **Returned rent after payouts:** Record actual bank debit against a due-from-owner/recovery asset, open a linked recovery case, freeze affected property disbursements, and route accounting/legal review. Recovery receivables are not available cash. If the return affects pooled trust sufficiency, freeze the affected bank pool pending remediation. Fee reversal liability/recovery follows the configured agreement and accounting review.

### 4.7 Approval, execution, and idempotency

Distribution batch lifecycle:

`DRAFT → VALIDATED → AWAITING_APPROVAL → APPROVED → SUBMISSION_PENDING → SUBMITTED → PARTIALLY_SETTLED / SETTLED`.

Also allow `REJECTED`, `EXPIRED`, `CANCELED`, `FAILED`, and `UNKNOWN`. Each payment item has its own state. A batch with mixed outcomes must display and reconcile item-level outcomes. `UNKNOWN` means provider acceptance is uncertain and prevents new submission until queried/reconciled. A bank return after settlement creates a linked return event; never erase the settlement history.

Validation produces a snapshot hash over amounts, recipient destination versions, source liabilities, agreement/policy versions, reconciliation cutoff, and funding allocations. Explicit approval records the authenticated manager, step-up evidence, timestamp, and snapshot hash. Approval expiry is proposed at 24 hours, configurable. Any amount/destination/source change invalidates approval. Recheck funds, recipient verification, active reservations, and hash immediately before export/submission.

In one database transaction, lock relevant liabilities/property funding/bank pool, validate balances, reserve funds, write the approved command and outbox event, and enforce unique `(organization_id, idempotency_key)`. Workers use stable provider idempotency keys per payment item. Duplicate requests return the original result; same key with a different body returns `409 IDEMPOTENCY_CONFLICT`. Network timeouts require lookup using the same provider key before retry; never generate a new key to escape uncertainty. A database-only retry cannot establish that an external transfer failed.

Instruction exports include batch/item IDs, amounts, currency, tokenized recipient mapping, requested execution date, approval reference and checksum. Access to a provider-specific file containing bank data is audited, encrypted and short-lived. Export does not mark payments submitted or settled. The manager records bank submission reference/evidence, followed by statement reconciliation or verified provider confirmation. Repeated downloads retain the same batch identity and show a duplicate-submission warning.

### 4.8 Accounting invariants and close

1. Every posted journal balances in one currency: sum debits equals sum credits; line amounts are positive integer cents.
2. A source event is posted at most once, including webhook replay and worker retry.
3. No payment exceeds outstanding approved liability, beneficial cash backing, or unreserved eligible bank funds.
4. A receipt cent is allocated at most once; a liability cent is settled/reserved at most once.
5. Posted journals, allocation evidence, approval snapshots, and issued statements are immutable.
6. Security deposits and reserves cannot be distributed without their explicit permitted release workflow.
7. Negative owner balances remain visible and block that owner’s distributions; no cross-property netting without an explicit approved agreement and posting.
8. Ledger control balances reconcile to subledgers; discrepancies block close and affected payments.
9. Closed periods reject backdated postings. Authorized reopen is audited; otherwise post a current-period correction referencing the original period and issue a revised statement.

Monthly close: reconcile bank/custody accounts; resolve or document timing items; accrue approved fees/invoices once; apply reserve rules; review deficits/holds; calculate proposals; approve independently of statement generation; produce versioned statements. Statements include property, owner share/effective period, opening funds, receipts by service/payment period, fee basis/rate, itemized expenses, reserves, outstanding invoices/tenant arrears shown distinctly, distributions and status, closing balances, reconciliation date and statement version. PDFs/HTML derive only from ledger snapshots. Download authorization is checked every time. Revise via a new version, with reason and supersession link.

## 5. Prospect prequalification and tours

### 5.1 Intake and conversation flow

1. Receive marketplace/email/web inquiry, deduplicate provider message ID, disclose automated assistance, and resolve listing ID to property/unit. Ask for a listing/address if ambiguous; do not guess.
2. Explain that this is preliminary intake, a human handles exceptions/final decisions, and formal screening occurs after a tour. Capture communication preferences/consent for each channel.
3. Ask desired move-in date, lease duration, self-reported household income and income period, employment/income source information, occupant count, pets, and objective relevant rental history. Accept nonemployment lawful income sources; do not require employer data when inapplicable.
4. Ask targeted clarification for missing/inconsistent fields. Do not ask for SSN, credit report, medical diagnosis, date of birth, race, religion, nationality, family relationships, or disability information during preliminary intake. Do not ask why someone needs an accommodation.
5. A deterministic policy evaluator returns `PRELIMINARILY_QUALIFIED`, `NEEDS_INFORMATION`, or `HUMAN_REVIEW`, with rule IDs and version. AI phrases the approved explanation without adding criteria.
6. Qualified prospects may choose a tour slot. A prospect who does not meet a configured criterion receives a neutral human-review path; no automatic final denial or final housing recommendation.
7. Once a tour is completed, invite formal application only through a manager-approved process. Formal consumer reports require the legally reviewed consent/permissible-purpose flow. MVP stores an external application reference/status, not raw reports.

Example flow: “Which property are you interested in?” → “When would you like to move in and for how long?” → “What is your approximate total household income and is that monthly or annual? You may include lawful nonemployment income.” → “How many people would occupy the home?” → “Will you have pets? Assistance-animal requests can be reviewed privately by the manager.” → ask missing objective rental-history fields → policy result → offer slots or human follow-up. Collect only approved structured history questions; free-form sentiment is not a screening score.

### 5.2 Policy schema and evaluator

Illustrative shape; numbers below are test fixtures, not adopted rental requirements:

```json
{
  "property_id": "prop_example",
  "version": 3,
  "status": "REVIEWED_ACTIVE",
  "effective_at": "2026-11-01T05:00:00Z",
  "reviewed_by": "user_manager",
  "legal_review_reference": "review_example",
  "rules": [
    {"id": "income", "field": "household_income_monthly_cents", "operator": "gte_rent_multiple", "ratio_numerator": 3, "ratio_denominator": 1, "failure_action": "HUMAN_REVIEW"},
    {"id": "lease", "field": "lease_months", "operator": "in", "values": [12], "failure_action": "HUMAN_REVIEW"}
  ],
  "missing_action": "NEEDS_INFORMATION",
  "accommodation_action": "HUMAN_REVIEW",
  "automatic_final_denial": false
}
```

Use a typed, allowlisted rule DSL; no arbitrary SQL/Python, free-text criteria, or LLM-generated policies. Reject protected characteristics and location/name/language proxies from evaluator inputs. Occupancy rules require specific lawful review and accommodation handling; do not use adult/child composition as a substitute. Rental history questions/rules require review for relevance and fair-housing impacts. Pet policies must separate assistance animals from pets and route accommodation handling privately. Manager policy publishing records review basis, effective date, version and reason.

Normalize declared income to monthly cents using a documented conversion (annual ÷ 12, weekly × 52 ÷ 12, biweekly × 26 ÷ 12; round half up once). Preserve original value/period and label unverified. No external income/employment verification before a completed tour. Missing, disputed, or unreliable information causes clarification/review; it is not converted to zero income or a negative score.

Prospect lifecycle: `NEW → COLLECTING → NEEDS_INFORMATION / HUMAN_REVIEW / PRELIMINARILY_QUALIFIED → TOUR_REQUESTED → TOUR_CONFIRMED → TOUR_COMPLETED → APPLICATION_INVITED`. Also `WITHDRAWN`, `UNRESPONSIVE`, `TOUR_CANCELED`, `NO_SHOW`. Rescheduling returns to a requested/confirmed tour without deleting history. Only a reviewed human action can record final application disposition; it is outside automated preliminary evaluation. Accommodation and complaint flags pause automated qualification/scheduling restrictions as appropriate and create a manager task; staff can arrange a tour following review.

### 5.3 Scheduling rules

- Proposed tours are 30 minutes with 15-minute buffers, property timezone, configurable business hours and minimum notice. These are proposed scheduling defaults, not lease terms.
- Intersect property access availability, agent calendar, occupied-unit permission/notice requirements, and prospect preferences. Contractor access and tours use distinct scheduling contexts.
- Represent requested local date/time plus IANA timezone and resolved UTC instant; reject nonexistent DST times and ask for clarification on ambiguous ones.
- Create expiring local slot holds (proposed 5 minutes). Use database exclusion constraints to prevent overlapping active bookings for the same agent/resource.
- External calendar free/busy checks precede booking. Recheck before confirmation; use a stable external event key. A provider timeout creates `CONFIRMATION_PENDING`, not a promised appointment. Reconcile before retrying.
- Confirm with property, local timezone, instructions, cancellation link, and accessible contact path. Send proposed reminders 24 hours and 2 hours ahead when consent/channel permits; deduplicate by appointment/version/reminder offset.
- Cancellation/rescheduling invalidates old reminder jobs and frees the slot. No-show never automatically denies an application.

Human review queue includes property, minimally necessary intake, rule IDs, missing data, reason, age and assigned reviewer. Reviewers may request information, correct a verified intake error, approve an exception with reason, or route to an accommodation specialist. They cannot silently change the historical policy evaluation. Proposed response target: one business day; this is not an emergency channel.

## 6. Maintenance intake and coordination

### 6.1 Required intake and progressive completion

Create a durable ticket as soon as a legitimate issue is reported, even if incomplete. Verify the tenant/property relationship with authenticated tenant access or a scoped lease-associated link. For unknown callers, create an unverified ticket with restricted disclosure and a manager verification task; never reveal occupancy or private address details merely from a phone number.

Collect and track each field as `PROVIDED`, `UNKNOWN`, `DECLINED`, or `NOT_PRACTICAL`, with clarification reason:

| Field | Required behavior |
| --- | --- |
| Identity and property/unit | Resolve lease relationship or mark verification pending |
| Description | Capture tenant’s words and structured symptoms |
| Exact location | Ask room, fixture/appliance and specific area; allow multiple locations |
| Onset and frequency | Ask first noticed time, continuous/intermittent, change or worsening |
| Photos/videos | Request targeted evidence with safe instructions; record inability/refusal |
| Contact | Verify preferred contact method and suitable callback time |
| Access windows | Request at least three distinct dates/time windows when practical; fewer do not block intake |
| Entry/safety | Capture permission status, pets/access needs, hazards, and practical entry instructions |

Every conversational turn first checks emergency signals, then chooses the highest-value missing question. Ask one or two focused questions per turn, avoiding repeated demands for already answered fields. After proposed three clarification attempts or tenant request, hand off with known gaps; do not loop indefinitely. Show the tenant a structured summary for correction and provide a ticket number.

### 6.2 Issue-specific follow-up playbooks

| Issue | Questions and requested media | Safety/escalation |
| --- | --- | --- |
| Leak/plumbing | Active flow or staining? Source/room? Clean water or sewage? Fixtures affected? When and after what use? Wide room photo and close-up/video of visible leak | Escalate uncontrolled flooding, sewage exposure, water near electricity; no instructions requiring electrical contact |
| HVAC | No heat/cooling or weak airflow? Thermostat displayed setting/error? Rooms affected? Outdoor conditions and onset? Photo of thermostat/error and accessible equipment label | Loss of essential services or dangerous temperature concerns goes to urgent human triage; no universal legal temperature threshold invented |
| Electrical | Which fixtures/outlets? Sparks, smoke, burning smell, buzzing, outage extent? Safe-distance photo only | Smoke/fire/sparking/shock hazard triggers emergency handling; never ask tenant to open panels, touch wires or reproduce danger |
| Appliance | Type, make/model if safely visible, error code, symptom, cycle/time, visible leak? Label and error photo | Gas smell, smoke or major leak overrides routine appliance intake |
| Structural/roof | Which wall/ceiling/area? New or growing crack/sagging? Weather relationship? Wide and close-up photos from a safe position | Collapse risk or rapidly sagging ceiling escalates; never ask tenant to climb or enter unstable areas |
| Pest/mold/moisture | Location, extent, recurrence, moisture source, affected areas? Safe photos; avoid diagnosis | Health/safety concern or severe active moisture routes to human review; no medical diagnosis or remediation promise |
| Lock/security | Exterior/interior door? Can home be secured? Lockout or damaged hardware? Contact/access needs? | Immediate personal danger routes to emergency services guidance; identity verification before sharing entry instructions |

Media requests explain usefulness: “If safe, please send a wide photo showing where the leak is and a close-up of the visible source.” Never require a tenant to cause a fault, dismantle equipment, touch hazards, climb, or remain in danger to obtain evidence.

### 6.3 Emergency behavior

Deterministic trigger rules and AI-assisted classification run in parallel; either may escalate. Examples include fire/smoke, gas odor, sparking, major flooding, structural collapse risk, and immediate threats to life/safety. Uncertain severe reports receive urgent human review. Rules are reviewed by the manager/local counsel; this list is not an exhaustive legal emergency definition.

On trigger: immediately create/update ticket at emergency priority, display a reviewed safety message (“If there is immediate danger, leave the area if safe and call 911 or the appropriate emergency service”), notify the manager/on-call fallback, and stop routine questioning until safety handoff. Do not assert that emergency services were contacted. Do not tell a tenant to operate switches in a suspected gas leak. Essential-service complaints receive urgent triage even if they do not match a life-safety phrase.

Proposed escalation schedule: primary immediate; alternate after 5 minutes without acknowledgement; continued alerts every 10 minutes until acknowledged or manually resolved. Require a configured staffed escalation destination before unattended intake launches. Delivery failure triggers fallback and an operations alert. Acknowledgement means a human accepted responsibility, not that the repair is complete. No ticket may be automatically de-escalated based solely on AI confidence.

### 6.4 Ticket and work-order states

`INTAKE_OPEN → TRIAGE_PENDING → MANAGER_REVIEW → ASSIGNMENT_PENDING → ASSIGNED → SCHEDULING → SCHEDULED → IN_PROGRESS → COMPLETION_REVIEW → COMPLETED → CLOSED`.

Alternative states: `WAITING_TENANT`, `WAITING_PARTS`, `WAITING_APPROVAL`, `CANCELED`, and `REOPENED`. Emergency priority is an orthogonal flag/event, so escalation cannot be lost in a scheduling state. Any open state may receive urgent escalation. Human cancellation requires reason; duplicate tickets are linked, not deleted. Reopening preserves prior completion and invoice history.

- Manager reviews severity, scope and gaps; approves an active, qualified contractor assignment. AI may recommend categories or draft scopes but cannot finalize assignment.
- Contractor sees only assigned scope, relevant media and approved access/contact instructions. Accept/decline events are recorded. Proposed windows are coordinated with tenant; confirmation requires both access authorization and contractor acceptance.
- Availability is not permission to enter. Record explicit entry permission, notice evidence and applicable lease/legal access review. Store door codes separately with time-limited access; never place them in notification subjects/logs.
- Cost estimates exceeding a configured authorization limit require owner/manager authorization as the agreement requires. No invented spending threshold. Emergency spending authority must be configured before relying on it.
- Contractor records work notes, parts, before/after evidence when practical and completion time. Tenant receives a completion follow-up. Proposed reminders after 24 and 72 hours; no response may close an operational ticket after manager review, but never represents tenant acceptance or invoice approval.
- Submitted invoice requires unique contractor invoice reference, service property, ticket/work order, line amounts, tax, total, service dates and document evidence. Manager validates scope/amount and approves. Approval posts a single contractor payable in Module 1; upload/completion alone posts nothing.
- Invoice lifecycle: `DRAFT → SUBMITTED → REVIEW → APPROVED → PARTIALLY_PAID / PAID`; also `DISPUTED`, `REJECTED`, `CREDITED`. Approved values are immutable; corrections use approved credit notes or replacement versions with reversal linkage. Contractor bank changes use the same verification controls as other payees.

### 6.5 Secure media lifecycle

`UPLOAD_REQUESTED → QUARANTINED → SCANNING → READY / REJECTED`. Ticket submission never waits for scanning. Proposed MVP limits: 10 files per ticket initially, 20 MB per image, 200 MB per video, up to 2 minutes per video; configurable after storage/load testing. Allow JPEG/PNG/HEIC and MP4/MOV only through actual file-type verification and safe conversion. Reject executable content, mismatched MIME, archive bombs and unsupported formats with a recoverable message.

Server issues single-object, short-lived signed upload URLs after relationship checks; random object keys include organization/ticket identifiers without tenant names. Validate declared and actual size/checksum, scan in isolated workers, strip location EXIF and unnecessary metadata from shared derivatives, and generate safe thumbnails/transcoded video. Originals remain private/quarantined until ready; if originals are retained for evidence, access is explicitly restricted. No public bucket listing or permanent public links. Each download rechecks authorization and uses a proposed 5-minute signed URL. Attachments from email are subject to the same quarantine. Rejected uploads retain safe error metadata and allow resubmission without losing the ticket.

## 7. Architecture and technology

### 7.1 Recommended stack (proposed)

| Layer | Decision and responsibility |
| --- | --- |
| Web | Next.js + TypeScript; responsive manager console and scoped tenant/prospect/contractor flows |
| API/domain | Python FastAPI, Pydantic validation, SQLAlchemy 2 and Alembic migrations |
| Database | Supported PostgreSQL release; primary source for ledger, state, locks, audit and outbox |
| Async | Redis broker + Celery workers for messaging, media, statements, reconciliation and calendar/provider jobs |
| Media | Private S3-compatible object storage with KMS encryption, lifecycle policies and signed access |
| Authentication | OIDC provider with MFA and short-lived sessions; final vendor unselected |
| AI | Server-side model adapter with JSON-schema outputs, allowlisted tools and redacted context |
| Observability | Structured redacted logs, metrics and distributed trace IDs; error tracker with PII filtering |
| Deployment | Containerized API/workers, managed database/Redis/storage, separate dev/staging/prod |

Next.js never connects directly to the database or banking provider. FastAPI performs authorization, deterministic domain operations and orchestration. Keep modules in one backend initially with explicit financial/prospect/maintenance services; avoid distributed ledger transactions. REST `/v1` contracts are generated into TypeScript types from OpenAPI. Use database migrations and pinned dependency lockfiles at implementation time; choose supported versions then.

### 7.2 Transaction and event architecture

All state changes and their outbox records commit atomically in PostgreSQL. An outbox dispatcher sends to Celery; consumers are at-least-once and deduplicate via inbox/event keys. Redis is never the only record of approvals, financial reservations, emergencies or appointments. Domain events include `ReceiptAvailable`, `InvoiceApproved`, `DistributionApproved`, `PaymentSettled`, `ProspectReviewNeeded`, `TourConfirmed`, `MaintenanceEmergencyDetected`, and `TicketCompleted`.

Webhook ingress verifies signatures/timestamps and stores provider event ID plus raw encrypted payload/reference before processing. Unique inbox constraint handles replay. Out-of-order events are reconciled against provider state; a late “pending” event cannot regress settled payment status. Jobs use exponential backoff with jitter and a dead-letter queue; financial unknown results require reconciliation instead of blind retry.

Use optimistic version fields/`If-Match` for routine edits. Financial reservation/posting uses database transactions with deterministic lock ordering and serializable transactions or explicit row locks plus constraints. Retry serialization failures with bounded jitter. Appointment resources use PostgreSQL range exclusion constraints. Database UTC time is authoritative for expiry.

### 7.3 Interfaces and accessible UX

Manager dashboard shows reconciliation exceptions, approvals, urgent tickets, prospective tenant review queue and upcoming appointments. Every financial detail has a source/evidence link and deterministic breakdown. Tenant flows support mobile uploads, resumable/failed upload retry, text-only intake and accessible contact alternatives. Target WCAG 2.2 AA for core journeys; status updates cannot depend on color alone. Show local timezone explicitly for appointments and disclose preliminary/unverified screening information.

## 8. PostgreSQL schema and relationships

### 8.1 Conventions and enforcement

Use UUID primary keys; every business table has `organization_id`, `created_at`, `updated_at`, and actor/source metadata as appropriate. Foreign keys use `(organization_id, id)` composite references to prevent cross-organization relationships. Mutable aggregates have `version bigint`. Money is `bigint` cents plus `currency char(3)` constrained to USD in MVP; rates use integer numerator/denominator or fixed-scale `numeric`, never float. Timestamps are `timestamptz`; local requested times retain timezone separately. Critical structure uses typed columns; JSONB is for versioned policy/snapshot/evidence payloads with schema validation.

### 8.2 Core entities

| Table | Key columns, relationships and constraints |
| --- | --- |
| `organizations` | Name, settings, default timezone; no production financial defaults |
| `users`, `role_grants` | OIDC subject unique per issuer, organization/resource scope, role, active dates |
| `parties`, `contacts` | Person/company identity, owner/tenant/contractor roles; encrypted contact values and consent references |
| `properties`, `units` | Address, timezone, unit count; unit belongs to one property |
| `ownership_periods`, `ownership_shares` | Property, effective daterange, agreement version; owner/weight rows sum to 1,000,000; overlapping periods prohibited |
| `leases`, `lease_parties` | Unit, lease dates, tenant associations, agreed rent, rent charge schedule; prevent invalid overlapping exclusive occupancy leases unless explicitly modeled |
| `agreements`, `fee_rules`, `reserve_rules` | Signed document reference, effective dates, fee base/rate/fixed terms, responsibility rules, reserve target/release authority; immutable published versions |
| `bank_accounts`, `payee_destinations` | Provider tokens, masked details, pool/type, verification state, destination version; no plaintext credentials |
| `receipts`, `receipt_evidence` | Method, payer, lease/unit/property, total cents, source/reference, custody dates, state; encrypted evidence references |
| `deposit_batches`, `deposit_items` | Bank account, slip, date, receipt slices; positive amount and sum bounds |
| `bank_transactions`, `bank_matches` | Provider ID unique by account, signed amount, dates, immutable import hash; match slices to deposits/payments |
| `availability_events`, `receipt_allocations` | Verified available amount/evidence; allocation to owner/property, ownership/fee versions; cumulative amounts bounded by available source |
| `ledger_accounts`, `journal_entries`, `journal_lines` | Account class/currency, source unique, posting date, reversal reference; lines carry bank/property/owner/lease/liability dimensions |
| `funding_lots`, `fund_reservations` | Source available cash provenance, property/owner/pool, liability/payment target, amount, active/released/consumed status; prevent overreservation under lock |
| `rent_charges`, `charge_allocations` | Operational tenant charges, due dates, receipt application, outstanding balance; independent of custodial ledger recognition |
| `reconciliations`, `reconciliation_items`, `period_closes` | Bank statement balances, matched lines/timing items, reviewer, close version/evidence; immutable approved closes |
| `distribution_batches`, `payment_items` | Snapshot/hash, approval/expiry, status; recipient version, liability reference, amount, provider key, external reference; uniqueness by source obligation and payment slice |
| `approvals`, `payment_events` | Actor, action, reason, authenticated step-up, snapshot hash; immutable provider/manual event history |
| `statements` | Owner/property/period, version, snapshot hash, artifact, superseded ID; unique scope/period/version |
| `listings`, `inquiries` | External listing mapping to unit/property, provider inquiry/message IDs, channel; unique source IDs |
| `prospects`, `prospect_intakes` | Contact reference, target listing, state; typed collected fields, missing statuses, income period/original/normalized value, unverified flag |
| `screening_policies`, `policy_evaluations` | Property/version/typed rule JSON, review metadata; immutable evaluation input hash, rule outcomes, result |
| `human_reviews`, `accommodation_cases` | Reason, assignee, due date, resolution; accommodation details separately restricted with minimal shared status |
| `resources`, `appointments`, `appointment_participants` | Resource calendar mapping, UTC range, timezone, type, property, subject, status, external event key, permission evidence, hold expiry |
| `maintenance_tickets`, `intake_fields` | Tenant/lease/unit, symptoms/category/location/onset/frequency, priority, verification, state, completion gaps and reasons |
| `media_objects` | Ticket, private key, MIME, bytes, checksum, scan status, derivative refs, retention/legal-hold metadata |
| `contractor_profiles`, `assignments`, `work_orders` | Approved status, trade/service area, credentials verification dates, ticket/contractor, acceptance, scope, estimate, authorization and access approval |
| `invoices`, `invoice_lines`, `credit_notes` | Work order/property/contractor, normalized invoice number, service dates, tax/total, approval version, payable journal ref; unique contractor + normalized invoice number with audited duplicate override |
| `conversations`, `messages` | Subject/context, channel, external IDs, consent, redacted content, delivery and escalation metadata |
| `notification_jobs`, `delivery_attempts` | Recipient/channel/consent, dedup key, scheduled time, appointment version, provider ID, result |
| `audit_events`, `outbox_events`, `inbox_events`, `idempotency_records` | Append-only event metadata; dispatch/retry state; unique provider IDs and request keys/body hashes |

### 8.3 Essential database constraints

```sql
-- Illustrative DDL fragments, to be completed by migrations.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE journal_lines (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  journal_id uuid NOT NULL,
  account_id uuid NOT NULL,
  side text NOT NULL CHECK (side IN ('DEBIT', 'CREDIT')),
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  currency char(3) NOT NULL CHECK (currency = 'USD'),
  property_id uuid,
  owner_id uuid,
  UNIQUE (organization_id, id)
  -- Composite FKs to journal/account/property/owner are required in full DDL.
);

-- On an appointments table with resource_id, starts_at, ends_at, and status:
-- EXCLUDE USING gist (
--   organization_id WITH =, resource_id WITH =,
--   tstzrange(starts_at, ends_at, '[)') WITH &&
-- ) WHERE (status IN ('HELD', 'CONFIRMATION_PENDING', 'CONFIRMED'));
```

Only a restricted posting function/service role may transition a journal from draft to posted. A deferred constraint trigger verifies at least two lines, balanced sums, consistent currency, valid required dimensions, valid source uniqueness and an open posting period. Triggers/privileges reject mutation of posted headers/lines. Enforce ownership-sum validity at publication with deferred checks under a property lock. Reservation/allocation sum constraints require transactional locking and posting-service enforcement; a row `CHECK` alone cannot enforce cross-row sums.

Apply PostgreSQL row-level security for organization isolation and restricted portal reads, with API authorization as an additional layer. Worker connections must set validated organization context per transaction and never leak session context through pooling. Financial rows are retained/voided by event, not soft-deleted. Index `(organization_id, property_id, posting_date)`, source IDs, queue state/due dates, message IDs, invoice references, and appointment ranges. Restrict JSON indexes to measured queries. Store credentials only in a secrets manager, not settings JSON.

## 9. REST API contracts

### 9.1 Global conventions

Base `/v1`; JSON UTF-8; bearer/session authentication except signed provider callbacks and scoped public intake tokens. Example IDs such as `prop_example` are readable placeholders for UUIDs, not production ID syntax. All responses include `request_id`; list responses use opaque cursor pagination (`limit` default 50, max 200). Money is integer cents and explicit currency; dates use ISO 8601. Organization comes from authenticated context, not a trusted request-body field.

Mutating financial commands require `Idempotency-Key`; optimistic edits require `If-Match` version. `POST` creation normally returns 201, reads/decisions 200, queued provider operations 202, deletes/cancellations 200 with event representation. No HTTP DELETE for posted financial records. Authorization yields 403 or 404 for inaccessible resource existence; validation 422, state/version/idempotency conflict 409, rate limiting 429 with `Retry-After`, dependency failure 503. Authenticate callbacks before accepting data.

Error envelope:

```json
{
  "error": {
    "code": "INSUFFICIENT_AVAILABLE_FUNDS",
    "message": "This property does not have enough eligible funds for this payment.",
    "details": {"requested_cents": 120000, "eligible_cents": 90000},
    "retryable": false
  },
  "request_id": "req_example"
}
```

### 9.2 Resource and command inventory

| Method and path | Purpose / permissions / special behavior |
| --- | --- |
| `GET /me` | Current scoped roles and capabilities |
| `GET, POST /properties` | Scoped listing / administrator creation |
| `GET, PATCH /properties/{id}` | Scoped read / versioned manager edit |
| `POST /properties/{id}/ownership-periods` | Publish validated effective ownership, manager/accounting |
| `POST /properties/{id}/agreements` | Create reviewed agreement version, manager |
| `POST /receipts` | Record payment evidence and custody/direct-bank path, accounting |
| `GET /receipts/{id}` | Amount-level custody/deposit/verification/allocation state |
| `POST /deposit-batches` | Link receipt slices and create pending deposit, accounting |
| `POST /bank-imports` | Upload validated CSV/provider import; asynchronous parsing |
| `GET /bank-transactions` | Unmatched/matched reconciliation queue |
| `POST /bank-matches` | Explicit reviewed match allocations, accounting |
| `POST /receipts/{id}/availability` | Verify availability with bank evidence, accounting; no AI |
| `POST /receipts/{id}/allocations` | Deterministic eligible allocation, accounting |
| `POST /receipts/{id}/returns` | Record actual return/evidence and correction workflow |
| `POST /reconciliations`, `POST /reconciliations/{id}/close` | Draft/approve reconciliation with difference checks |
| `GET /properties/{id}/ledger` | Paginated journal/read-only balance breakdown |
| `POST /journals/{id}/reversals` | Controlled correction with reason; no arbitrary AI posting |
| `POST /distribution-batches` | Calculate draft from eligible liabilities and agreements |
| `POST /distribution-batches/{id}/validate` | Recompute snapshot and funding checks |
| `POST /distribution-batches/{id}/approve` | Explicit financial approver + step-up + snapshot hash |
| `POST /distribution-batches/{id}/export` | Approved instruction artifact; retain batch identity |
| `POST /distribution-batches/{id}/submit` | Approved live adapter only; 202, stable item keys |
| `POST /payment-items/{id}/submission-evidence` | Record manual bank submission reference |
| `POST /payment-items/{id}/settlement-evidence` | Verified settlement evidence and reconcile; permission-gated |
| `POST /distribution-batches/{id}/cancel` | Cancel eligible items; query uncertain provider items first |
| `POST /statements`, `GET /statements/{id}` | Generate versioned statement / authorized read |
| `POST /inquiries` | Authorized connector or scoped web inquiry intake |
| `POST /prospects/{id}/messages` | Collect missing intake via scoped access, no authoritative screening by LLM |
| `PATCH /prospects/{id}/intake` | Typed correction with source and version |
| `POST /prospects/{id}/evaluate` | Deterministic reviewed policy evaluation |
| `POST /properties/{id}/screening-policies` | Publish validated reviewed policy, authorized manager |
| `GET /human-reviews`, `POST /human-reviews/{id}/resolve` | Human-only exception queue and reasoned resolution |
| `GET /tour-slots?property_id=...` | Eligible scoped slots with timezone and expiry |
| `POST /appointments/holds` | Atomic time-bound hold for permitted resource |
| `POST /appointments/{id}/confirm` | Access/calendar checks; 202 while provider pending |
| `POST /appointments/{id}/reschedule`, `POST /appointments/{id}/cancel` | Versioned change with reminder invalidation |
| `POST /appointments/{id}/complete` | Staff-attested tour/repair completion |
| `POST /prospects/{id}/application-invitations` | Manager-approved, requires completed tour |
| `POST /maintenance-tickets` | Persist incomplete ticket; emergency checks immediately |
| `GET, PATCH /maintenance-tickets/{id}` | Scoped read / typed intake updates |
| `POST /maintenance-tickets/{id}/messages` | Follow-up intake and safety checks |
| `POST /maintenance-tickets/{id}/media-uploads` | Authorized quarantine upload URL |
| `POST /media/{id}/complete` | Verify object/checksum and queue scanning |
| `GET /media/{id}/download` | Ready-only authorized short-lived URL |
| `POST /maintenance-tickets/{id}/escalations` | Immediate durable escalation |
| `POST /escalations/{id}/acknowledge` | Human responsibility acknowledgment |
| `POST /maintenance-tickets/{id}/assignments` | Manager-approved contractor/work-order assignment |
| `POST /assignments/{id}/respond` | Assigned contractor acceptance/decline |
| `POST /work-orders/{id}/completion` | Contractor evidence and review request |
| `POST /maintenance-tickets/{id}/transitions` | Role/state/guard checked lifecycle change |
| `POST /invoices`, `GET /invoices/{id}` | Contractor/accounting invoice submission/read |
| `POST /invoices/{id}/approve` | Manager approval and single payable accrual |
| `POST /invoices/{id}/credit-notes` | Approved correction; preserve original |
| `POST /webhooks/{provider}` | Signed/replay-protected inbox; return 202 quickly |

### 9.3 Financial payload examples

`POST /receipts`, accounting permission, `Idempotency-Key: receipt-example-001`:

```json
{
  "property_id": "prop_example",
  "unit_id": "unit_example",
  "lease_id": "lease_example",
  "payer_party_id": "tenant_example",
  "method": "CHECK",
  "amount_cents": 200000,
  "currency": "USD",
  "received_at": "2026-11-06T15:00:00Z",
  "reference": "masked-check-reference",
  "service_period": "2026-11",
  "evidence_media_ids": ["document_example"]
}
```

201 response:

```json
{
  "id": "receipt_example",
  "status": "RECORDED",
  "amount_cents": 200000,
  "available_cents": 0,
  "allocated_cents": 0,
  "currency": "USD",
  "journal_id": "journal_custody_example",
  "version": 1,
  "request_id": "req_example"
}
```

`POST /distribution-batches` request and draft response:

```json
{"property_ids": ["prop_example"], "as_of": "2026-11-30", "include": ["OWNER", "CONTRACTOR", "MANAGEMENT"], "currency": "USD"}
```

```json
{
  "id": "batch_example",
  "status": "DRAFT",
  "items": [
    {"id": "pay_a", "kind": "OWNER", "recipient_id": "owner_a", "amount_cents": 175800, "destination_version": 2},
    {"id": "pay_b", "kind": "OWNER", "recipient_id": "owner_b", "amount_cents": 117200, "destination_version": 1},
    {"id": "pay_c", "kind": "CONTRACTOR", "recipient_id": "contractor_example", "liability_id": "invoice_example", "amount_cents": 45000, "destination_version": 1},
    {"id": "pay_m", "kind": "MANAGEMENT", "recipient_id": "manager_company", "amount_cents": 32000, "destination_version": 1}
  ],
  "total_cents": 370000,
  "currency": "USD",
  "retained_reserves_cents": 80000,
  "blocking_errors": [],
  "request_id": "req_example"
}
```

After validation, `POST /distribution-batches/{id}/approve` with recent step-up session:

```json
{"snapshot_hash": "sha256:example-validation-hash", "decision": "APPROVE", "reason": "Reviewed reconciled November distributions"}
```

200 returns `status: APPROVED`, approval ID, exact snapshot hash and expiry. It does not submit money. `submit` returns 202 with item states and a status URL; settled amounts derive from verified provider/reconciliation evidence.

### 9.4 Prospect and scheduling payload examples

`POST /prospects/{id}/evaluate` has no caller-supplied authoritative result; it references intake version. Example response:

```json
{
  "prospect_id": "prospect_example",
  "intake_version": 4,
  "policy_version": 3,
  "result": "NEEDS_INFORMATION",
  "missing_fields": ["income_period", "lease_months"],
  "rule_results": [{"rule_id": "income", "result": "UNKNOWN"}],
  "formal_screening_permitted": false,
  "request_id": "req_example"
}
```

`POST /appointments/holds`:

```json
{
  "kind": "TOUR",
  "prospect_id": "prospect_example",
  "property_id": "prop_example",
  "resource_id": "agent_example",
  "starts_at": "2026-11-10T15:00:00-05:00",
  "ends_at": "2026-11-10T15:30:00-05:00",
  "timezone": "America/New_York"
}
```

201 returns hold ID, UTC times, `expires_at`, version and local timezone. A simultaneous conflicting hold returns 409 `SLOT_UNAVAILABLE`; a review-required prospect returns 409 `HUMAN_REVIEW_REQUIRED` unless a recorded human exception permits booking.

### 9.5 Maintenance and invoice payload examples

`POST /maintenance-tickets` accepts partial information:

```json
{
  "unit_id": "unit_example",
  "description": "Water drips below the kitchen sink when the tap runs.",
  "location": "Kitchen, cabinet under sink",
  "onset": "2026-11-05 evening",
  "frequency": "During tap use",
  "contact_id": "contact_example",
  "media_status": "UNKNOWN",
  "preferred_access_windows": [],
  "entry_permission": "NOT_YET_GRANTED",
  "safety_concerns": "No visible nearby electrical devices"
}
```

201 response:

```json
{
  "id": "ticket_example",
  "status": "INTAKE_OPEN",
  "priority": "ROUTINE_REVIEW_PENDING",
  "missing_fields": ["media_or_limitation", "access_windows_or_limitation"],
  "next_questions": [
    "If safe, can you send a wide photo and close-up of the visible leak?",
    "Is water pooling or continuing to flow when the tap is off?"
  ],
  "request_id": "req_example"
}
```

`POST /maintenance-tickets/{id}/media-uploads` request:

```json
{"filename": "sink.jpg", "content_type": "image/jpeg", "size_bytes": 2400000, "sha256": "example-checksum"}
```

201 returns media ID, signed `upload_url`, required headers, expiry and `QUARANTINED` destination. Completion queues scanning; no ready download until scan/conversion passes.

`POST /invoices`:

```json
{
  "work_order_id": "work_example",
  "property_id": "prop_example",
  "contractor_id": "contractor_example",
  "invoice_number": "INV-1042",
  "currency": "USD",
  "lines": [{"description": "Approved sink repair", "quantity": "1", "unit_price_cents": 45000, "line_total_cents": 45000}],
  "tax_cents": 0,
  "total_cents": 45000,
  "document_media_id": "invoice_document_example"
}
```

Backend recalculates quantity/line/tax totals deterministically and rejects mismatches. Submission returns `SUBMITTED`, no payable journal. Approval verifies authorization/work evidence, then returns `APPROVED` and `payable_journal_id` once. AI-extracted quantities/taxes remain drafts requiring review.

## 10. AI architecture and tool permissions

### 10.1 Agents and execution boundary

Implement bounded conversational workflows, not an unrestricted autonomous process. A routing service selects a prospect or maintenance assistant; a finance explanation assistant receives read-only deterministic calculation results. Each turn has a trace ID, tenant/organization context, allowed tools, token/time budget and output schema. Proposed limit: five tool calls/turn and a 20-second interactive deadline; exceedance returns a useful saved-state/human-handoff message. Model vendor/model choice remains configurable and is not a confirmed banking or screening provider.

Untrusted email, uploads, tenant messages and retrieved documents are data. They cannot override system instructions, grant permissions or introduce tool names. Financial document extraction produces typed candidate fields with source-page references/confidence; a human confirms before authoritative posting. Models never see raw bank credentials, full consumer reports or unnecessary protected information.

| Allowed tool | Boundary |
| --- | --- |
| `get_public_property_details` | Only listing-approved information |
| `get_own_intake`, `save_intake_draft` | Scoped prospect data; validated fields only |
| `evaluate_prequalification` | Calls deterministic reviewed-policy service; cannot supply outcome |
| `list_available_slots`, `request_tour_hold` | Service enforces eligibility, access rules and conflicts |
| `create_maintenance_ticket`, `update_ticket_intake` | Persist tenant report; cannot clear emergency flags |
| `request_media_upload` | Scoped quarantine links with reviewed safety wording |
| `escalate_to_manager` | Durable queue; emergency path available without completeness |
| `draft_contractor_scope` | Draft only; manager assignment required |
| `get_calculation_explanation` | Read authorized ledger calculation snapshot, no new amounts |
| `draft_message` | Channel consent, approved templates and dispatch policy enforced by service |

Forbidden tools/capabilities: raw SQL, arbitrary code execution, unrestricted internet requests, ledger posting/reversals, payment approval/submission, recipient destination mutation, policy publishing, final housing decision, formal report purchase before completed tour, contractor assignment approval or legal/medical diagnosis.

### 10.2 Message controls and reliability

Routine clarification/reminders may be dispatched automatically within consent and reviewed policy. Financial/contractor approval requests and housing dispositions require the appropriate human workflow. Safety messages use reviewed templates that can render without an LLM. Persist conversation turns before sending. Tool services repeat authorization and validation; a model-generated “approved” string is never an approval record.

Maintain versioned prompts, playbooks, policy schemas and evaluation datasets. Record model/prompt/tool versions, input/output hashes, decision traces and redacted snippets according to retention settings. Evaluate prompt injection, hallucinated amounts, discriminatory questions, accommodation routing, emergency recall, excessive questioning and missing-media handling before prompt/model changes. A model outage degrades to structured forms, deterministic safety checks and human review; accounting and emergency alerting remain operational.

## 11. Integrations

| Integration | Required behavior and fallback |
| --- | --- |
| Banking/ACH | Provider unselected. Tokenized recipients, verification, transaction imports, balances/availability evidence, idempotent transfers if enabled, status lookup, signed webhooks and returns. Fallback: reviewed CSV imports and approved instructions/export with submission evidence |
| Zillow/marketplaces | Do not assume public API access or scrape in violation of terms. Use approved partner API if available, consented email forwarding/parser, or listing-linked web intake. Preserve listing IDs/source attribution; ambiguous mapping routes to staff |
| Email/SMS | Provider unselected. Consent/opt-out, signed delivery callbacks, deduplication, retry/fallback, sender identity and secure links. SMS is not a channel for bank data or sensitive screening documents |
| Calendar | Google/Microsoft or selected provider adapter; free/busy, stable event keys, cancellation and change reconciliation. Fallback is manager-confirmed scheduling, explicitly pending until confirmed |
| Formal screening | Separate post-tour application provider/workflow, legally reviewed authorization/permissible purpose and human disposition. No automatic report ordering in MVP |
| Object storage/scanner | Private storage, malware scan, image/video normalization, signed URL expiry and audit |
| OIDC and secrets | Scoped identities/MFA, key rotation, environment separation, revocation and vendor outage behavior |

Each adapter must expose capability flags (`can_import`, `can_verify_available`, `can_submit`, `can_query_by_key`) and contract tests. Never infer an unsupported capability from the provider name. Verify webhook signatures against raw request bytes, enforce replay windows where supported and rotate secrets. Scheduled reconciliation recovers missed callbacks. Sandbox transactions and return scenarios must pass before live financial activation.

## 12. Security, privacy, and regulatory considerations

This document defines engineering controls, not a legal opinion. An NC-qualified attorney and appropriate real-estate/accounting professional must validate the actual business model, licensing, trust handling, leases and policies before production. Avoid hard-coding a statutory rule from a summary without confirming current applicability and exceptions.

### 12.1 North Carolina and federal review areas

- **NC property management/trust accounting:** Review licensing applicability under N.C. General Statutes Chapter 93A and North Carolina Real Estate Commission rules, including 21 NCAC 58A .0116–.0118 as applicable. Confirm required account types, deposit timing, custodial records, reconciliations, permitted disbursements and retention with a qualified reviewer. Model custody/deposit/availability dates separately so actual rules can be enforced.
- **Tenant Security Deposit Act:** N.C.G.S. Chapter 42, Article 6 (§§ 42-50 et seq.). Security deposits remain a restricted category, with bank/trust/bond, notice, refund and deduction obligations reviewed before enabling full deposit administration. Never treat them as rent.
- **Habitability and repairs:** N.C.G.S. § 42-42 and applicable housing/building codes require legal review of repair obligations, essential services and emergency procedures. AI cannot promise that a statutory repair deadline has been met. No general right of entry or fixed notice period is invented; consult the lease, governing law and emergency circumstances.
- **Fair housing:** Federal Fair Housing Act, including 42 U.S.C. §§ 3604 and 3617, North Carolina Fair Housing Act (Chapter 41A), and applicable local/other federal protections. Review consistent criteria, occupancy limits, assistance animals, accommodations, retaliation protections and disparate effects. Property-specific policies need documented lawful rationale and review.
- **FCRA:** 15 U.S.C. § 1681 et seq.; formal consumer report permissible purpose, required authorization/notices as applicable, secure handling and legally reviewed adverse-action procedures. A report-based housing action, including conditional terms, must enter human/legal review; preliminary intake must not bypass these obligations.
- **Privacy and communications:** Review NC identity-theft/breach provisions (Chapter 75, Article 2A), relevant other state laws for users served, TCPA/SMS and CAN-SPAM requirements as applicable. Record consent, channel purpose, opt-out and deletion/access requests; do not claim compliance based only on having a checkbox.
- **Payments:** Validate bank/ACH provider requirements, authorization and return handling, applicable Nacha rules and any required financial regulatory analysis. Do not assume the platform may custody or transmit funds merely because it can produce an instruction file.

Primary reference starting points, to be checked for current text during production review:

- [NC General Statutes Chapter 93A](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByChapter/Chapter_93A.html)
- [NC General Statutes Chapter 42](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByChapter/Chapter_42.html)
- [NC General Statutes Chapter 41A](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByChapter/Chapter_41A.html)
- [NC General Statutes Chapter 75](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/ByChapter/Chapter_75.html)
- [North Carolina Real Estate Commission](https://www.ncrec.gov/)
- [HUD fair housing information](https://www.hud.gov/program_offices/fair_housing_equal_opp)
- [FTC Fair Credit Reporting Act information](https://www.ftc.gov/legal-library/browse/statutes/fair-credit-reporting-act)

These links identify review sources; this specification does not assert that a live legal review has occurred.

### 12.2 Technical controls

- TLS in transit; managed encryption at rest for database, backups and objects. Field-level encryption/tokenization for bank/contact/sensitive identity information; keys in KMS/secrets manager with rotation.
- No SSN/full credit report collection in preliminary flows. Separate confidential accommodation records from ordinary conversations and contractor views. Redact medical details volunteered in free text from downstream context where practical.
- OIDC, MFA/step-up, least-privilege service identities, expiring scoped portal links, revocable sessions, CSRF protection for cookie sessions, strict CORS, secure cookies and content security policy.
- Signed uploads, server-side file validation, malware isolation, URL expiry, download audit, no public storage ACLs. Block SSRF from user-supplied URLs and prohibit model-directed fetches.
- Rate limits by identity/IP/channel, abuse throttling without blocking emergency handoff, attachment quotas and operational alerts. Proposed default authenticated API limit 120 requests/minute, tuned by route/role; uploads and provider callbacks have separate limits.
- Append-only audit trail with actor/service, action, target/version, reason, request/trace ID and timestamp. Export to tamper-evident retention storage; do not log secrets, door codes, signed URLs or unnecessary PII.
- Proposed recovery targets: RPO ≤15 minutes, RTO ≤4 hours for core database services. Encrypted point-in-time backups and quarterly restore exercises; tested key recovery.
- Retention is category-based, configurable and legally reviewed before production. Launch configuration must specify accounting/audit, prospect messages, accommodation records, maintenance evidence, originals/derivatives and provider data retention. Legal holds suspend deletion. Avoid an invented universal retention duration. Redact/delete eligible PII without rewriting immutable financial evidence; preserve minimal required audit references.
- Payment destination updates require step-up, out-of-band verification and notification to established contact details; a changed email alone is not evidence of bank ownership.

## 13. Errors, exceptions, and operations

| Scenario | Required response |
| --- | --- |
| Duplicate bank webhook, invoice or transfer request | Unique keys + inbox/idempotency records; return prior result, no additional journal/payment |
| Missing agreement or uncertain ownership period | Block calculation/affected distribution; show missing configuration and reviewer task |
| Bank return or negative balance | Record actual event, cancel/freeze affected proposals, open recovery/reconciliation case |
| Provider timeout after submission | Mark `UNKNOWN`; query/reconcile same provider key; keep funds reserved |
| Partial payment failure | Preserve settled items; retry only definitively failed eligible items with correct idempotency semantics and reapproval if inputs changed |
| Bank mismatch | Exception queue; prohibit forced balancing and affected payouts until reviewed |
| Prospect ambiguous property | Ask property/listing clarification, preserve inquiry; do not leak tenant information |
| Accommodation/discrimination complaint | Restrict sensitive details, create urgent human review; no automatic adverse outcome |
| Conflicting calendars/DST ambiguity | Refuse false confirmation, ask/offer alternatives, release expired holds |
| Tenant has no camera or only one access window | Record limitation, persist ticket, continue practical scheduling/human support |
| Suspected emergency with incomplete identity | Escalate and provide reviewed safety guidance immediately; verify identity in parallel |
| Upload malware/failure | Quarantine/reject safely, retain ticket, request alternate evidence or human visit |
| Contractor unavailable/no-show | Notify manager/tenant, retain evidence, seek newly approved assignment/appointment |
| Unapproved cost/invoice dispute | Pause payable accrual/payment, preserve ticket/work history and route manager |
| Email/SMS/calendar outage | Durable queued status with fallback; distinguish queued from delivered/confirmed |
| LLM outage or unsafe response | Structured form/template fallback and human queue; no effect on financial permissions |
| Redis loss/worker restart | Rebuild pending work from PostgreSQL outbox; do not lose reservations/emergencies |

Operations console must show dead-letter jobs, oldest emergency acknowledgement age, webhook lag, reconciliation differences, stale unknown payments, expiring approvals and unassigned tickets. Alerts route to configured staff, with runbooks for payout freeze, webhook outage, data breach, compromised recipient, failed restore and emergency notification failure. Support a manager-controlled kill switch for automatic outbound messaging, calendar booking and payment submission independently; manual ticket intake and ledger reads remain available.

## 14. Performance and scalability

Proposed initial sizing: 100 properties, up to 300 units, 1,000 active tenant/prospect contacts, 20 concurrent staff/portal sessions, 10,000 messages/month and 1,000 maintenance files/month. These are planning assumptions, not confirmed portfolio facts.

- Ordinary API reads/writes: p95 ≤500 ms excluding external providers and large media; paginated ledger views p95 ≤1 second under initial sizing.
- Persist inbound message/ticket and emergency event before asynchronous processing; webhook acknowledgment p95 ≤2 seconds.
- Interactive AI reply target p95 ≤15 seconds, with progress/saved-state fallback at deadline. Deterministic emergency path does not wait for AI.
- Monthly proposal for 100 properties: ≤60 seconds in background; statement generation ≤5 minutes, with progress and per-property failure isolation.
- Emergency event enqueue ≤5 seconds; external dispatch attempt ≤30 seconds when provider operational. Alert on missed deadline; do not equate dispatch with delivery/acknowledgement.
- Core app proposed availability target 99.5% monthly, excluding clearly announced maintenance; financial correctness never trades off against latency targets.
- Scale API/workers independently, stream uploads directly to object storage, bound video conversion concurrency and database connection pools. Paginate history and archive cold records without losing audit accessibility. Validate at 10× planned transaction/message volume before broader rollout.

## 15. Verification and automated tests

Implement tests alongside application development; this specification task creates no application/tests. Use pytest/property-based testing for domain accounting, PostgreSQL integration tests for locks/RLS/triggers, contract fixtures for providers, and Playwright for web journeys. Do not rely on mocks for journal balance/concurrency or external-transfer uncertainty semantics.

### 15.1 Financial test matrix

| ID | Setup/action | Expected result |
| --- | --- | --- |
| FIN-01 | Post $2,000 check; deposit without availability evidence | No owner allocation/distribution eligibility; custody/pending and unapplied balance |
| FIN-02 | Execute worked $4,000 rent example | Fee 32,000 cents; invoice 45,000; owners 175,800/117,200; closing reserve/bank 80,000 |
| FIN-03 | Allocate 10,001 cents at 60/40 | 6,001 + 4,000; deterministic for replay |
| FIN-04 | Re-run receipt/invoice approval webhook and worker 100 times | One source journal and one payable only |
| FIN-05 | Two workers reserve same $900 against $1,200 total requests | At most $900 reserved; loser gets conflict/insufficiency |
| FIN-06 | Pooled bank has $10,000 but target property $100 | Reject $200 payment; no use of another property’s funds |
| FIN-07 | Approved batch destination/version changes before submit | Approval invalid; no provider call |
| FIN-08 | Timeout occurs after provider accepts transfer | State unknown; lookup same key; one transfer after recovery |
| FIN-09 | Pay accrued $450 contractor invoice | Debit payable/credit bank only; owner expense not deducted again |
| FIN-10 | Return check after owner distribution settles | Actual bank debit and recovery asset, freeze, no fictitious available funds |
| FIN-11 | Try unbalanced/foreign-currency/closed-period journal or edit posted line | Database/service rejection with no partial posting |
| FIN-12 | $1,000 deposit only $700 available | Allocate at most $700; $300 remains unavailable/unapplied |
| FIN-13 | Existing owner deficit and reserve target example | Maximum owner proposal 52,000 cents |
| FIN-14 | Security-deposit cash present; rent absent | No owner/fee payment eligibility from deposit |
| FIN-15 | One of four payment items fails after three settle | Preserve three settlements, no full-batch replay |
| FIN-16 | Reimport bank CSV; change body under same idempotency key | No duplicate bank rows; conflicting request returns 409 |
| FIN-17 | Ownership changes midperiod | Use configured effective-period rule; historical entries unchanged |
| FIN-18 | Export approved batch twice | Same batch/item identities, no settlement recorded, audit downloads |
| FIN-19 | Outstanding invoice exceeds property cash | Invoice recorded, deficit visible, payment blocked pending authorized funding decision |

Property-based tests generate random valid receipt/fee/expense/share/return sequences and assert balanced journals, conserved cents, no overallocated receipts, no overreserved funds and reproducible outputs. Include integer overflow boundary validation, zero amounts, negative correction events and rounding ties. Test crash boundaries before/after outbox commit, external submission, webhook persistence and settlement posting.

### 15.2 Prospect and scheduling tests

- PRO-01: Missing income period leads to clarification, not zero income/failure.
- PRO-02: Qualifying self-reported intake permits tour booking and labels information unverified; no formal report called.
- PRO-03: Formal application invitation/report tool before completed tour is rejected server-side.
- PRO-04: Income below illustrative threshold routes to human review, never automatic final denial.
- PRO-05: Assistance-animal/accommodation request creates private review; pet rejection logic is not applied automatically.
- PRO-06: Change protected/proxy fields in otherwise identical fixtures; evaluator inputs/results stay identical and prohibited policy fields are rejected.
- PRO-07: Two prospects request the same resource/window; only one active hold/booking wins.
- PRO-08: DST gap/overlap is clarified; occupied property without recorded lawful access cannot be confirmed.
- PRO-09: Calendar timeout yields pending status, retry reconciliation creates at most one external event.
- PRO-10: Cancellation/reschedule suppresses old reminders; opt-out suppresses disallowed channel sends.
- PRO-11: Ambiguous Zillow listing asks clarification; duplicate inquiry does not duplicate prospect/tour.
- PRO-12: Reviewed policy version changes after intake; prior evaluation persists, booking uses current applicable policy or explicit human exception.

### 15.3 Maintenance tests

- MNT-01: “Sink leaks” prompts exact location, onset/frequency, targeted wide/close media, safety and availability questions across turns.
- MNT-02: Tenant cannot provide media or three windows; ticket persists and limitation is visible to manager/contractor.
- MNT-03: “I smell gas” escalates before normal intake regardless of missing identity/media; no unsafe instructions or false claim that 911 was called.
- MNT-04: Primary emergency alert fails/unacknowledged; fallback attempt and audit occur on schedule.
- MNT-05: Malicious/oversized/disguised file remains inaccessible; safe resubmission does not duplicate ticket.
- MNT-06: Contractor from another assignment/org cannot download media or see contact/entry codes.
- MNT-07: Availability alone never authorizes entry; appointment needs permission/notice evidence and contractor acceptance.
- MNT-08: Invoice upload/completion creates no payable; approval posts exactly once and duplicate invoice is flagged.
- MNT-09: Tenant reports unresolved repair after completion; reopen preserves evidence, assignments and payments.
- MNT-10: Prompt injection in image text/message cannot approve contractor, invoice or payment.
- MNT-11: Emergency persists despite classifier outage/contradictory LLM low-risk result; only human review can de-escalate.

### 15.4 Integration, security and end-to-end validation

Test organization isolation across every API/object download, owner access across ownership periods, role escalation, CSRF/session expiry, signed-link revocation, webhook replay/signature failure, retention/legal holds, malware quarantine and audit redaction. Run accessibility checks and manual keyboard/screen-reader checks on critical flows. Load test stated volumes and restore a backup into isolated staging with reconciled balances.

End-to-end acceptance journeys: (1) check receipt → deposit → verified availability → approved invoice/fee → reconciled statement → manager-approved export → verified settlement; (2) listing inquiry → missing-data conversation → reviewed deterministic preliminary result → conflict-safe tour → completion → formal application invitation; (3) incomplete repair report → targeted questions/media limitation → approved contractor → permission-aware appointment → completion → invoice approval → payable in finance. Repeat financial journey with return/timeout failures and maintenance journey with emergency escalation.

## 16. MVP acceptance criteria

MVP is accepted only when the following are demonstrated in staging with realistic, explicitly illustrative data:

1. All three end-to-end journeys pass with role authorization and immutable audit evidence.
2. Financial examples produce exact cents; FIN-01 through FIN-19 and accounting property-based tests pass, including concurrent reservation and crash recovery.
3. No payment/export can proceed without explicit manager approval over unchanged inputs, verified destination and eligible funds. Live execution remains disabled until its separate production gate passes.
4. Owners can access only their correct versioned statements; monthly close reconciles bank/control/subledger balances and identifies outstanding items.
5. Preliminary screening is configurable and deterministic, supports missing-data/accommodation review, and never performs final housing decisions or pre-tour formal screening.
6. Tours enforce calendar/resource conflicts and access review, support cancellation/reschedule, and cannot be falsely confirmed on provider outage.
7. Maintenance assistant proactively asks issue-specific questions and media requests, captures all eight intake categories or documented gaps, and never blocks a legitimate report for absent media/windows.
8. Emergency events persist and escalate without waiting for routine intake or LLM availability; fallback notification and human acknowledgement are demonstrated.
9. Contractor access is scoped, assignment human-approved, and invoice approval creates one payable linked to its property/ticket.
10. Private storage/scanning, MFA/step-up, isolation, signed callbacks, consent/opt-out, audit redaction, backup restoration and core accessibility checks pass.
11. Provider outages degrade to documented manual workflows with explicit pending/unknown states, no duplicate actions and recoverable queues.
12. Deployment/runbooks, configuration checklist, migration/rollback procedure, OpenAPI and operational dashboards are delivered at implementation time.

Staging acceptance is separate from production authorization. All production gates below must be signed off before enabling affected real-world functionality.

## 17. Implementation phases

Phases are dependency-based milestones, not promised delivery dates. Implementation begins only after this specification-writing task is complete and a separate build task is authorized.

| Phase | Deliverable | Exit criterion / dependency |
| --- | --- | --- |
| 0 — Discovery/configuration | Review agreements, units, ownership, bank model, communication consent, emergency coverage and policies; record decisions | Missing production values explicitly tracked; test fixtures approved |
| 1 — Foundation | Auth/RBAC/RLS, core schema/migrations, audit/outbox, storage quarantine, secrets and CI/staging | Cross-organization isolation, durable jobs and backup restore verified |
| 2 — Accounting core | Immutable journal, receipt/deposit/availability, allocation/fees/reserves, invoices, reconciliation | Worked examples, invariants and concurrency tests pass; accountant reviews model |
| 3 — Maintenance priority workflow | Issue playbooks, durable incomplete intake, media, emergencies, contractor scheduling/completion/invoices | MNT suite and emergency fallback drill pass; approved invoices integrate with phase 2 |
| 4 — Prospects and tours | Listing inquiry adapter/fallback, typed intake, reviewed policy evaluator, human review and calendar | PRO suite passes; no pre-tour formal screening or automated final decisions |
| 5 — Statements/distribution controls | Period close, owner portal, proposals, approval snapshots, instruction exports and settlement evidence | Full FIN/E2E suite and monthly close simulation pass |
| 6 — Pilot and optional live payments | Provider sandbox/live adapter validation, operational training, monitoring, limited real portfolio rollout | Legal/accounting/owner configuration gates complete; manager authorizes controlled launch |

Use small pilot cohorts and reconcile every early transaction. Rollback disables dispatch/submission and restores compatible application versions; never delete posted journals or blindly roll back a database that would forget already-executed external actions. Failed migrations must have reviewed forward-repair plans and tested backups.

## 18. Open questions and production gates

These questions must be resolved in configuration/decision records, not answered by an implementation agent’s invention.

| Question | Blocks | Required confirmation |
| --- | --- | --- |
| Exact properties, units, leases and existing balances? | Production import/ledger opening | Manager supplies reconciled opening bank, custodial obligations, arrears and ownership-effective records; accountant verifies |
| Which business entity/license and trust accounting rules apply? | Real-money handling | NC-qualified legal/accounting review and approved operational procedures |
| Which bank/accounts, pooled or segregated structure, payment provider and availability evidence? | Real deposits/payouts and live adapter | Manager/bank/provider approve account types, authorization, available-fund rules, limits and return handling |
| What fees apply per landlord agreement? | Fee accrual and affected owner statements/payouts | Signed fee base, rates/fixed fees, timing, proration, caps, exclusions and reversal rules |
| What owner shares, expense responsibility and effective-period rules apply? | Beneficial allocation | Effective-dated agreements, including transfers and jointly owned properties |
| What reserves, spending authority, payment priorities and shortfall funding rules apply? | Reserve changes/unfunded invoices/emergency spend | Manager/owners approve property-specific rules and release authority |
| Who approves and verifies recipients; is dual control required? | Payment activation | Named roles, bank verification method, step-up and fraud-response runbook |
| What is the monthly close/statement schedule and retention? | Official statements and production data lifecycle | Accountant/legal approval of close rules, correction approach and retention matrix |
| Which screening/occupancy/pet policies and lawful income treatment apply? | Automatic preliminary qualification | Reviewed property-specific policies, accommodation process and consistent explanations |
| Who handles applications, reports and adverse action after tours? | Formal screening integration | Provider selection plus legal/manager-approved authorization and human decision procedure |
| What marketplace access and communication consent exist? | Automated external intake/outbound channels | Authorized integration access, sender identity, consent/opt-out rules |
| Who provides 24/7 emergency coverage and backup? | Unattended maintenance launch | Tested primary/alternate contacts, acknowledgement schedule and reviewed safety templates |
| Which contractors and access/notice rules are approved? | Assignment and occupied-unit appointments | Approved contractor list/credentials, spending limits, lease/legal access procedure |
| What languages, accessibility and accommodation support are available? | Supported production conversational channels | Reviewed language templates and human alternatives |
| Who can view/retain media, entry codes and sensitive accommodation information? | Production privacy configuration | Least-privilege access map, retention/deletion/hold policy and incident owner |

Production sign-off records must identify the manager/product owner, financial reviewer and appropriate legal reviewer for their respective gates. Unresolved gates disable only the affected functionality with a visible reason; no test fixture is promoted silently. The implementing agent should document material technical deviations in architecture decision records and update this PRD before changing financial or housing-decision behavior.
