# ADR 0017: Versioned manual bank CSV import

Date: 2026-11-07. Status: accepted technical decision for local/manual imports.

## Problem

PRD §4.2 and §11 require manual bank import as a fallback. The existing API accepted canonical JSON but rejected all CSV because no bank-specific layout was confirmed. Reimporting an existing bank transaction ID also ignored changed amounts/dates, hiding inconsistent source evidence.

## Decision

Add `canonical_csv_v1` to `POST /v1/bank-imports` and a file selector on the accounting screen. This is an application-owned interchange format, not an assumption about a selected bank. Users must map bank exports to this format explicitly. Generic `format: csv` remains unconfigured. Bank accounts must already exist and be accessible to the accounting actor.

The exact header is `bank_account_id,external_id,amount_cents,posted_on`. Files are UTF-8 (optional BOM), with standard CSV quoting and LF or CRLF line endings. Blank lines are ignored; surrounding cell whitespace is trimmed. Account IDs are UUIDs; external IDs must be nonempty, up to 200 characters; amounts are signed integer USD cents within PostgreSQL bigint range (positive = credit, negative = debit); dates use valid `YYYY-MM-DD`. Limits are 2 MiB and 10,000 transactions. Reject missing/extra columns, unknown headers, fractional/scientific amounts, invalid dates, malformed quoting and mixed CSV/JSON payloads. Errors identify the line without echoing financial data. Parse the entire CSV before inserting anything.

All imports reuse the existing authorization, organization isolation, idempotency and database transaction boundaries. An exact repeated account/external ID is safe and counted as existing. An amount/date conflict returns `409 BANK_TRANSACTION_CONFLICT`; it neither overwrites the original nor accepts other rows from that batch. This includes competing concurrent imports and conflicts within a single new batch. Do not discard the original and reimport a corrected bank line under a new ID without source review.

Importing adds bank evidence only: no journal, deposit match, availability verification, funds allocation or payment is performed. Production banking and accounting gates remain open. Arbitrary provider exports still require mapping; no scraping or provider call is introduced.

## API example

Send `Idempotency-Key` with accounting permission:

```json
{
  "format": "canonical_csv_v1",
  "csv_text": "bank_account_id,external_id,amount_cents,posted_on\n00000000-0000-4000-8000-000000000001,example-credit,10001,2026-11-07\n"
}
```

The UUID above is illustrative; replace it with an existing account ID returned by `POST /v1/bank-accounts`. Success retains the JSON import response: `created`, `existing`, and `request_id`. Retrying the same request/key returns the original result. The UI retains its request key for retries of the same selected file after uncertain network outcomes. Selecting a file again creates a new request, with transaction-level deduplication still enforced.

## Verification

`test_bank_csv_import.py` covers parsing, limits, malformed inputs, exact request replay, JSON/CSV deduplication, conflicting evidence, atomic validation and AI denial. Additional accounting-core regression cases cover whole-batch rollback, reuse of a rejected request key, same-batch conflicts, and concurrent exact/conflicting imports. The browser accounting test covers file selection, successful import, request replay, malformed rows and conflict display.
