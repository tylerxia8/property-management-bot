# ADR 0009 — Prospect evaluation and tour holds

Date: 2026-11-07

Status: accepted for phase 4. Not a fair-housing approval and not a calendar vendor selection.

## Decision

Income conversion is one half-up step to integer cents: annual ÷ 12, weekly × 52 ÷ 12, biweekly × 26 ÷ 12. Monthly values stay as entered. The original cents and period are stored. Missing period does not become zero.

The evaluator accepts only these rule fields: `household_income_monthly_cents`, `lease_months`, `occupant_count`, `pets_declared`. Operators are `gte_rent_multiple`, `in`, `gte`, and `lte`. Failure action is `HUMAN_REVIEW` only. Policies that name a protected characteristic, a proxy (name, language, postal code), adult/child composition, or `automatic_final_denial: true` are rejected.

The input hash uses the allowlisted intake values. Extra personal attributes are ignored and are not columns on the intake table.

Tour conflict protection is the exclusion constraint `tour_appointments_no_overlap` on the buffered `tstzrange`. Application code also expires stale holds, but the constraint is what makes a race fail. The calendar provider setting has no enabled value in this milestone. `external_event_created` is checked false in the database.

Reminder and notification rows are local records. Cancel, reschedule, and opt-out change their status. No sender is called.

Accommodation notes use the existing AES-GCM helper. The accommodation table’s restrictive policy allows the property manager, the organization administrator, and the subject user.

Restrictive policies on tenant and financial tables allow a signed-in portal user only where a relationship exists: a tenant’s own lease, a reporter or assigned contractor on a ticket, staff for operational tables. `grok_posting` remains able to insert journals because those policies allow that role explicitly. A prospect actor is not staff and has no lease, so those policies return no rows.

## Consequences

A later calendar vendor needs a migration that can set `external_event_created` and a provider mode that this build does not contain. A later screening vendor is a separate consent flow. Publishing a non-fixture policy is a manager action with a review reference; this repository still does not choose the property’s real ratio.
