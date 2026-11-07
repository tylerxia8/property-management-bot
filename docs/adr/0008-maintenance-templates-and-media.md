# ADR 0008 — Maintenance templates and local media checks

Date: 2026-11-07

Status: accepted as the phase 3 implementation. Not a counsel-approved emergency list or a production antivirus product.

## Decision

Questions and the emergency safety sentence are fixed templates from PRD §6.2 and §6.3. The process does not call a model. `classifier_result` is stored as untrusted text and cannot de-escalate. Only a property manager, with a reason, can clear the emergency flag.

The emergency phrases are the PRD examples: gas, fire, smoke, sparking, shock, flooding, sewage, and collapse or a rapidly sagging ceiling. They are not represented as a complete legal definition. Essential-service wording without those phrases is marked urgent for a person and does not pretend to be a life-safety match.

Escalation timing uses the PRD’s proposed 5-minute fallback and 10-minute repeat. Tests move a clock. Jobs are inserted as local records. `delivered_at` stays null. A missing staffed destination is `DESTINATION_UNCONFIGURED`.

Media checks that this machine can actually perform:

- JPEG and PNG are opened with Pillow 13.0.0. EXIF is dropped by saving a new image. A thumbnail is written
- MP4 and MOV durations are read with ffprobe. Files longer than 2 minutes, or files ffprobe cannot read, stay unready. A metadata-stripped MP4 derivative is made with ffmpeg when the probe succeeds
- Declared type must match the file magic. Executables and archives are rejected
- HEIC brands are detected. Pillow in this environment does not convert HEIC, so those objects are rejected with `HEIC_CONVERSION_UNAVAILABLE` instead of being marked ready

The scanner record says `fixture-byte-scanner`. That string is not a production malware engine.

Door codes use the existing AES-GCM helper. Contractor payloads and notification JSON omit them. Entry permission is a separate flag from access windows. No notice-day count is coded.

Invoice approval calls `approve_invoice` from phase 2. Completion and upload do not.

## Consequences

A later production scanner has to be a different mode that is allowed when `APP_ENV=production`. The fixture mode will keep refusing there.
