# Phase 4 scope — prospective tenants and tours

PRD §17 phase 4: listing inquiry, typed intake, a reviewed policy evaluator, human review, and calendar holds. The exit bar is the PRO suite, with no pre-tour formal screening and no automated final housing decision.

Phase 5 statements, distribution approval, export, and settlement evidence stay unbuilt.

## In this milestone

- Listings bind an external listing id to a property and unit. An inquiry stores the provider message id. A second delivery of that id returns the same inquiry and does not create another prospect or tour.
- Unknown or multiple matches do not guess a unit. The response asks which listing.
- Intake fields are typed. Income keeps the original cents and period. Monthly cents are normalized once with half-up rounding. A missing period leaves monthly cents null.
- Screening policies are versioned, reviewed, and limited to an allowlist. Protected characteristics and name, language, and postal-code proxies are rejected at publish time. `automatic_final_denial` cannot be true. A failing rule can only request human review.
- No policy is seeded as a real rule. Evaluation with no reviewed policy returns human review and `CONFIGURATION_REQUIRED`. The illustrative 3× rent ratio exists only when a manager publishes a policy marked `fixture` with a `fixture:` review reference.
- Evaluations are insert-only. They record the policy version, intake version, input hash, and rule ids. `formal_screening_permitted` stays false.
- Assistance-animal requests open a private accommodation case. Pet rules are not applied to that request. Accounting, contractors, and other prospects cannot read the case.
- Tour holds use a PostgreSQL exclusion constraint on the buffered resource range. Expired holds are marked expired before a new insert. DST gaps are rejected. Ambiguous local times ask for an earlier or later choice.
- A missing schedule returns `CONFIGURATION_REQUIRED`. Tests publish the PRD’s proposed 30-minute tour, 15-minute buffer, and 5-minute hold as a labeled fixture. Those numbers are not a hidden global default.
- Confirming a tour with the calendar provider unset yields `CONFIRMATION_PENDING` and one outbox job. The database rejects `external_event_created = true`. A manager may record `MANAGER_CONFIRMED` without claiming an external event.
- Occupied units cannot be confirmed without manager-supplied access evidence. No notice-day count is invented.
- Cancel and reschedule suppress prior reminder rows. A channel the prospect opted out of is stored as `OPTED_OUT`. `delivered_at` stays null. Nothing is sent.
- An application invitation requires a completed tour and a manager. The consumer-report route always returns `REPORT_ORDERING_DISABLED` and writes no report.
- A final disposition is a manager action with a reason and an audit row. The evaluator cannot write one.
- Prospects see their own rows. Tenants do not see screening rows. Contractors do not see door codes or accommodation cases. This is enforced with restrictive row-level policies, not only with role checks in the API.

## Not in this milestone

- Phase 5 owner statements, distribution batches, approval snapshots, and payment export
- A live calendar, email, or SMS provider
- Ordering a consumer report or storing a report body
- An automated approval or denial of housing
- A production screening threshold

## Access boundary

API requests set `app.actor_id`. Intake tokens also set `app.intake_ticket_id` or `app.access_mode`, so a maintenance link is not a session that can read every row in the organization. Connections that set only `app.organization_id` still see that organization’s rows. That is the existing M0 test path. The API does not use it for a signed-in prospect, tenant, or contractor.
