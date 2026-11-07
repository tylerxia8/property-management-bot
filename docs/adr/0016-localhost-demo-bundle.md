# ADR 0016 — Localhost Docker demo bundle

Date: 2026-11-07

Status: accepted

## Decision

The fixture sample can be started on the operator's computer with Docker Compose. The web server is published only on `127.0.0.1:3000`. The browser calls `/v1` on that same origin, and Next proxies to the API container. Postgres has no host port. The compose project and volume are named `grok-property-sample` and `grok-property-sample-pg`.

Role and database passwords are generated on the computer into an untracked `.env` when the bundle starts. They are not stored in the image or the zip. `APP_ENV` stays `test` for this bundle. `DEMO_FIXTURE=sample` is required for the role buttons. Payment, messaging, and calendar outbound stay unset or off. The bootstrap SQL creates `grok_demo_sample` and does not create the test or e2e databases.

## Consequences

Image builds use `postgres:16.10-bookworm`, `python:3.12.3-slim-bookworm`, and `node:22.23.4-bookworm-slim`. Those registry indexes include `linux/arm64` and `linux/amd64`. A Mac launcher is `start-macos.sh`. It was not executed on Apple silicon. The bundle does not install ffmpeg, so media derivatives are not produced. This is not a production deployment.
