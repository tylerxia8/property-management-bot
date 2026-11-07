# Grok Bot

Grok Bot is a proposed AI-assisted property management platform for a North Carolina portfolio of 51–100 residential rental properties.

The product specification covers:

- Rent collection, deterministic double-entry accounting, landlord statements, and manager-approved payment instructions.
- Preliminary tenant prequalification before tours, with human review and formal screening after the tour.
- Detailed maintenance intake, safe photo/video collection, emergency escalation, and approved contractor coordination.

Read the **[Engineering Product Requirements Document — Version 2.0](PRD.md)** for workflows, database design, API contracts, accounting formulas, security requirements, acceptance tests, implementation phases, and production gates.

The local implementation includes organization isolation, dev/test authentication, property and unit management, a double-entry ledger, preliminary screening and tours, maintenance intake, statements, and approved distribution instruction exports. A fictional local demo supports exploring these workflows. Live banking, outbound messaging, external calendars, production identity, and production media services remain disabled or unconfigured.

For setup and the demo bundle, see [docs/SETUP.md](docs/SETUP.md) and the [demo instructions](deploy/grok-property-sample/README.md). The [implementation plan](docs/PLAN.md), [local acceptance matrix](docs/ACCEPTANCE.md), and [dependency gates](docs/DEPENDENCY_GATES.md) distinguish implemented behavior from remaining work. Local test evidence is in [docs/evidence](docs/evidence); it does not establish staging acceptance or production readiness.

Business-specific fees, banking providers, landlord agreements, and legally reviewed screening policies remain explicit configuration and production prerequisites.

To present the local fictional-data demo on Windows, start Docker Desktop and double-click `Start-Demo.cmd`. Follow the [demo walkthrough](docs/DEMO_WALKTHROUGH.md). The demo keeps live payments, messaging, and external calendars disabled.

For the password-protected Railway website, deployment and operating instructions are in [Hosted demo](docs/HOSTED_DEMO.md).

See the [open-source comparison](docs/OPEN_SOURCE_REVIEW.md) for adopted listing-matching and HEIC improvements, measured results, and the accounting, scheduling, and conversation platforms reviewed.
