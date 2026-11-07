# ADR 0006 — Ledger posting and unspecified templates

Date: 2026-11-07

Status: accepted for enforcement mechanics. Business rates remain configuration.

## Decision

`grok_app` cannot insert or update journal rows. `app_post_journal` is `SECURITY DEFINER`, owned by `grok_posting` (`NOLOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`). The function still has to match the transaction’s organization GUC, so it does not bypass row-level security. A deferred constraint trigger rejects unbalanced, single-line, non-USD, and closed-period journals. Posted headers and lines cannot be updated or deleted; the trigger applies to the table owner and to the migrator superuser.

Chart codes 1010–2070 are inserted per organization by `app_ensure_proposed_chart`. They are the proposed codes from §4.3, not a fee schedule and not a regulatory chart.

Money in Python is `int` cents. Fee rounding uses `Decimal` with `ROUND_HALF_UP` once. Share allocation uses integer floor and largest remainder. Remainder ties break by ascending UUID text. That tie break is the stable ordering chosen for “ties by stable owner UUID”; the PRD does not say ascending versus descending.

Security-deposit receipts use the custody asset path and credit 2070 instead of 2010. The PRD requires segregation and forbids using deposits as rent, and it does not list a separate deposit template. The 2070 credit is the specified restricted liability. Deposit cash is tagged `SECURITY_DEPOSIT` and cannot fund fees, owner distributions, or contractor settlements.

Reserve top-up is a 2020 to 2030 reclass and moves the same number of cents from rent funding lots to reserve lots. It does not invent cash.

Direct-bank receipts, CSV imports, non-weight responsibility, fractional invoice quantities, and outbound clearing stay gated. Canonical bank import is a JSON list of account, external id, signed amount, and date. That is the normalized record §4.2 already names, not a claimed bank-file dialect.

Opening reserve cash is a manual journal with source `OPENING_RESERVE_CASH`. It is not a reconciled production trial balance.

## Consequences

Tests that need an 8% fee create that agreement in the test. No migration inserts a rate.
