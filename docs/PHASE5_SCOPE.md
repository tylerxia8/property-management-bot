# Phase 5 scope — statements and distribution controls

PRD §17 phase 5: period close, owner statements, distribution proposals, approval snapshots, instruction export, and settlement evidence. Live payment submission stays off.

Phase 6 pilot and live bank execution stay unbuilt.

## Actor isolation, before the new tables

A `grok_app` connection that set only `app.organization_id` could read that organization's properties, leases, journals, receipts, prospects, intakes, and maintenance rows. Accommodation cases were already closed. Entry-secret reads were open. That is fail-open actor isolation: a forgotten actor, or a pooled session that kept an organization and dropped the actor, exposed owner and tenant data. It was not harmless.

Runtime policies now require a real actor with a matching role, or an explicit row relationship. `grok_posting` remains the journal function owner and is named in the journal and period-close policies. `grok_migrator` is the superuser used by Alembic and is not a runtime identity. There is no actorless allow rule. A connection that already has the `grok_app` password can still set `app.actor_id`; the control closes the missing-actor leak, and it is not a second credential.

## In this milestone

- Distribution batches draft owner, contractor, and management items from ledger balances. Reserves and security deposits are not items. A negative owner balance is omitted, not netted across properties.
- Validation locks funding lots for that property and reserves cents. Another property's cash cannot fund the item.
- Approval stores the manager, a dev/test step-up timestamp, and the snapshot hash. Production has no step-up route. If step-up freshness is not configured, approval returns `CONFIGURATION_REQUIRED`. Tests pass an explicit approval lifetime. The PRD's 24 hours is not applied silently.
- A destination version or amount change makes the hash stale. Submit and export then return `APPROVAL_INVALID`.
- Export keeps the batch and item ids, writes an audit row, and does not settle. A second export returns the same artifact and a duplicate-download warning.
- `POST /distribution-batches/{id}/submit` exists. With the simulator unset, or in production, it returns `409 PROVIDER_SUBMISSION_DISABLED`. It does not 404.
- `payment_simulator=enabled` is accepted only when `APP_ENV` is development or test. It records simulator events and can post the same settlement journals as the ledger commands. Those journals are simulator settlement, not a bank transfer. The old simulated-settlement routes stay `409 APPROVAL_CONTRACT_REQUIRED` even if the fixture flag is true.
- A return after settlement debits account 1040, credits bank 1030, freezes the property, and keeps the settlement row.
- Owner statements are immutable snapshots. An owner sees only a linked party. Another owner and a prospect see none.

## Not in this milestone

- A live payment provider or a real bank file
- Production OIDC or MFA
- Phase 6 rollout
- Automated housing decisions
- A new fee, share, or priority rule
