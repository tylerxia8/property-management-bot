# ADR 0014 — GitHub Actions for the local evidence suite

Date: 2026-11-07

Status: accepted

## Decision

`.github/workflows/ci.yml` runs `scripts/run_m0_evidence.sh` on pull requests and on pushes to `main`. The job uses Ubuntu 24.04, CPython 3.12, Node 22, the distribution PostgreSQL and ffmpeg packages, and Playwright Chromium.

Python installs from `apps/api/requirements.lock`, then installs this repository with `--no-deps --no-build-isolation`. The web app installs with `npm ci`. The workflow token is limited to `contents: read`. It does not use `pull_request_target`, a repository secret, a payment provider, or a deployment.

## Consequences

A missing check run is not a success. Merging still has to observe the hosted conclusion for the current head and GitHub’s mergeability result.
