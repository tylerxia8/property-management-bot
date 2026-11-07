# Grok Bot

Grok Bot is a proposed AI-assisted property management platform for a North Carolina portfolio of 51–100 residential rental properties.

The product specification covers:

- Rent collection, deterministic double-entry accounting, landlord statements, and manager-approved payment instructions.
- Preliminary tenant prequalification before tours, with human review and formal screening after the tour.
- Detailed maintenance intake, safe photo/video collection, emergency escalation, and approved contractor coordination.

Read the **[Engineering Product Requirements Document — Version 2.0](PRD.md)** for workflows, database design, API contracts, accounting formulas, security requirements, acceptance tests, implementation phases, and production gates.

M0 is the foundation slice: organization isolation, dev/test authentication that fails closed in production, property and unit commands, and a small web shell. Ledger, screening, maintenance, and live providers are not implemented. Local setup and the current test evidence are in [docs/SETUP.md](docs/SETUP.md) and [docs/evidence](docs/evidence).

Business-specific fees, banking providers, landlord agreements, and legally reviewed screening policies remain explicit configuration and production prerequisites.
