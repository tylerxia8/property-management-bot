# ADR 0004 — M0 HTTP surface

Date: 2026-11-07

Status: accepted for endpoints the PRD already names. The unit-route role split is an unconfirmed analogy and is called that in the API description. It is not a confirmed business policy.

## Context

PRD §9.2 names `GET /me`, `GET/POST /properties`, and `GET/PATCH /properties/{id}` for this foundation. Property creation is administrator creation. Property patch is a versioned manager edit. §9.1 defines the error envelope, cursor pagination, `Idempotency-Key` for financial commands, and `If-Match` for optimistic edits.

The property/unit distinction is confirmed, and M0’s scope includes a property/unit API. §9.2 does not list unit routes. Who may create a unit is not specified.

## Decision

Implemented routes:

| Method and path | Authorization in M0 | Notes |
| --- | --- | --- |
| `GET /v1/health` | Public | Reports `local_auth_enabled`. No tenant data. |
| `POST /v1/auth/local/login` | Dev/test only | See ADR 0002. |
| `GET /v1/me` | Any authenticated user | Roles are re-read from `role_grants`. |
| `GET /v1/properties` | `properties.read` | Cursor pagination. |
| `POST /v1/properties` | `properties.create` | Requires `Idempotency-Key`. |
| `GET /v1/properties/{id}` | `properties.read` | |
| `PATCH /v1/properties/{id}` | `properties.update` | Requires `If-Match`. |
| `GET /v1/properties/{id}/units` | `units.read` | |
| `POST /v1/properties/{id}/units` | `units.create` | Requires `Idempotency-Key`. |
| `PATCH /v1/properties/{id}/units/{unit_id}` | `units.update` | Requires `If-Match`. |

Capability map used by the server, not the browser:

- `organization_administrator`: `properties.read`, `properties.create`, `units.read`, `units.create`
- `property_manager`: `properties.read`, `properties.update`, `units.read`, `units.update`
- `accounting_staff`: `properties.read`, `units.read`
- `owner`, `tenant`, `prospect`, `contractor`, `ai_service`, `worker`: no M0 property or unit capability

A grant with `resource_type` or `resource_id` set is stored and does not add these capabilities. Only organization-wide grants (both null) apply. That is fail-closed behavior until resource scope has a specified evaluator.

Unit commands copy the property command split: administrators create, property managers edit, accounting staff read. This is an analogy with §9.2 so the unit API can be tested. It is not a confirmed unit policy. A later decision can replace it without a data migration.

`organization_id` is taken from the authenticated session. Bodies that include it are rejected (`extra=forbid`).

`Idempotency-Key` is required on property and unit creation even though §9.1 mandates it for financial commands specifically. M0 has no financial command yet; the same unique `(organization_id, key)` record, replay, and `409 IDEMPOTENCY_CONFLICT` behavior is what the foundation tests. No idempotency TTL is configured, because the PRD does not define one.

`If-Match` must carry the current integer version. Missing precondition returns `428 PRECONDITION_REQUIRED`. A stale version returns `409 VERSION_CONFLICT`.

`unit_count` in property responses is the count of `units` rows. It is not a separately stored marketing field.

Pagination cursors are opaque base64 JSON of `(created_at, id)`. Default limit 50, maximum 200.

Parties, encrypted contacts, and encrypted inbox payloads have database and service coverage and no public HTTP API. §9.2 does not name those routes.

## Consequences

- OpenAPI from the running app is the contract for these routes.
- The UI hides create and edit controls from its capability list, and the API enforces the same capabilities again.
- Replacing the unit role analogy does not require rewriting the ledger, because the ledger is not in this milestone.
