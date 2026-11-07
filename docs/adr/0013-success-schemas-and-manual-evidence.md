# ADR 0013 — Declared success schemas and manual evidence

Date: 2026-11-07

Status: accepted

## Decision

Every mounted JSON success response uses a Pydantic model whose fields are the keys the handler already returns. The generator writes those component schemas, request bodies, parameter types, and success response types. A success response with no schema is a test failure. `GET /v1/media/{id}/content` stays `application/octet-stream`. It is not given a JSON model.

The error body stays `{error: {code, message, details, retryable}, request_id}`. Validation details contain `loc` and `msg` only, which is what the handler emits.

Manual submission and settlement evidence records an approved ledger fact. It does not call a bank. The command requires an organization-wide manager (`distributions.approve`), a current approval snapshot, an `Idempotency-Key`, and a non-empty reference. The amount and currency come from the item. `bank_contacted` is false. A second manual evidence row for the same item and kind is rejected. Settlement evidence is rejected unless the item is `APPROVED` or `UNKNOWN`, and it is rejected when a simulator settlement already exists. Cash is not cleared when the reference is blank. The fixture settlement flag is not read.

PRD §4.6 specifies the pre-allocation receipt return as reversing the matching custody entry, limited to the original receipt. That path stays. The same section says a return after allocation and before payout reverses allocations and fee accruals according to the agreement. The agreement does not name those accounts, so that return stays `CONFIGURATION_REQUIRED` and posts nothing. A return after payout is the distribution-item path already specified as a debit to 1040. This decision does not add a second reversal.

## Consequences

`0008_success_contracts` adds a unique index for manual evidence kinds. Generated TypeScript reports zero success responses typed as `unknown`.
