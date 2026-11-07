# Phase 3 scope — maintenance

PRD §17 phase 3: issue playbooks, durable incomplete intake, media, emergencies, contractor scheduling, completion, and invoices. Approved invoices use the phase 2 payable command.

Phase 4 prospects and phase 5 statements and distribution controls stay unbuilt.

## In this milestone

- A ticket is stored on the first legitimate report, including when media and access windows are missing
- Eight intake fields, each `PROVIDED`, `UNKNOWN`, `DECLINED`, or `NOT_PRACTICAL`
- Reviewed template playbooks. One or two questions a turn. Handoff after three replies or when the tenant asks to stop
- Deterministic emergency rules run before questions. The safety text is the PRD template. No claim that responders were contacted. Gas guidance does not say to operate switches
- Escalation rows, acknowledgement, and fallback attempts on an injectable clock. Notification rows stay unsent
- Unverified callers get a ticket and no occupancy or address
- Accommodation notes and door codes are stored apart from the contractor view. Door codes are encrypted and kept out of notification payloads
- Media quarantine, magic-byte checks, checksum and size checks, JPEG/PNG EXIF stripping and thumbnails, and ffmpeg duration checks for MP4/MOV
- The byte scanner runs only when `APP_ENV` is development or test and `media_scanner=fixture`. It is named as a fixture. Production cannot mark an object ready with it
- HEIC is recognized and left unready when this environment cannot convert it
- Manager-only contractor assignment. Contractors see only the assigned ticket. Availability is not entry permission
- Completion does not post a payable. Manager approval uses the existing invoice approval command once. Reopen keeps assignments and invoices
- No model calls. Questions come from templates. A classifier result cannot clear an emergency

## Not in this milestone

- Prospect prequalification and tour booking
- Distribution-batch approval, export, and owner statements
- A staffed on-call vendor. Without a configured destination, escalation is recorded as `DESTINATION_UNCONFIGURED` and nothing is sent
- A spending-limit number. Estimates wait for authorization. No threshold is invented
- A statutory notice period. Confirmation requires manager-supplied notice evidence, entry permission, and contractor acceptance
- Production malware scanning, KMS, and object storage

## Fixture boundary

`media_scanner=fixture` in production does not scan objects into `READY`. The same rule is used for the ledger settlement flag in ADR 0007.

## Gap found before this module

Phase 2 had left four manager routes that could reserve a distribution or clear a payable with no approval snapshot. ADR 0007 gates them. Invoice approval is unchanged: it posts one payable and does not clear cash.
