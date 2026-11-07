# Phase 2 scope — accounting core

PRD §17 phase 2 deliverable: immutable journal, receipt/deposit/availability, allocation/fees/reserves, invoices, and reconciliation.

This file records the phase 2 boundary. Phase 3 maintenance is in `docs/PHASE3_SCOPE.md`. Phase 4 prospects are in `docs/PHASE4_SCOPE.md`. Phase 5 statements, distribution batches, approval snapshots, instruction export, and the owner portal stay unbuilt. They are not dropped.

## In this milestone

- Proposed chart 1010–2070, labeled proposed, with no fee rate seeded
- Posted journals only through `app_post_journal`, balanced in integer cents, USD only, immutable after posting, reversals as new journals
- Closed posting periods reject backdated journals
- Check and cash custody lifecycle with amount-level counters
- Rent charges as an operational subledger that does not post custodial cash
- Explicit fee agreements; a missing agreement returns `CONFIGURATION_REQUIRED` and posts nothing
- Ownership weights totaling 1,000,000 and largest-remainder allocation
- Reserve targets applied by those weights, as a liability reclass plus a funding-lot reclass
- Invoice submission with no journal; manager approval posts one contractor payable
- Security deposits credited to 2070 and barred from owner, fee, and contractor cash
- Bank transaction import in a canonical JSON body, match records, and reconciliation close that refuses an unexplained difference
- Simulated liability settlement journal (debit 2040/2050/2060, credit 1030) with no bank call
- Manager declaration of an owner distribution for the calculated candidate, with no export and no provider submit
- Accounting screens for recording a receipt, reading its counters, and reading a property ledger

## Not in this milestone

| Item | Where it belongs |
| --- | --- |
| Maintenance intake, media, contractor assignment | Phase 3. It will call invoice approval. |
| Prospect policy evaluator and tours | Phase 4 |
| Distribution batch lifecycle, approval expiry, export files, owner statements, monthly statement package | Phase 5 |
| Live `submit`, provider timeout, and real settlement webhooks | Phase 6, and still simulated until the provider and accounting rules are confirmed |
| FIN-05 payment reservation race, FIN-07 approval invalidation, FIN-08 provider timeout, FIN-15 mixed batch settlement, FIN-18 export identity | Phase 5 or 6 tests. Not claimed here. |

## Gates left visible

- `DIRECT_BANK` receipts return `DIRECT_BANK_TEMPLATE_UNCONFIGURED`
- CSV bank imports return `BANK_IMPORT_FORMAT_UNCONFIGURED`
- Responsibility modes other than ownership weights return `CONFIGURATION_REQUIRED`
- Outbound-clearing is not given an account code
- No creditor priority is chosen when property cash cannot fund a payable
- Illustrative 8% exists only inside the FIN-02 test, on an agreement that test creates
