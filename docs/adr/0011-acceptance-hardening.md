# ADR 0011 — Local acceptance hardening

Date: 2026-11-07

Status: accepted before the code in this milestone. This is not staging acceptance and not a production launch.

## Approval lifetime

PRD §4.7 says approval expiry is proposed at 24 hours and configurable. The previous API let the caller send `approval_ttl_hours`, including a very large number, and the server stored it. That defeats expiry.

This milestone does not adopt 24 hours as a business rule. `APPROVAL_TTL_HOURS` defaults to 0. Approval then returns `CONFIGURATION_REQUIRED` and stores nothing. When an operator sets a positive integer, that value is the only lifetime used. The request body no longer accepts a lifetime; a client that sends one gets `422 VALIDATION_ERROR`. Tests and the browser evidence process set `24` only as a bounded fixture. Production stays at 0 until a reviewed policy is configured.

Export, submit, and settlement recompute the snapshot, destination party and version, and the reserved amount. An expired approval returns `APPROVAL_EXPIRED` on export as well as submit.

## Step-up and simulator

Local password step-up stays on the dev/test login router. Production does not mount it. A client cannot send a step-up timestamp. `payment_simulator=enabled` does nothing when `APP_ENV=production`. The four declaration and simulated-settlement routes stay `APPROVAL_CONTRACT_REQUIRED`.

## Worker and webhooks

PRD §7.2 names Celery and Redis. This repository does not run either. The durable record remains PostgreSQL. A local worker claims pending outbox rows with `app_outbox_progress`, retries with backoff, and marks `FAILED` after five attempts. It never opens a network connection. `delivered` is false. Redis is not installed and is not a source of truth.

Signed webhooks are accepted only when `APP_ENV` is development or test and `WEBHOOK_SECRET` is at least 16 characters. Production returns `WEBHOOK_NOT_CONFIGURED` even if a secret is present. Invalid signatures and stale timestamps write no inbox row. The same provider event id does not post a second journal. The worker posts an invoice payable only when the signed actor is a manager or organization administrator in that organization.

## Downgrade

`alembic downgrade` refuses to run unless `ALLOW_DESTRUCTIVE_DOWNGRADE=1`. Downgrade can drop ledger and distribution tables. The migration test sets the flag. A production process must not. Revision 0006 also restores intake, media, message, and accommodation policies that a 0005 downgrade removes and does not recreate.

## What this ADR does not decide

No fee, reserve, screening, or housing rule. No live bank, OIDC vendor, Celery broker, or object store. Cookie CSRF stays unimplemented because the session is a bearer token, not a cookie. The local backup drill is `pg_dump` and `pg_restore`, not encrypted point-in-time recovery.
