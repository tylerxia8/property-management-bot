# ADR 0015 — Isolated fixture demo

Date: 2026-11-07

Status: accepted

## Decision

`grok_demo_sample` is a separate database for a fictional walkthrough. `scripts/reset_demo_sample.sh` drops and recreates only that database. The seed refuses every other name and refuses `APP_ENV=production`.

`POST /v1/demo/session` is mounted only when `APP_ENV` is development or test, `DEMO_FIXTURE=sample`, and both database URLs name `grok_demo_sample`. The SQL function also returns no row in any other database. Production does not mount the route. Passwords for the fixture users are random and are not returned.

Screening ratios and the tour schedule in that seed are stored with `fixture:` labels. Outbound messaging, calendar, and payment stay off.

## Consequences

The ordinary test and e2e databases do not gain a passwordless role switch. A public deployment is not part of this decision.
