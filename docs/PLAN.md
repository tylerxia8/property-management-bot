# Implementation plan

Source specification: `PRD.md` version 2.0 on `main`, commit `85f8615e4ccaccf4b5c33935e6422ad8273024b8`. SHA-256 `3d8a61c71b3c1bdb143d92319440506537cc2043b9334f939c33f31a765fab11`.

## How to read the earlier discovery note

The first discovery pass listed proposals D1–D24. Those proposals were not approved as a set. Technical choices actually used for M0 are the ADRs in `docs/adr/`. Anything that would change a financial rule, a housing decision, or an unspecified business policy stays unimplemented and is listed in `docs/DEPENDENCY_GATES.md`.

The original task asked for simulated financial execution until a banking provider and property accounting rules are confirmed, and for human review of housing decisions. Those instructions still bind later milestones. This M0 change has no payment execution and no housing decision.

Limits on external sends, paid services, production deploy, and merges are launch workflow boundaries for this agent. They are not recorded as additional end-user prohibitions, and they are not treated as contradictions inside the PRD. Missing production credentials are the gates the PRD already names in §11 and §18.

The task’s coverage list (accounting, prequalification, maintenance) names areas to build. It is not an approved reordering of PRD §17. Sequence follows §17 dependencies.

## Sequence

| Order | PRD phase | Milestone | Status |
| --- | --- | --- | --- |
| 0 | Discovery | Read the specification and record gates | Done |
| 1 | Phase 1 foundation | M0 auth, RLS, audit, outbox, idempotency, property/unit API, web shell | Implemented on this branch |
| 2 | Phase 2 accounting core | Immutable journal, receipt through reconciliation, invoice payable posting | Implemented on this branch. See `docs/PHASE2_SCOPE.md` |
| 3 | Phase 3 maintenance | Intake, media, emergencies, contractor work, invoice approval calling phase 2 | Implemented on this branch. See `docs/PHASE3_SCOPE.md`. Payable clearing stays behind ADR 0007. |
| 4 | Phase 4 prospects and tours | Intake, policy evaluator, human review, scheduling | Implemented on this branch. See `docs/PHASE4_SCOPE.md`. No consumer report and no live calendar. |
| 5 | Phase 5 statements and distributions | Close, statements, approval snapshots, instruction export, simulator settlement evidence | Implemented on this branch. See `docs/PHASE5_SCOPE.md` and ADR 0010. Provider submission stays disabled. |
| 6 | Phase 6 pilot and optional live payments | Provider sandbox or live adapter | Not started. Blocked by the §18 gates and by the instruction to keep money simulated until the provider and accounting rules are confirmed. |
| 7 | Local acceptance hardening | Security fixes, local worker, journeys, backup drill, accessibility scan | Implemented locally. This is not §16 staging acceptance. See `docs/ACCEPTANCE.md`. |

M0 does not pull phase 2–6 work forward.

## M0 scope

In scope:

- FastAPI service, Alembic revision, Next.js shell, lockfiles, setup and traceability docs
- Organizations, users, role grants, parties, encrypted contacts, properties, units
- Audit, outbox, encrypted inbox uniqueness, idempotency
- RLS, composite foreign keys, non-owner runtime role
- `GET /v1/me` and the property/unit commands in ADR 0004
- Dev/test local login that fails closed outside those environments

Out of scope: ledger, fees, distributions, prospects, maintenance workflows, provider adapters, production OIDC, a Celery dispatcher, backup-restore drills.
