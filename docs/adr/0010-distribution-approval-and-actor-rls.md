# ADR 0010 — Fail-closed actor RLS and distribution approval

Date: 2026-11-07

Status: accepted for phase 5. Not a bank integration and not production MFA.

## Actor decision

`grok_app` policies no longer treat a missing actor as permission to see an organization. The impact of the old rule was direct: with `app.organization_id` set and `app.actor_id` empty, the runtime role could select properties, leases, journals, receipts, prospects, and maintenance tickets. A stale pooled actor is cleared on checkout; a new checkout that sets only the organization now sees no rows.

`app_post_journal` still runs as `grok_posting`. Those policies name that role. Migrations keep using `grok_migrator`, which is a superuser and is not granted to the application role. A worker that must post without a person uses that `grok_posting` identity. It does not connect as `grok_app` with an empty actor.

The actor GUC is the application's trust boundary. Anyone who can connect as `grok_app` can set `app.actor_id` to a user UUID. The policies stop a missing or unknown actor from reading rows. They are not a second password.

Portal rows keep their relationship rules: a tenant and a ticket, a prospect and their own intake, an owner and a linked statement. Staff is `property_manager`, `organization_administrator`, or `accounting_staff`.

## Payment decision

The four fixture settlement routes cannot clear a payable. The fixture flag does not reopen them.

Clearing happens only inside an approved distribution item whose snapshot still matches, and only when the process is development or test and `payment_simulator=enabled`. The ledger source type remains the settlement type. The payment event row says `SIMULATOR`, so a journal from this path is not evidence of a bank debit.

`/submit` is a real route. Its disabled result is `PROVIDER_SUBMISSION_DISABLED`.

Step-up is a local password check stored as a timestamp. It is not mounted in production. Approval refuses to proceed when `step_up_max_age_seconds` is 0, which is the default. Tests set the age explicitly.

Approval lifetime is a required field on approve. This build does not fill in 24 hours by itself.

## Statement decision

A statement row stores the ledger figures and a hash. Updates are rejected. A new version points at the prior row. Owner reads use a party link, not the organization role alone.
