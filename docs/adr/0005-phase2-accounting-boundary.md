# ADR 0005 — Phase 2 accounting boundary

Date: 2026-11-07

Status: accepted as the scope cut for this milestone. Not a product-owner approval of fee, ownership, or payment policy.

## Context

PRD §17 puts the immutable journal, receipt lifecycle, allocation, fees, reserves, invoices, and reconciliation in phase 2. Statements, distribution controls, and settlement evidence are phase 5. Maintenance and prospects follow in later runs.

The worked example in §4.5 and several §4.3 posting templates produce owner-distribution and settlement journals. Those templates are ledger rules. The batch approval, export, and provider submission around them are phase 5 and phase 6.

## Decision

Phase 2 posts the specified templates, including owner-distribution declaration and simulated liability settlement, because the worked-example oracle and FIN-09 cannot be shown without those journals.

Those commands do not call a bank, do not write an export file, and do not create a distribution batch. `POST /v1/distribution-batches/{id}/submit` is not registered.

Declaration requires the property-manager role. Settlement requires that role and property rent-cash lots. Neither command is available to the AI role.

Phase 5 remains the place for snapshot hashes, approval expiry, instruction export, owner statements, and the FIN-05/07/08/15/18 payment-batch tests.

## Consequences

A later phase 5 change should wrap these journals with the batch lifecycle rather than posting a second copy of the same economic event. Source uniqueness on the journal is what keeps that from double-posting.
