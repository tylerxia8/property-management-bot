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
| §4 through §6 financial, prospect, and maintenance behavior | Phase 2 accounting, phase 3 maintenance, phase 4 prospects | `tests/test_accounting_core.py`, `tests/test_maintenance.py`, `tests/test_prospects.py` |

## Phase 2 acceptance map

| ID | Result in this milestone | Evidence |
| --- | --- | --- |
| FIN-01 | Executed | `test_fin_01_unverified_check_is_not_distributable` |
| FIN-02 | Executed, exact cents including closing bank 80,000 | `test_fin_02_worked_example_exact_cents` |
| FIN-03 | Executed | `test_cent_allocation_and_half_up_rounding` |
| FIN-04 | See the phase 5 map. One hundred approval replays post one payable | `test_fin_04_hundred_replays_post_one_journal` |
| FIN-05 | See the phase 5 map | `test_fin_05_concurrent_reservations_cannot_exceed_cash` |
| FIN-06 | Executed for property cash isolation | `test_fin_06_other_property_cash_cannot_fund_payment` |
| FIN-07 | See the phase 5 map | `test_fin_07_destination_change_invalidates_approval` |
| FIN-08 | See the phase 5 map. Submit is a route and returns `409 PROVIDER_SUBMISSION_DISABLED` when the simulator is unset | `test_fin_08_timeout_then_same_key_settles_once` |
| FIN-09 | Executed inside FIN-02: settlement debits the payable and credits bank, and owner expense is not posted again | `test_fin_02_worked_example_exact_cents` |
| FIN-10 | See the phase 5 map | `test_fin_10_return_books_recovery_and_freezes` |
| FIN-11 | Executed for closed period and direct journal-line insert rejection | `test_fin_11_database_rejects_bad_journals` |
| FIN-12 | Executed | `test_fin_12_partial_availability_limits_allocation` |
| FIN-13 | Executed, candidate 52,000 cents | `test_fin_13_deficit_limits_distribution_candidate` |
| FIN-14 | Executed | `test_security_deposit_cannot_fund_owner_or_fee` |
| FIN-15 | See the phase 5 map | `test_fin_15_partial_failure_is_not_replayed` |
| FIN-16 | Canonical reimport and idempotency conflict executed. CSV layout remains gated | `test_direct_bank_and_csv_are_gated` |
| FIN-17 | Executed. A later ownership period changes only the later allocation | `test_fin_17_later_ownership_does_not_rewrite_posted_allocation` |
| FIN-18 | See the phase 5 map | `test_fin_18_second_export_keeps_identity_and_does_not_settle` |
| FIN-19 | Executed | `test_fin_19_invoice_deficit_blocks_settlement_not_accrual` |
| M0 suite | Re-run with phase 2 | full pytest |
| §16 staging acceptance | Not claimed | Local tests only |

Playwright covers the dev/test shell: local-auth disclosure, accounting read without create, tenant forbidden state, administrator create, manager rename and unit add, and a tenant maintenance report. It does not claim WCAG certification.

## Phase 3 acceptance map

The assertion column is what the executed test checked. A test name by itself is not the proof.

| ID | Result | What was asserted |
| --- | --- | --- |
| MNT-01 | Executed | “Sink leaks” responses, across turns, contained room/fixture, onset, wide and close-up media, hazard, and access-window questions, at most two per turn. The third reply set `handoff` and returned no questions. “stop asking” also stopped questions. Two ticket rows remained. |
| MNT-02 | Executed | Media `NOT_PRACTICAL` with the tenant’s reason and one access window stayed on the ticket. Status was not `CANCELED`. Manager and assigned contractor reads included that reason and window. |
| MNT-03 | Executed | “I smell gas” with a claimed unit and unknown media returned `emergency` true, priority `EMERGENCY`, and no questions. Safety text is the PRD sentence plus “Do not operate electrical switches.” The body did not say responders were contacted or that 911 was called. The stored `unit_id` was null. An outbox row `MaintenanceEmergencyDetected` had no delivery timestamp, and no notification job had `delivered_at` set. |
| MNT-04 | Executed | With the test clock, a failing primary destination stored an unsent primary job. Five minutes later the alternate destination had a fallback job and an audit row. Ten minutes later a repeat job existed. Acknowledgement stopped further jobs. A second organization with no destination stored `DESTINATION_UNCONFIGURED` and `delivered_at` null. |
| MNT-05 | Executed | A declared 21 MB image was rejected before storage. `MZ` bytes, a PNG declared as JPEG, and HEIC bytes were `REJECTED` and not downloadable. A JPEG became `READY` only under the fixture scanner, the derivative and thumbnail omitted the original EXIF description, and a one-second MP4 became `READY` with `video_understanding` false. The ticket count stayed 1. |
| MNT-06 | Executed | The entry-code response and ciphertext did not contain the plaintext code. The assigned contractor’s ticket JSON and every notification payload omitted the code and the accommodation note. The other contractor and another organization received 404 for the ticket or download. |
| MNT-07 | Executed | An access window left the appointment `REQUESTED`. Confirming without permission, notice evidence, and an accepted assignment returned `409 ENTRY_PERMISSION_REQUIRED`. After acceptance, permission, and notice evidence, status became `CONFIRMED`. The estimate response had `spending_limit` null and `WAITING_APPROVAL`. |
| MNT-08 | Executed | Completion left `payable_journal_id` null and did not add a journal. Work-order invoice submit stayed `SUBMITTED` with no payable. Manager approval created one `INVOICE_APPROVAL` journal. A second approval returned the same journal id and the count stayed 1. A repeated invoice number returned `409 DUPLICATE_INVOICE`. The approved invoice and its link row remained. |
| MNT-09 | Executed | After completion, approval, and `COMPLETED`, reopen returned `REOPENED`. The assignment id, invoice link, and payable journal id were unchanged. |
| MNT-10 | Executed | An instruction to approve and pay, including inside an uploaded JPEG, left the contractor `approved` false, invoice count 0, and journal count 0. The AI role received 403 on assignment. The scan result had no transcript. |
| MNT-11 | Executed | `classifier_result` `low_risk` left `emergency` true and cleared the questions. The tenant received 403 and a blank manager reason returned 422. A manager reason stored the actor and cleared the flag. One `maintenance.classifier_ignored` audit row existed. |
| Settlement gate | Executed | With the fixture flag off, a manager approval left the 2040 payable at 4000 and bank 1030 at 0. Simulated settlement and distribution declaration returned `409 APPROVAL_CONTRACT_REQUIRED`. Production with the flag true still had `fixture_ledger_settlement_allowed` false, and the unauthenticated settlement call returned 401. |
| Fixture scanner boundary | Executed | Production settings with `media_scanner=fixture` did not allow the scanner. A valid JPEG scanned with that flag stayed not ready, code `SCANNER_NOT_CONFIGURED`, scanner name not `fixture-byte-scanner`. The default test app did the same over HTTP, and download returned 404. |

Not run from phases 2 and 3, and not claimed here: a staffed on-call vendor send; a spending-limit number; a statutory notice period; production antivirus, KMS, or object storage; HEIC conversion; model or video-understanding calls. FIN-02 now clears payables through an approved simulator batch. FIN-06 and FIN-19 stop at `INSUFFICIENT_FUNDS` on validate. The fixture settlement flag does not clear a payable.

## Phase 4 acceptance map

The assertion column is what the executed test checked.

| ID | Result | What was asserted |
| --- | --- | --- |
| PRO-01 | Executed | Income of 250000 cents with no period stayed `income_monthly_cents` null. The question said a missing period is not treated as zero. Evaluation was `NEEDS_INFORMATION` with `income_period` missing, `final_denial` false, and no disposition row. Annual 6 cents becomes 1, biweekly 3 becomes 7, and weekly 3 becomes 13, one half-up step. |
| PRO-02 | Executed | A fixture 2× policy and complete intake returned `PRELIMINARILY_QUALIFIED`. Income and the prospect stayed unverified. A hold was `HELD` with `external_event_created` false. The report route returned `409 REPORT_ORDERING_DISABLED`. |
| PRO-03 | Executed | Invitation before a completed tour returned `409 TOUR_NOT_COMPLETED` and wrote no invitation. The report route returned `409 REPORT_ORDERING_DISABLED`. |
| PRO-04 | Executed | Income under the labeled 3× fixture returned `HUMAN_REVIEW`, `policy_fixture` true, and `final_denial` false. The review item said `final_housing_decision` false. The AI role received 403 on disposition and no disposition row existed. |
| PRO-05 | Executed | An assistance-animal intake marked the pet rule `NOT_APPLIED` and returned `HUMAN_REVIEW`. The evaluation body did not contain the accommodation note. Accounting and another prospect read 0 accommodation rows. The manager read 1. |
| PRO-06 | Executed | A second evaluate that posted race, language, postal code, and name kept the same input hash and result. A policy using `race` or `failure_action` `DENY` returned `422 PROHIBITED_POLICY_FIELD`. |
| PRO-07 | Executed | Two concurrent hold requests for the same resource and window returned 201 and 409. One `HELD` row remained. |
| PRO-08 | Executed | `2026-03-08T02:30` in `America/New_York` returned `409 NONEXISTENT_LOCAL_TIME`. `2026-11-01T01:30` returned `409 AMBIGUOUS_LOCAL_TIME`. `dst_resolution` `later` created the hold. Confirming that occupied unit without access evidence returned `409 ACCESS_NOT_RECORDED`. After evidence, status was `MANAGER_CONFIRMED` and `external_event_created` was false. |
| PRO-09 | Executed | Confirm with the provider unset returned `CONFIRMATION_PENDING` and `external_event_created` false. The retry returned the same external event key. One `CalendarSyncRequested` outbox row existed. |
| PRO-10 | Executed | SMS consent false stored `OPTED_OUT` and `delivered_at` null. Email consent true stored `SCHEDULED`, then cancel set those rows to `SUPPRESSED` with `delivered_at` still null. Reschedule of a later hold also left the prior email reminders `SUPPRESSED`. |
| PRO-11 | Executed | An address hint matching two Elm listings returned `ambiguous` true, no prospect id, and a question that no unit was selected. Repeating the provider message id returned the same inquiry with `duplicate` true. A resolvable listing id created one prospect. A replay kept that prospect id. Prospect count was 1 and tour count was 0. |
| PRO-12 | Executed | The first evaluation stayed `PRELIMINARILY_QUALIFIED` with its original hash after a stricter policy version. The new evaluation was `HUMAN_REVIEW` on the new version. Updating an evaluation row raised a database error. A hold without an exception returned `409 HUMAN_REVIEW_REQUIRED`. A manager exception with a reason then allowed a `HELD` tour. |
| Portal scope | Executed | A prospect actor read 0 properties, 0 leases, and 0 journal entries. The same organization with a manager actor read the property. An unset actor and a random actor each read 0 properties. |

Not run: a live calendar send, an email or SMS send, a consumer-report order, and any automated final housing decision.

## Phase 5 acceptance map

The assertion column is what the executed test checked. Simulator rows are development/test payment-simulator events. They are not bank transfers.

| ID | Result | What was asserted |
| --- | --- | --- |
| FIN-04 | Executed | The same invoice approval was posted 100 times. Every response returned the same `payable_journal_id`. `INVOICE_APPROVAL` journal count was 1. This is an HTTP replay, not a separate worker process. |
| FIN-05 | Executed | Cash was 90,000 cents. Two batches requested 70,000 and 50,000. Concurrent validate returned 200 and 409. Reserved cents were the winning amount, 50,000 or 70,000, and not more than 90,000. |
| FIN-07 | Executed | A new destination version after approval made submit return `409 APPROVAL_INVALID`. Payment-event count stayed 0. |
| FIN-08 | Executed | The first simulator script `timeout` left the batch `UNKNOWN`, `bank_contacted` false, and posted no settlement. The same provider key with script `settle` posted one `INVOICE_SETTLEMENT` and one `SIMULATOR_SETTLED` key. A second settle kept those counts at 1. |
| FIN-10 | Executed | After simulator settlement, a return set account 1040 to the item amount, `disbursements_frozen` true, and kept the settlement journal. The event was `simulator` true. |
| FIN-15 | Executed | Four 10,000-cent items were approved. One script `fail` left the batch `PARTIALLY_SETTLED` with three `SETTLED` and one `FAILED`. A second submit did not add journals. Settlement count stayed 3. |
| FIN-18 | Executed | Two exports returned the same batch id and item id. The second had `duplicate_download` true and `settled` false. Settlement journals stayed 0. Two `distribution.exported` audit rows existed. With the simulator unset, submit returned `409 PROVIDER_SUBMISSION_DISABLED`. |
| Actor isolation | Executed | Organization set with actor unset, and organization set with a nil actor UUID, each read 0 properties. The real manager read 1. Checkout cleared a session-level actor left on a pooled connection. A prospect read 0 properties; a random actor read 0. |
| Statement access | Executed | The linked owner read the statement and listed that one id. The other owner received 404 and an empty list. Updating `owner_statements` raised a database error. |
| Settlement gate | Executed | With the fixture flag on, simulated settlement and distribution declaration still returned `409 APPROVAL_CONTRACT_REQUIRED`. Payable 2040 stayed 4,000 and bank 1030 stayed 0. |
| Cent invariants | Executed | Twenty random ownership allocations summed to the input cents. Three small available receipts left debit totals equal to credit totals. |

Not run, and not claimed: a live payment provider, a bank file, production OIDC or MFA, an out-of-process webhook worker, and phase 6 rollout. Playwright covers export without settlement and owner-only statement visibility. It does not claim WCAG certification.
