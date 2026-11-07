# ADR 0002 — Dev/test local auth is not production OIDC or MFA

Date: 2026-11-07

Status: accepted as a technical test seam. Not an approval of a production identity provider, and not a substitute for PRD §3 MFA or §11 OIDC.

## Context

M0 has to exercise server-side authorization against real roles. The OIDC vendor is unselected (PRD §7.1 and §11). PRD §3 requires MFA and step-up for financial approval, recipient bank changes, and privileged role changes. M0 does not expose those privileged mutations.

This agent’s launch limits avoid paid identity services. That limit is a workflow boundary. It is not recorded here as an end-user prohibition or as a contradiction in the PRD. Production OIDC remains a §18-style integration gate.

## Decision

- `APP_ENV` defaults to `production`.
- `POST /v1/auth/local/login` is mounted only when `APP_ENV` is `development` or `test`. Otherwise the route is absent.
- Tokens minted by that route carry `amr=local_dev` and the environment name. Verifiers reject them unless local auth is enabled for that same environment.
- No `amr=oidc` token is accepted. OIDC verification is not implemented.
- The local issuer stored on dev/test users is the sentinel `https://local.invalid/dev-auth`. It is not an OIDC discovery URL. The login route does not accept a caller-supplied issuer.
- Password hashes use `pgcrypto` `crypt()` and stay in `users.dev_password_hash`. The runtime role `grok_app` has no `SELECT` privilege on that column. Login comparison runs inside `SECURITY DEFINER` function `app_local_login`, owned by `grok_auth`.
- A hash present in the database does not enable production login.
- The seed script refuses to run unless `APP_ENV` is `development` or `test`, and refuses database names that do not end in `_dev`, `_test`, or `_e2e`.
- Local token lifetime defaults to 8 hours. That number is a dev session bound, not an MFA step-up window. PRD §3 “recent step-up” has no confirmed duration, so none is invented.

M0 does not issue cookie sessions and does not implement CSRF or step-up. Those stay incomplete until a real OIDC/session design is chosen. The web shell states on screen that local sign-in is not production OIDC or MFA.

## Consequences

- API tests cover production fail-closed behavior with the same database that contains a dev password hash.
- Shipping this route to a production process would require `APP_ENV=production`, which does not mount the route and does not honor local tokens.
- Financial approval endpoints are not part of M0, so this ADR does not satisfy the MFA requirement for payments.
