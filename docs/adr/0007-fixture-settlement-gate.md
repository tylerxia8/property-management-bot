# ADR 0007 — Fixture settlement is not payment approval

Date: 2026-11-07

Status: accepted. Closes a gap found while reviewing phase 2 before phase 3.

## Gap

Phase 2 exposed four HTTP commands that move money inside the ledger without an approval snapshot:

- `POST /v1/properties/{id}/distribution-declarations` reserves owner funds into declared distributions
- `POST /v1/invoices/{id}/simulated-settlement` clears a contractor payable against bank cash
- `POST /v1/fee-settlements/simulated` clears the management-fee payable
- `POST /v1/distribution-declarations/{id}/simulated-settlement` clears a declared distribution

They required the property-manager role only. PRD §4.7 requires an authenticated approval over an unchanged snapshot before payment. Phase 5, which owns that approval contract, is not built. Leaving these routes open would be a payable-clearing backdoor.

Invoice approval is different. It posts the payable once. It does not clear cash. That route stays.

Opening reserve entries are manual journals, not payment clearing. They stay accounting-staff operations.

## Decision

Those four routes return `409 APPROVAL_CONTRACT_REQUIRED` and post nothing unless both of these are true:

- `APP_ENV` is `development` or `test`
- `allow_fixture_ledger_settlement` is true

The flag defaults to false. Setting it in production does not enable the routes. The FIN-02, FIN-06, and FIN-19 tests opt in for the oracle only. No approval snapshot is pretended; the flag is a test seam, not the phase 5 contract.

## Consequences

Phase 5 must add snapshot approval before these journals can run without the fixture flag. Until then, a normal manager token cannot reserve a distribution or clear a payable.

## Phase 5 update

ADR 0010 supersedes the fixture flag. `fixture_ledger_settlement_allowed` is always false, including in development and test, so the four routes stay `409 APPROVAL_CONTRACT_REQUIRED` even when the flag is set. A payable clears only inside an approved distribution item while `payment_simulator=enabled` in development or test. That path records `simulator=true` and is not a bank transfer. Ordinary dev usage of the old routes does not clear cash.
