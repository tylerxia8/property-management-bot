# Local acceptance matrix

Date: 2026-11-07. This is the local implementation record. It is not PRD §16 staging acceptance. Staging acceptance requires realistic data in a staging environment, named reviewers, and the §18 production gates. Those gates are still open. No live payment, message, calendar, or consumer-report integration is configured.

| Requirement | Status | Evidence |
| --- | --- | --- |
| Organization RLS, missing actor fails closed, pool checkout clears identity | Implemented | `test_actor_unset_and_stale_pool_hide_rows`, `test_portal_actor_cannot_read_other_people_rows` |
| API does not trust a client-sent actor, role, or organization | Implemented | Principal comes from the signed local token. Webhook organization is accepted only after HMAC, and the worker checks the named user is a manager in that organization |
| Bearer session expiry | Implemented | `verify_token` rejects `exp` in the past. Cookie CSRF is not implemented because there is no cookie session. ADR 0011 |
| Approval lifetime is not caller-controlled | Implemented | `test_client_cannot_choose_approval_lifetime`. Default `APPROVAL_TTL_HOURS=0` returns `CONFIGURATION_REQUIRED`. Tests and the browser process set 24 as a fixture |
| Snapshot recomputed on approve, export, submit, and settlement | Implemented | `_require_current_approval` and `_assert_snapshot_inputs`. Destination party, version, and reserved cents are checked. Export past the policy window returns `APPROVAL_EXPIRED` |
| Simulator and step-up closed in production | Implemented | `test_production_closes_simulator_step_up_and_webhooks` |
| Old payable and declaration routes cannot bypass approval | Implemented | `test_fixture_flag_still_cannot_clear_a_payable` covers all four routes |
| FIN-01 through FIN-19 | Implemented locally | `docs/TRACEABILITY.md`. FIN-04 worker proof is `test_fin_04_worker_replays_one_payable`: 100 signed webhooks and 100 worker passes, one payable journal |
| FIN-08 provider timeout | Partial | Deterministic simulator only. No provider was contacted. `bank_contacted` is false |
| PRO-01 through PRO-12 | Implemented locally | `tests/test_prospects.py` |
| MNT-01 through MNT-11 | Implemented locally | `tests/test_maintenance.py` |
| §15.4 three journeys, plus return/timeout and emergency | Implemented locally | `test_journey_receipt_to_export_timeout_and_return`, `test_journey_inquiry_to_invitation`, `test_journey_repair_and_emergency` |
| Property-based cent conservation and stateful double allocation | Implemented | `tests/test_money_invariants.py`, `test_stateful_receipts_cannot_be_allocated_twice` |
| Signed webhook invalid signature, stale timestamp, and replay | Implemented for the local contract | `test_fin_04_worker_replays_one_payable`. Production ingress stays `WEBHOOK_NOT_CONFIGURED` |
| Transactional outbox worker, delivery disabled, retry then dead letter | Implemented | `test_worker_retries_then_dead_letters_without_delivery`. Redis is not installed |
| OpenAPI 0.1.0 and generated TypeScript path list | Implemented | `apps/web/lib/api-types.generated.ts`, `test_openapi_types_match_the_running_app` |
| Media symlink escape | Implemented | `safe_media_file`, `test_media_symlink_is_not_opened`. Scanner still fails closed unless the dev/test fixture flag is set |
| Migration roundtrip and destructive downgrade refusal | Implemented | `test_migration_up_down_up`, `test_downgrade_without_flag_is_refused` |
| Local backup restore | Executed as a drill | `scripts/backup_restore_drill.sh`, `docs/evidence/backup-restore.txt`. Not an encrypted quarterly PITR |
| Core axe scan | Executed in Playwright | `apps/web/tests/accessibility.spec.ts`. Not a WCAG certification or screen-reader audit |
| Operations queue | Partial | `GET /v1/operations/queue` returns dead letters, unknown payments, approved batches, and unassigned emergencies. `alerts_sent` is false. Nothing is paged |
| OIDC, MFA, KMS, live bank, Celery, Redis, object storage, legal retention | Gated | `docs/DEPENDENCY_GATES.md` and PRD §18. Not labeled as a later phase in order to hide them |
| Load test at 10× planned volume | Not run | No staging environment in this milestone |
| Manual screen-reader pass | Not run | Not claimed |

The latest command log is `docs/evidence/README.md`. A passing local suite does not accept the MVP.
