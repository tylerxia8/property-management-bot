# Open-source comparison and adopted improvements

Reviewed November 7, 2026 against the original three workflows in `PRD.md`.
Repository metadata, upstream READMEs, license files, PyPI metadata, and installed
wheel notices were inspected. This is a targeted fit review, not an independent
audit of every platform or a claim of accuracy on real tenant data.

## Findings

| Requirement | Candidate and source | Assessment and decision |
| --- | --- | --- |
| Accounting, reconciliation, statements | [ERPNext](https://github.com/frappe/erpnext), GPL-3.0; [Bigcapital](https://github.com/bigcapitalhq/bigcapital), AGPL-3.0 | Both offer broader corporate accounting workflows. Their documentation does not establish equivalence to our custody/pending/available cash states, per-owner restricted funds, immutable journals, or explicit distribution approval rules. Retain the existing ledger. Consider a separate corporate-books export later rather than introducing a second financial source of truth. |
| Rental administration | [MicroRealEstate](https://github.com/microrealestate/microrealestate) | Relevant leases/rents/receipts product. GitHub license metadata is ambiguous (`NOASSERTION`), and US trust-accounting equivalence was not established. No code copied or adopted. |
| Tour scheduling | [Cal.diy](https://github.com/calcom/cal.diy), MIT | Includes self-hosted scheduling, but the upstream README explicitly recommends personal, non-production use. Our current PostgreSQL holds already enforce overlap protection and DST clarification. No evidence that migrating improves the required safeguards. Keep holds; external calendar integration still requires an account and configured consent. |
| Conversational intake and human handoff | [Chatwoot](https://github.com/chatwoot/chatwoot), MIT outside enterprise code; [Frappe Helpdesk](https://github.com/frappe/helpdesk), AGPL-3.0 | Strong candidates for a staffed shared inbox, assignments, and communication history. Neither establishes better maintenance emergency recognition or lawful housing screening accuracy in our setting. Defer a separate inbox service until actual channels, staff, consent, and routing are configured. No outbound messages enabled. |
| Dialogue/NLU | [Rasa](https://github.com/RasaHQ/rasa), Apache-2.0 for the inspected repository | A real conversational framework, but needs training examples, evaluation, and hosting. No tenant corpus or labeled benchmark exists here. Replacing deterministic safety and screening logic would not be an evidenced accuracy improvement. Keep reviewed questions and human review; do not present this application as a trained model. |
| Inexact property hints | [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz), MIT, version 3.14.6 | **Adopted.** Offers typo-tolerant candidate ranking without an AI model or network service. Misspelled hints now return up to three confirmation suggestions. Fuzzy scores never select a unit, create a prospect, or make a housing decision. |
| iPhone maintenance photos | [pillow-heif](https://github.com/bigcat88/pillow_heif), version 1.8.1 | **Adopted for the existing dev/test media path.** Valid HEIC photos now produce JPEGs and thumbnails; EXIF orientation is applied before metadata removal. Previously all HEIC uploads were left unready. Corrupt files fail closed. Source license is BSD-3-Clause; the distributed binary wheels are GPLv2 because of bundled codecs. See the notices below. |
| Malware scanning | [ClamAV](https://github.com/Cisco-Talos/clamav), GPL-2.0 | Useful future external scanner, but image decoding is not malware scanning. Adopting an unconfigured adapter would not protect uploads. No claim of production media readiness; scanning, storage durability, signature freshness, and operational monitoring remain prerequisites. |

## Implemented behavior and limits

- Exact external listing IDs remain authoritative. An unknown external ID does
  not silently fall back to an address guess.
- Literal matching normalizes Unicode and case, treats SQL wildcard characters
  as text rather than patterns, and checks whole numeric tokens. `10 Elm Street`
  does not select `110 Elm Street`. Duplicate/ambiguous labels still require
  clarification. Candidate queries are organization-scoped and bounded to 1,001
  rows; more than 1,000 candidates fails closed to clarification.
- Fuzzy candidates use RapidFuzz WRatio with a 75 similarity cutoff. The cutoff
  is a suggestion filter, not a probability or housing policy. Hints shorter
  than four characters do not get fuzzy suggestions. No external service sees
  tenant information.
- HEIC decoding uses the primary image only, a 20 MB input limit, and a 40 million
  pixel decoded-image limit. JPEG/PNG derivatives are also orientation-corrected.
  Metadata is removed from derivatives; originals stay quarantined under the
  existing access rules. This does not remove sensitive content visible in a photo.
- Stored-media completion and checksum scanning now stream file hashes in 1 MB
  chunks instead of reading an entire stored video into another Python byte buffer.
  The initial HTTP upload still buffers its request body; decoded image memory
  is additional. This is not a whole-request memory bound or a faster-I/O claim.
- Production fixture scanning remains disabled, and the hosted demo retains
  `MEDIA_SCANNER=unset`. The new decoder does not enable production media uploads.

## Measurements and verification

Run `PYTHONPATH=apps/api/src python scripts/benchmark_open_source.py`.
On this Windows workstation, a synthetic 16 MiB file produced identical SHA-256
digests. Python allocation peaks were 16,785,882 bytes for the whole-file hash
versus 2,106,462 bytes for the streamed hash: **87.5% lower hashing peak memory**.
This uses `tracemalloc`, not process RSS or decoder memory.

One hundred in-memory typo queries across 1,000 fictional listing labels measured
5.482 ms median and 11.243 ms p95. This excludes database and HTTP latency; it is
not a claim that fuzzy matching is faster than the old substring lookup.

Twelve local component regressions cover typo suggestions, numeric conflicts,
wildcards, ambiguity, candidate bounds, real HEIC decoding, corrupt HEIC,
metadata removal, JPEG orientation, pixel limits, and disabled scanning. API
integration tests cover inquiry replay/external-ID precedence and HEIC download.
Full regression and demo-browser checks run in GitHub CI.

Regression hardening also found that request-scoped database cleanup could run
after an HTTP response had started. A local failure probe returned HTTP 201
despite a failed commit under the old scope. Database dependencies now use
FastAPI's function scope so commit/rollback completes before the response is
sent. Two API regressions check failed-commit status and visibility from a
separate database connection at response start. Property creation also waits
for initial loading and uses its confirmed response instead of allowing stale
list loads to hide the new record. Browser tests assert mutation API results
and CI retains browser failure evidence.

OSV's package/version query returned no vulnerability IDs for RapidFuzz 3.14.6
or pillow-heif 1.8.1 on the review date. This is not a security audit of their
native codec libraries. Versions are pinned in `requirements.lock`.

## Dependency notices and distribution

Upstream notices are retained verbatim in `docs/licenses/`:

- [RapidFuzz MIT notice](licenses/RapidFuzz-MIT.txt)
- [pillow-heif source notice](licenses/pillow-heif-BSD.txt)
- [pillow-heif binary codec notices and versioned source links](licenses/pillow-heif-bundled.txt)

The pillow-heif wheel includes libheif, libde265, and x265. Its binary license
must not be described as BSD-only. Installed dependency distributions retain
their upstream notices. The source demo zip includes these notices and installs
unmodified dependencies during the user's image build; it does not contain
vendored wheels or Docker images. Any subsequent binary redistribution must
preserve the applicable license and corresponding-source requirements.
