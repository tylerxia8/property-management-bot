# ADR 0012 — Contract routes, scoped grants, and declared responses

Date: 2026-11-07

Status: accepted before the code in this milestone. No business rate, fee, or housing rule is decided here.

## Routes

PRD §9.2 names eight commands this API did not mount, plus `POST /receipts/{id}/returns`. This milestone mounts them.

- The property ledger is a read of posted journal rows for that property, with the same balance breakdown `property_balances` already returns. It does not post.
- A journal reversal swaps the posted lines and inserts a new journal whose `reversal_of_id` is the original. The original stays. The same journal reversed again returns the same reversal. A closed period is rejected by `app_post_journal`.
- Bank transactions are the rows already imported. A match records cents against one deposit batch on the same bank account and cannot exceed the transaction or the unmatched deposit total. It does not post a journal.
- Invoice read returns the existing invoice projection. A credit note increases `credited_cents`, keeps the original payable journal, and posts a new balanced journal. It cannot credit more than the unsettled remainder.
- A receipt return posts the opposite custody entry only when nothing has been allocated. A return after allocation responds `CONFIGURATION_REQUIRED`. The agreement does not define those reversal legs.
- Submission evidence stores a manager reference and does not settle. Settlement evidence posts the same settlement journal as an approved distribution item, with `simulator` false and kind `MANUAL_SETTLEMENT`. It still requires the current approval snapshot. It is not the simulator and not a bank transfer.

## Resource scope

`capabilities` and `roles` on `/me` stay the organization-wide grants. A grant with `resource_type` and `resource_id` is returned on `grants` and authorizes that capability only for that resource. It does not make `app_actor_is_staff()` true. Bank-account queues have no property column, so they stay organization-wide. A scoped property grant cannot read them.

## Kill switches and alerts

Organization settings store `outbound.messaging_enabled`, `outbound.calendar_enabled`, and `outbound.payment_enabled`. Missing values are false. False blocks automatic calendar outbox rows and `POST /distribution-batches/{id}/submit`. Manual ledger reads, ticket intake, and manual evidence stay available. Alerts are rows in PostgreSQL. Dispatch retries and can record a fallback row. `delivered_at` stays null.

## Response schemas

New routes declare Pydantic success models whose fields are the values the handler returns. The generator still emits `unknown` for success responses whose route does not declare a model. Declaring a model must not drop a field the handler returns.
