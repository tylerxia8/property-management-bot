import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.auth.tokens import _sign, verify_token
from grok_bot.crypto import encrypt_text
from grok_bot.db import set_tenant
from grok_bot.domain.accounting import approve_invoice, submit_invoice
from grok_bot.domain.media_scan import sha256_file, scan_stored_file
from grok_bot.domain.records import write_audit, write_outbox
from grok_bot.domain.maintenance_workspace import ticket_details
from grok_bot.errors import problem
from grok_bot.redaction import redact

def safe_media_file(root: Path, key: str, *, allow_missing: bool = False) -> Path:
    parts = Path(key).parts
    if not key or Path(key).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        problem(404, "NOT_FOUND", "Media not found.")
    current = root
    if current.is_symlink():
        problem(404, "NOT_FOUND", "Media not found.")
    for part in parts:
        current = current / part
        if current.is_symlink():
            problem(404, "NOT_FOUND", "Media not found.")
    if not allow_missing and not current.is_file():
        problem(404, "NOT_FOUND", "Media not found.")
    return current


SAFETY_MESSAGE = "If there is immediate danger, leave the area if safe and call 911 or the appropriate emergency service."
GAS_GUIDANCE = "Do not operate electrical switches."
FIELD_ORDER = (
    "identity_property",
    "description",
    "exact_location",
    "onset_frequency",
    "media",
    "contact",
    "access_windows",
    "entry_safety",
)
LIFE_SAFETY_TERMS = (
    "smell gas",
    "gas leak",
    "smell of gas",
    "rotten egg",
    "fire",
    "smoke",
    "sparking",
    "sparks",
    "electric shock",
    "i was shocked",
    "flooding",
    "sewage",
    "collapse",
    "collapsing",
    "sagging ceiling",
    "carbon monoxide",
    "co alarm",
    "gas smell",
    "burning smell",
    "exposed wire",
    "live wire",
    "spark",
)
URGENT_TERMS = ("no heat", "no cooling", "no hot water")
PLAYBOOKS = {
    "leak": {
        "exact_location": "Which room and fixture is leaking, and is the water clean or sewage?",
        "onset_frequency": "When did you first notice it, and does it happen continuously or only after use?",
        "media": "If safe, please send a wide photo showing where the leak is and a close-up of the visible source.",
        "entry_safety": "Are there hazards or pets near the leak? Do not touch electrical equipment.",
        "access_windows": "What access windows work for you? Fewer than three does not block this request.",
        "contact": "What is the best way and time to reach you about this repair?",
    },
    "general": {
        "exact_location": "Where in the home is the problem, including the room and fixture if there is one?",
        "onset_frequency": "When did it start, and is it continuous or intermittent?",
        "media": "If it is safe, a wide photo and a close-up help the contractor prepare.",
        "entry_safety": "Are there hazards, pets, or limits on how someone should enter?",
        "access_windows": "What access windows work for you? One window is enough to keep the request open.",
        "contact": "What is the best way and time to reach you about this repair?",
    },
}
PLAYBOOKS["hvac"] = {
    **PLAYBOOKS["general"],
    "exact_location": "Is this no heat, no cooling, or weak airflow, and which rooms are affected?",
    "media": "If safe, send a photo of the thermostat or an accessible equipment label. Do not dismantle the equipment.",
}
PLAYBOOKS["electrical"] = {
    **PLAYBOOKS["general"],
    "exact_location": "Which fixtures or outlets are affected? Stay at a safe distance.",
    "media": "If safe, send a photo from a distance. Do not open panels or touch wires.",
}
PLAYBOOKS["appliance"] = {
    **PLAYBOOKS["general"],
    "exact_location": "Which appliance is affected, and is there an error code you can read without taking it apart?",
}
PLAYBOOKS["structural"] = {
    **PLAYBOOKS["general"],
    "exact_location": "Which wall, ceiling, or roof area is affected? Do not climb.",
    "media": "If safe, send a wide photo and a close-up from a stable position. Do not climb.",
}
PLAYBOOKS["pest_mold"] = {
    **PLAYBOOKS["general"],
    "exact_location": "Where is the pest, mold, or moisture, and how large is the area? This intake does not diagnose a health condition.",
}
PLAYBOOKS["lock"] = {
    **PLAYBOOKS["general"],
    "exact_location": "Which door is affected, and can the home be secured?",
}


def create_verified_ticket(session, organization_id, user_id, body, secret: str, when: datetime) -> dict:
    requested_unit = body.get("unit_id")
    requested_lease = body.get("lease_id")
    lease = _lease_for_user(session, organization_id, user_id, requested_unit, requested_lease)
    reported_safety = " ".join(str(body.get(k) or "") for k in ("description", "location", "safety_concerns"))
    if (requested_unit or requested_lease) and lease is None and not _classify(reported_safety)[0]:
        problem(422, "INVALID_HOME", "Choose a home linked to your tenancy.")
    text_value = body.get("description") or ""
    return _create_ticket(
        session,
        organization_id,
        secret,
        description=text_value,
        verification="VERIFIED" if lease else "UNVERIFIED",
        unit_id=lease["unit_id"] if lease else None,
        lease_id=lease["id"] if lease else None,
        reporter_user_id=user_id,
        identity_status="PROVIDED" if lease else "UNKNOWN",
        when=when,
        intake=body,
        category=body.get("category"),
    )


def create_unverified_ticket(session, organization_id, description: str, secret: str, when: datetime) -> dict:
    return _create_ticket(
        session,
        organization_id,
        secret,
        description=description,
        verification="UNVERIFIED",
        unit_id=None,
        lease_id=None,
        reporter_user_id=None,
        identity_status="UNKNOWN",
        when=when,
        intake={},
        category=None,
        public=True,
    )


def add_message(session, organization_id, ticket_id, body: str, classifier_result: str | None, secret: str, clock, actor_id, field_key: str | None = None) -> dict:
    ticket = _lock_ticket(session, organization_id, ticket_id)
    structured_answer = field_key is not None
    if field_key is not None and field_key != "general" and field_key not in PLAYBOOKS.get(ticket["category"], PLAYBOOKS["general"]):
        problem(422, "VALIDATION_ERROR", "Choose a valid follow-up question.")
    session.execute(
        text(
            """
            INSERT INTO ticket_messages (id, organization_id, ticket_id, body, classifier_result)
            VALUES (:id, :organization_id, :ticket_id, :body, :classifier_result)
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "ticket_id": ticket_id,
            "body": body,
            "classifier_result": classifier_result,
        },
    )
    life_safety, urgent = _classify(body)
    now = clock.now()
    if life_safety or ticket["emergency"]:
        _mark_emergency(
            session,
            organization_id,
            ticket_id,
            actor_id,
            now,
            life_safety=True,
            safety_context="gas" if _gas(body) or _gas(ticket["description"] or "") else "",
        )
        if classifier_result:
            write_audit(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="maintenance.classifier_ignored",
                target_type="maintenance_ticket",
                target_id=ticket_id,
                target_version=None,
                request_id="maintenance",
                before_state=None,
                after_state={"classifier_result": classifier_result, "emergency_unchanged": True},
            )
        return get_ticket(session, organization_id, ticket_id, secret, viewer="manager", persist_questions=False)
    if urgent:
        session.execute(
            text("UPDATE maintenance_tickets SET urgent_triage = true WHERE organization_id = :organization_id AND id = :id"),
            {"organization_id": organization_id, "id": ticket_id},
        )
        _open_escalation(session, organization_id, ticket_id, actor_id, now, life_safety=False)
    asked = ticket["asked_fields"] if isinstance(ticket["asked_fields"], list) else json.loads(ticket["asked_fields"] or "[]")
    if field_key is not None:
        asked = [] if field_key == "general" else [field_key]
    if structured_answer:
        for answered_field in asked:
            _set_field(session, organization_id, ticket_id, answered_field, "PROVIDED", body, None)
    attempts = ticket["clarification_attempts"] + (1 if not structured_answer and (asked or _handoff_requested(body)) else 0)
    if _handoff_requested(body) or attempts >= 3:
        session.execute(
            text(
                """
                UPDATE maintenance_tickets
                SET handoff = true, clarification_attempts = :attempts, asked_fields = '[]'::jsonb,
                    status = CASE WHEN status = 'INTAKE_OPEN' THEN 'MANAGER_REVIEW' ELSE status END
                WHERE organization_id = :organization_id AND id = :id
                """
            ),
            {"attempts": attempts, "organization_id": organization_id, "id": ticket_id},
        )
        return get_ticket(session, organization_id, ticket_id, secret, viewer="manager", persist_questions=False)
    if asked:
        session.execute(
            text(
                """
                UPDATE maintenance_tickets
                SET clarification_attempts = :attempts
                WHERE organization_id = :organization_id AND id = :id
                """
            ),
            {"attempts": attempts, "organization_id": organization_id, "id": ticket_id},
        )
    return get_ticket(session, organization_id, ticket_id, secret, viewer="manager", persist_questions=True)


def set_intake(session, organization_id, ticket_id, field_key, status, value, reason) -> dict:
    if field_key not in FIELD_ORDER:
        problem(422, "VALIDATION_ERROR", "Unknown intake field.")
    if status not in {"PROVIDED", "UNKNOWN", "DECLINED", "NOT_PRACTICAL"}:
        problem(422, "VALIDATION_ERROR", "Unknown intake status.")
    _lock_ticket(session, organization_id, ticket_id)
    _set_field(session, organization_id, ticket_id, field_key, status, value, reason)
    return {"field_key": field_key, "status": status}


def acknowledge(session, organization_id, escalation_id, user_id, clock) -> dict:
    row = session.execute(
        text("SELECT id, ticket_id, state FROM escalations WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": escalation_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Escalation not found.")
    session.execute(
        text(
            """
            UPDATE escalations
            SET state = 'ACKNOWLEDGED', acknowledged_by = :user_id, acknowledged_at = :now
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"user_id": user_id, "now": clock.now(), "organization_id": organization_id, "id": escalation_id},
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=user_id,
        action="maintenance.escalation_acknowledged",
        target_type="escalation",
        target_id=escalation_id,
        target_version=None,
        request_id="maintenance",
        before_state={"state": row["state"]},
        after_state={"state": "ACKNOWLEDGED"},
    )
    return {"id": str(escalation_id), "state": "ACKNOWLEDGED"}


def deescalate(session, organization_id, ticket_id, user_id, reason: str) -> dict:
    if not reason.strip():
        problem(422, "VALIDATION_ERROR", "A reason is required to clear an emergency.")
    _lock_ticket(session, organization_id, ticket_id)
    session.execute(
        text(
            """
            UPDATE maintenance_tickets
            SET emergency = false, deescalated_by = :user_id, deescalation_reason = :reason
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"user_id": user_id, "reason": reason, "organization_id": organization_id, "id": ticket_id},
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=user_id,
        action="maintenance.deescalated",
        target_type="maintenance_ticket",
        target_id=ticket_id,
        target_version=None,
        request_id="maintenance",
        before_state={"emergency": True},
        after_state={"emergency": False, "reason": reason},
    )
    return {"id": str(ticket_id), "emergency": False}


def advance_escalations(session, organization_id, clock, actor_id) -> dict:
    now = clock.now()
    rows = session.execute(
        text(
            """
            SELECT id, ticket_id, created_at, state
            FROM escalations
            WHERE organization_id = :organization_id AND state = 'OPEN'
            """
        ),
        {"organization_id": organization_id},
    ).mappings().all()
    created = 0
    for row in rows:
        jobs = session.execute(
            text(
                """
                SELECT kind, scheduled_for FROM notification_jobs
                WHERE organization_id = :organization_id AND escalation_id = :escalation_id
                ORDER BY scheduled_for
                """
            ),
            {"organization_id": organization_id, "escalation_id": row["id"]},
        ).mappings().all()
        kinds = {job["kind"] for job in jobs}
        if "fallback" not in kinds and now - row["created_at"] >= timedelta(minutes=5):
            _notification(session, organization_id, row["ticket_id"], row["id"], "fallback", now)
            created += 1
            write_audit(
                session,
                organization_id=organization_id,
                actor_id=actor_id,
                action="maintenance.escalation_fallback",
                target_type="escalation",
                target_id=row["id"],
                target_version=None,
                request_id="maintenance",
                before_state={"fallback": False},
                after_state={"fallback": True},
            )
        elif "fallback" in kinds and jobs and now - jobs[-1]["scheduled_for"] >= timedelta(minutes=10):
            _notification(session, organization_id, row["ticket_id"], row["id"], "repeat", now)
            created += 1
    return {"recorded_attempts": created}


def request_upload(session, organization_id, ticket_id, declared_content_type: str, size_bytes: int, filename: str, sha256: str) -> dict:
    _lock_ticket(session, organization_id, ticket_id)
    count = session.execute(
        text("SELECT count(*) FROM media_objects WHERE organization_id = :organization_id AND ticket_id = :ticket_id"),
        {"organization_id": organization_id, "ticket_id": ticket_id},
    ).scalar()
    if count >= 10:
        problem(422, "MEDIA_LIMIT", "This ticket already has the configured number of files.")
    if declared_content_type.startswith("image/") and size_bytes > 20 * 1024 * 1024:
        problem(422, "MEDIA_LIMIT", "Images are limited to 20 MB.")
    if declared_content_type.startswith("video/") and size_bytes > 200 * 1024 * 1024:
        problem(422, "MEDIA_LIMIT", "Videos are limited to 200 MB.")
    media_id = uuid4()
    storage_key = f"{organization_id}/{ticket_id}/{media_id}/original"
    session.execute(
        text(
            """
            INSERT INTO media_objects (
              id, organization_id, ticket_id, status, declared_content_type, size_bytes, sha256, storage_key
            ) VALUES (
              :id, :organization_id, :ticket_id, 'QUARANTINED', :declared_content_type, :size_bytes, :sha256, :storage_key
            )
            """
        ),
        {
            "id": media_id,
            "organization_id": organization_id,
            "ticket_id": ticket_id,
            "declared_content_type": declared_content_type,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "storage_key": storage_key,
        },
    )
    del filename
    return {"id": str(media_id), "status": "QUARANTINED", "storage_key": storage_key}


def store_and_scan(session, settings, organization_id, media_id, payload: bytes | None) -> dict:
    row = session.execute(
        text("SELECT * FROM media_objects WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": media_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Media not found.")
    path = safe_media_file(Path(settings.media_root), row["storage_key"], allow_missing=True)
    if payload is None:
        if not path.exists():
            problem(409, "UPLOAD_INCOMPLETE", "The quarantined upload has not arrived.")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    declared_hash = row["sha256"]
    session.execute(
        text("UPDATE media_objects SET status = 'SCANNING' WHERE id = :id"),
        {"id": media_id},
    )
    if row["size_bytes"] is not None and path.stat().st_size != row["size_bytes"]:
        session.execute(
            text("UPDATE media_objects SET status = 'REJECTED', scan_code = 'SIZE_MISMATCH', rejection_reason = 'Declared size does not match the upload.' WHERE id = :id"),
            {"id": media_id},
        )
        return {"id": str(media_id), "status": "REJECTED", "scan_code": "SIZE_MISMATCH", "scanner_name": None, "ticket_id": str(row["ticket_id"])}
    if declared_hash and sha256_file(path) != declared_hash:
        session.execute(
            text("UPDATE media_objects SET status = 'REJECTED', scan_code = 'CHECKSUM_MISMATCH', rejection_reason = 'Declared checksum does not match the upload.' WHERE id = :id"),
            {"id": media_id},
        )
        return {"id": str(media_id), "status": "REJECTED", "scan_code": "CHECKSUM_MISMATCH", "scanner_name": None, "ticket_id": str(row["ticket_id"])}
    result = scan_stored_file(
        path=path,
        declared_content_type=row["declared_content_type"],
        expected_sha256=declared_hash,
        fixture_allowed=settings.fixture_media_scanner_allowed,
    )
    status = "READY" if result.ready else "REJECTED"
    derivative = None
    if result.ready and (path.parent / "derivative.jpg").exists():
        derivative = str(Path(row["storage_key"]).parent / "derivative.jpg")
    if result.ready and (path.parent / "derivative.mp4").exists():
        derivative = str(Path(row["storage_key"]).parent / "derivative.mp4")
    session.execute(
        text(
            """
            UPDATE media_objects
            SET status = :status, detected_type = :detected_type, scanner_name = :scanner_name,
                scan_code = :scan_code, rejection_reason = :reason, derivative_key = :derivative_key,
                sha256 = :sha256
            WHERE id = :id
            """
        ),
        {
            "status": status,
            "detected_type": result.detected_type,
            "scanner_name": result.scanner_name,
            "scan_code": result.code,
            "reason": result.reason,
            "derivative_key": derivative,
            "sha256": sha256_file(path),
            "id": media_id,
        },
    )
    if result.ready:
        _set_field(session, organization_id, row["ticket_id"], "media", "PROVIDED", "Photo attached", None)
    return {"id": str(media_id), "status": status, "scan_code": result.code, "scanner_name": result.scanner_name, "ticket_id": str(row["ticket_id"])}


def assign_contractor(session, organization_id, ticket_id, profile_id, scope: str, actor_id) -> dict:
    profile = session.execute(
        text("SELECT id, approved FROM contractor_profiles WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": profile_id},
    ).mappings().first()
    if profile is None or not profile["approved"]:
        problem(409, "CONTRACTOR_NOT_APPROVED", "Assignment requires an approved contractor.")
    assignment_id = uuid4()
    work_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO assignments (id, organization_id, ticket_id, contractor_profile_id, status, scope)
            VALUES (:id, :organization_id, :ticket_id, :profile_id, 'PENDING', :scope)
            """
        ),
        {
            "id": assignment_id,
            "organization_id": organization_id,
            "ticket_id": ticket_id,
            "profile_id": profile_id,
            "scope": scope,
        },
    )
    session.execute(
        text(
            """
            INSERT INTO work_orders (id, organization_id, ticket_id, assignment_id)
            VALUES (:id, :organization_id, :ticket_id, :assignment_id)
            """
        ),
        {"id": work_id, "organization_id": organization_id, "ticket_id": ticket_id, "assignment_id": assignment_id},
    )
    session.execute(
        text("UPDATE maintenance_tickets SET status = 'ASSIGNED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": ticket_id},
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="maintenance.assigned",
        target_type="maintenance_ticket",
        target_id=ticket_id,
        target_version=None,
        request_id="maintenance",
        before_state=None,
        after_state={"assignment_id": str(assignment_id)},
    )
    return {"assignment_id": str(assignment_id), "work_order_id": str(work_id), "status": "ASSIGNED"}


def respond_assignment(session, organization_id, assignment_id, user_id, accept: bool) -> dict:
    row = _assignment_for_user(session, organization_id, assignment_id, user_id)
    status = "ACCEPTED" if accept else "DECLINED"
    session.execute(
        text("UPDATE assignments SET status = :status WHERE organization_id = :organization_id AND id = :id"),
        {"status": status, "organization_id": organization_id, "id": row["id"]},
    )
    return {"id": str(row["id"]), "status": status}


def complete_work(session, organization_id, work_order_id, notes: str) -> dict:
    session.execute(
        text(
            """
            UPDATE work_orders
            SET completion_notes = :notes, completed_at = clock_timestamp()
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"notes": notes, "organization_id": organization_id, "id": work_order_id},
    )
    ticket_id = session.execute(
        text("SELECT ticket_id FROM work_orders WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": work_order_id},
    ).scalar()
    session.execute(
        text("UPDATE maintenance_tickets SET status = 'COMPLETION_REVIEW' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": ticket_id},
    )
    return {"work_order_id": str(work_order_id), "status": "COMPLETION_REVIEW", "payable_journal_id": None}


def submit_work_invoice(session, organization_id, work_order_id, body: dict) -> dict:
    work = session.execute(
        text("SELECT id, ticket_id FROM work_orders WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": work_order_id},
    ).mappings().first()
    invoice = submit_invoice(session, organization_id, body)
    session.execute(
        text(
            """
            INSERT INTO maintenance_invoice_links (
              id, organization_id, ticket_id, work_order_id, invoice_id
            ) VALUES (
              :id, :organization_id, :ticket_id, :work_order_id, :invoice_id
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "ticket_id": work["ticket_id"],
            "work_order_id": work_order_id,
            "invoice_id": invoice["id"],
        },
    )
    invoice["payable_journal_id"] = invoice["payable_journal_id"]
    return invoice


def approve_work_invoice(session, organization_id, invoice_id, posting_date):
    return approve_invoice(session, organization_id, invoice_id, posting_date)


def reopen_ticket(session, organization_id, ticket_id) -> dict:
    ticket = _lock_ticket(session, organization_id, ticket_id)
    session.execute(
        text("UPDATE maintenance_tickets SET status = 'REOPENED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": ticket_id},
    )
    return {"id": str(ticket_id), "status": "REOPENED", "previous_status": ticket["status"]}


def store_entry_code(session, organization_id, ticket_id, code: str, key: bytes) -> dict:
    ciphertext, nonce, version = encrypt_text(code, key)
    session.execute(
        text(
            """
            INSERT INTO entry_secrets (id, organization_id, ticket_id, ciphertext, nonce, key_version)
            VALUES (:id, :organization_id, :ticket_id, :ciphertext, :nonce, :key_version)
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "ticket_id": ticket_id,
            "ciphertext": ciphertext,
            "nonce": nonce,
            "key_version": version,
        },
    )
    return {"stored": True}


def store_accommodation(session, organization_id, ticket_id, note: str, key: bytes) -> dict:
    ciphertext, nonce, version = encrypt_text(note, key)
    session.execute(
        text(
            """
            INSERT INTO accommodation_notes (id, organization_id, ticket_id, ciphertext, nonce, key_version)
            VALUES (:id, :organization_id, :ticket_id, :ciphertext, :nonce, :key_version)
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "ticket_id": ticket_id,
            "ciphertext": ciphertext,
            "nonce": nonce,
            "key_version": version,
        },
    )
    return {"stored": True}


def create_appointment(session, organization_id, ticket_id, starts_at, ends_at, timezone_name: str) -> dict:
    ticket = _lock_ticket(session, organization_id, ticket_id)
    appointment_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO maintenance_appointments (
              id, organization_id, ticket_id, unit_id, starts_at, ends_at, timezone, status
            ) VALUES (
              :id, :organization_id, :ticket_id, :unit_id, :starts_at, :ends_at, :timezone, 'REQUESTED'
            )
            """
        ),
        {
            "id": appointment_id,
            "organization_id": organization_id,
            "ticket_id": ticket_id,
            "unit_id": ticket["unit_id"],
            "starts_at": starts_at,
            "ends_at": ends_at,
            "timezone": timezone_name,
        },
    )
    return {"id": str(appointment_id), "status": "REQUESTED", "entry_permission": "NOT_YET_GRANTED"}


def confirm_appointment(session, organization_id, appointment_id, entry_permission: str, notice_evidence: str | None, contractor_accepted: bool) -> dict:
    appointment = session.execute(
        text(
            """
            SELECT ticket_id, status FROM maintenance_appointments
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "id": appointment_id},
    ).mappings().first()
    if appointment is None:
        problem(404, "NOT_FOUND", "Appointment not found.")
    accepted = session.execute(
        text(
            """
            SELECT id FROM assignments
            WHERE organization_id = :organization_id AND ticket_id = :ticket_id AND status = 'ACCEPTED'
            """
        ),
        {"organization_id": organization_id, "ticket_id": appointment["ticket_id"]},
    ).first()
    if entry_permission != "GRANTED" or not (notice_evidence or "").strip() or not contractor_accepted or accepted is None:
        problem(
            409,
            "ENTRY_PERMISSION_REQUIRED",
            "Availability is not permission to enter. Confirmation needs entry permission, notice evidence, and an accepted contractor assignment.",
        )
    session.execute(
        text(
            """
            UPDATE maintenance_appointments
            SET status = 'CONFIRMED', entry_permission = :entry_permission,
                notice_evidence = :notice_evidence, contractor_accepted = true
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {
            "entry_permission": entry_permission,
            "notice_evidence": notice_evidence,
            "organization_id": organization_id,
            "id": appointment_id,
        },
    )
    return {"id": str(appointment_id), "status": "CONFIRMED"}


def record_estimate(session, organization_id, work_order_id, estimate_cents: int) -> dict:
    session.execute(
        text(
            """
            UPDATE work_orders
            SET estimate_cents = :estimate_cents, authorization_state = 'WAITING_APPROVAL'
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"estimate_cents": estimate_cents, "organization_id": organization_id, "id": work_order_id},
    )
    session.execute(
        text(
            """
            UPDATE maintenance_tickets SET status = 'WAITING_APPROVAL'
            WHERE organization_id = :organization_id AND id = (
              SELECT ticket_id FROM work_orders WHERE organization_id = :organization_id AND id = :id
            )
            """
        ),
        {"organization_id": organization_id, "id": work_order_id},
    )
    return {"authorization_state": "WAITING_APPROVAL", "spending_limit": None}


def get_ticket(session, organization_id, ticket_id, secret: str, viewer: str, persist_questions: bool = False) -> dict:
    ticket = _lock_ticket(session, organization_id, ticket_id)
    fields = session.execute(
        text(
            """
            SELECT field_key, status, value_text, reason
            FROM intake_fields WHERE organization_id = :organization_id AND ticket_id = :ticket_id
            ORDER BY field_key
            """
        ),
        {"organization_id": organization_id, "ticket_id": ticket_id},
    ).mappings().all()
    missing = [field for field in FIELD_ORDER if _field_status(fields, field) in {"UNKNOWN", None}]
    book = PLAYBOOKS.get(ticket["category"], PLAYBOOKS["general"])
    asked_keys = [] if ticket["handoff"] or ticket["emergency"] else [field for field in missing if field in book][:2]
    questions = [book[field] for field in asked_keys]
    if persist_questions and not ticket["emergency"] and not ticket["handoff"]:
        session.execute(
            text("UPDATE maintenance_tickets SET asked_fields = CAST(:asked AS jsonb) WHERE id = :id"),
            {"asked": json.dumps(asked_keys), "id": ticket_id},
        )
    safety = None
    if ticket["emergency"]:
        safety = SAFETY_MESSAGE
        if ticket["safety_context"] == "gas" or _gas(ticket["description"] or ""):
            safety = f"{SAFETY_MESSAGE} {GAS_GUIDANCE}"
    if ticket["emergency"]:
        priority = "EMERGENCY"
    elif ticket["urgent_triage"]:
        priority = "URGENT_TRIAGE"
    else:
        priority = "ROUTINE_REVIEW_PENDING"
    intake = [
        {
            "field_key": field["field_key"],
            "status": field["status"],
            "reason": field["reason"],
            "value_text": None if viewer == "public" else field["value_text"],
        }
        for field in fields
    ]
    payload = {
        "id": str(ticket["id"]),
        "ticket_number": ticket["ticket_number"],
        "status": ticket["status"],
        "priority": priority,
        "verification": ticket["verification"],
        "emergency": ticket["emergency"],
        "urgent_triage": ticket["urgent_triage"],
        "handoff": ticket["handoff"],
        "category": ticket["category"],
        "missing_fields": missing,
        "intake": intake,
        "next_questions": questions,
        "safety_message": safety,
        "model_adapter": "disabled",
        "questions_source": "template",
        "video_understanding": False,
        "intake_token": mint_ticket_token(secret, organization_id, ticket_id),
    }
    if viewer == "contractor":
        payload.pop("intake_token", None)
    if viewer == "public":
        return {
            "id": payload["id"],
            "ticket_number": payload["ticket_number"],
            "status": payload["status"],
            "priority": payload["priority"],
            "verification": payload["verification"],
            "emergency": payload["emergency"],
            "missing_fields": missing,
            "next_questions": questions,
            "safety_message": safety,
            "model_adapter": "disabled",
            "questions_source": "template",
            "video_understanding": False,
            "intake_token": payload["intake_token"],
        }
    payload.update(ticket_details(session, organization_id, ticket_id))
    return payload


def can_view_ticket(session, organization_id, ticket_id, user_id, roles: tuple[str, ...]) -> str | None:
    row = session.execute(
        text(
            """
            SELECT reporter_user_id FROM maintenance_tickets
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "id": ticket_id},
    ).mappings().first()
    if row is None:
        return None
    caps = _caps(roles)
    if "maintenance.manage" in caps or "maintenance.acknowledge" in caps:
        return "manager"
    if "maintenance.respond" in caps and _user_assigned(session, organization_id, ticket_id, user_id):
        return "contractor"
    if "maintenance.report" in caps and row["reporter_user_id"] == user_id:
        return "tenant"
    return None


def viewer_can_read_media(session, organization_id, ticket_id, user_id, roles: tuple[str, ...]) -> bool:
    return can_view_ticket(session, organization_id, ticket_id, user_id, roles) is not None


def _user_assigned(session, organization_id, ticket_id, user_id) -> bool:
    row = session.execute(
        text(
            """
            SELECT a.id
            FROM assignments AS a
            JOIN contractor_profiles AS c
              ON c.id = a.contractor_profile_id AND c.organization_id = a.organization_id
            WHERE a.organization_id = :organization_id AND a.ticket_id = :ticket_id AND c.user_id = :user_id
            """
        ),
        {"organization_id": organization_id, "ticket_id": ticket_id, "user_id": user_id},
    ).first()
    return row is not None


TICKET_STATUSES = {
    "INTAKE_OPEN",
    "TRIAGE_PENDING",
    "MANAGER_REVIEW",
    "ASSIGNMENT_PENDING",
    "ASSIGNED",
    "SCHEDULING",
    "SCHEDULED",
    "IN_PROGRESS",
    "COMPLETION_REVIEW",
    "COMPLETED",
    "CLOSED",
    "WAITING_TENANT",
    "WAITING_PARTS",
    "WAITING_APPROVAL",
    "CANCELED",
    "REOPENED",
}


def create_contractor_profile(session, organization_id, party_id, user_id, approved: bool, trades: str) -> dict:
    profile_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO contractor_profiles (
              id, organization_id, party_id, user_id, approved, trades
            ) VALUES (
              :id, :organization_id, :party_id, :user_id, :approved, :trades
            )
            """
        ),
        {
            "id": profile_id,
            "organization_id": organization_id,
            "party_id": party_id,
            "user_id": user_id,
            "approved": approved,
            "trades": trades,
        },
    )
    return {"id": str(profile_id), "approved": approved, "trades": trades}


def set_category(session, organization_id, ticket_id, category: str) -> dict:
    if category not in PLAYBOOKS:
        problem(422, "VALIDATION_ERROR", "Unknown maintenance category.")
    _lock_ticket(session, organization_id, ticket_id)
    session.execute(
        text("UPDATE maintenance_tickets SET category = :category WHERE organization_id = :organization_id AND id = :id"),
        {"category": category, "organization_id": organization_id, "id": ticket_id},
    )
    return {"id": str(ticket_id), "category": category}


def transition_ticket(session, organization_id, ticket_id, action: str, reason: str | None, duplicate_of, status: str | None, actor_id) -> dict:
    ticket = _lock_ticket(session, organization_id, ticket_id)
    if action == "cancel":
        if not (reason or "").strip():
            problem(422, "VALIDATION_ERROR", "Cancellation requires a reason.")
        new_status = "CANCELED"
    elif action == "reopen":
        new_status = "REOPENED"
    elif action == "link_duplicate":
        if duplicate_of is None:
            problem(422, "VALIDATION_ERROR", "A duplicate link needs the other ticket.")
        session.execute(
            text("UPDATE maintenance_tickets SET duplicate_of_id = :duplicate_of WHERE organization_id = :organization_id AND id = :id"),
            {"duplicate_of": duplicate_of, "organization_id": organization_id, "id": ticket_id},
        )
        write_audit(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            action="maintenance.duplicate_linked",
            target_type="maintenance_ticket",
            target_id=ticket_id,
            target_version=None,
            request_id="maintenance",
            before_state={"status": ticket["status"]},
            after_state={"duplicate_of_id": str(duplicate_of), "deleted": False},
        )
        return {"id": str(ticket_id), "status": ticket["status"], "duplicate_of_id": str(duplicate_of), "deleted": False}
    elif action == "set_status":
        if status == "CANCELED":
            problem(422, "VALIDATION_ERROR", "Cancellation requires a reason.")
        if status not in TICKET_STATUSES:
            problem(422, "VALIDATION_ERROR", "Unknown ticket status.")
        new_status = status
    else:
        problem(422, "VALIDATION_ERROR", "Unknown ticket transition.")
    session.execute(
        text("UPDATE maintenance_tickets SET status = :status WHERE organization_id = :organization_id AND id = :id"),
        {"status": new_status, "organization_id": organization_id, "id": ticket_id},
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="maintenance.transition",
        target_type="maintenance_ticket",
        target_id=ticket_id,
        target_version=None,
        request_id="maintenance",
        before_state={"status": ticket["status"]},
        after_state={"status": new_status, "reason": reason},
    )
    session.execute(text("INSERT INTO maintenance_status_updates (id, organization_id, ticket_id, status, reason) VALUES (:id,:org,:ticket,:status,:reason)"),
                    {"id": uuid4(), "org": organization_id, "ticket": ticket_id, "status": new_status, "reason": reason})
    return {"id": str(ticket_id), "status": new_status}


def mint_ticket_token(secret: str, organization_id: UUID, ticket_id: UUID) -> str:
    import time

    return _sign(
        {
            "amr": "intake_link",
            "env": "ticket",
            "exp": int(time.time()) + 86400,
            "org": str(organization_id),
            "sub": str(ticket_id),
            "v": 1,
        },
        secret,
    )


def read_intake_token(secret: str, token: str) -> dict:
    payload = verify_token(token, secret)
    if payload.get("amr") not in {"intake_link", "intake_org"}:
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    return payload


def mint_org_token(secret: str, organization_id: UUID) -> str:
    import time

    return _sign(
        {
            "amr": "intake_org",
            "env": "ticket",
            "exp": int(time.time()) + 86400,
            "org": str(organization_id),
            "sub": str(organization_id),
            "v": 1,
        },
        secret,
    )


def _create_ticket(session, organization_id, secret, description, verification, unit_id, lease_id, reporter_user_id, identity_status, when, intake, category, public=False):
    safety_text = " ".join(str(part or "") for part in (description, (intake or {}).get("location"), (intake or {}).get("safety_concerns")))
    life_safety, urgent = _classify(safety_text)
    chosen = category if category in PLAYBOOKS else _category(description)
    status = "TRIAGE_PENDING" if verification == "UNVERIFIED" and not life_safety else "INTAKE_OPEN"
    number = session.execute(
        text(
            """
            INSERT INTO ticket_counters (organization_id, last_number)
            VALUES (:organization_id, 1)
            ON CONFLICT (organization_id) DO UPDATE
            SET last_number = ticket_counters.last_number + 1
            RETURNING last_number
            """
        ),
        {"organization_id": organization_id},
    ).scalar()
    ticket_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO maintenance_tickets (
              id, organization_id, ticket_number, unit_id, lease_id, reporter_user_id,
              verification, status, category, emergency, urgent_triage, description, safety_context
            ) VALUES (
              :id, :organization_id, :ticket_number, :unit_id, :lease_id, :reporter_user_id,
              :verification, :status, :category, :emergency, :urgent_triage, :description, :safety_context
            )
            """
        ),
        {
            "id": ticket_id,
            "organization_id": organization_id,
            "ticket_number": number,
            "unit_id": unit_id,
            "lease_id": lease_id,
            "reporter_user_id": reporter_user_id,
            "verification": verification,
            "status": status,
            "category": chosen,
            "emergency": life_safety,
            "urgent_triage": urgent and not life_safety,
            "description": description,
            "safety_context": "gas" if life_safety and _gas(safety_text) else "",
        },
    )
    session.execute(
        text("SELECT set_config('app.intake_ticket_id', :ticket_id, true)"),
        {"ticket_id": str(ticket_id)},
    )
    for field_key in FIELD_ORDER:
        field_status = "UNKNOWN"
        value = None
        if field_key == "description" and description:
            field_status = "PROVIDED"
            value = description
        if field_key == "identity_property":
            field_status = identity_status
        _set_field(session, organization_id, ticket_id, field_key, field_status, value, None)
    _apply_reported_fields(session, organization_id, ticket_id, intake or {})
    if life_safety or urgent:
        _open_escalation(session, organization_id, ticket_id, reporter_user_id, when, life_safety=life_safety)
    viewer = "public" if public else "manager"
    return get_ticket(session, organization_id, ticket_id, secret, viewer, persist_questions=True)


def _apply_reported_fields(session, organization_id, ticket_id, intake: dict) -> None:
    if intake.get("location"):
        _set_field(session, organization_id, ticket_id, "exact_location", "PROVIDED", intake["location"], None)
    if intake.get("onset") or intake.get("frequency"):
        combined = " ".join(part for part in (intake.get("onset"), intake.get("frequency")) if part)
        _set_field(session, organization_id, ticket_id, "onset_frequency", "PROVIDED", combined, None)
    if intake.get("media_status") in {"PROVIDED", "UNKNOWN", "DECLINED", "NOT_PRACTICAL"}:
        _set_field(session, organization_id, ticket_id, "media", intake["media_status"], None, intake.get("media_reason"))
    windows = intake.get("preferred_access_windows")
    if isinstance(windows, list) and windows:
        _set_field(session, organization_id, ticket_id, "access_windows", "PROVIDED", json.dumps(windows), None)
    if intake.get("safety_concerns"):
        _set_field(session, organization_id, ticket_id, "entry_safety", "PROVIDED", intake["safety_concerns"], None)
    if intake.get("contact") or intake.get("contact_id"):
        _set_field(session, organization_id, ticket_id, "contact", "PROVIDED", str(intake.get("contact") or intake.get("contact_id")), None)


def _mark_emergency(session, organization_id, ticket_id, actor_id, when, life_safety=True, safety_context=""):
    session.execute(
        text(
            """
            UPDATE maintenance_tickets
            SET emergency = true,
                safety_context = CASE WHEN :safety_context = '' THEN safety_context ELSE :safety_context END
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"safety_context": safety_context, "organization_id": organization_id, "id": ticket_id},
    )
    if life_safety:
        _open_escalation(session, organization_id, ticket_id, actor_id, when, life_safety=True)


def _open_escalation(session, organization_id, ticket_id, actor_id, when, life_safety: bool):
    existing = session.execute(
        text(
            """
            SELECT id FROM escalations
            WHERE organization_id = :organization_id AND ticket_id = :ticket_id AND state = 'OPEN'
            """
        ),
        {"organization_id": organization_id, "ticket_id": ticket_id},
    ).scalar()
    if existing:
        return existing
    escalation_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO escalations (id, organization_id, ticket_id, state, created_at)
            VALUES (:id, :organization_id, :ticket_id, 'OPEN', :created_at)
            """
        ),
        {"id": escalation_id, "organization_id": organization_id, "ticket_id": ticket_id, "created_at": when},
    )
    _notification(session, organization_id, ticket_id, escalation_id, "primary", when)
    write_outbox(
        session,
        organization_id=organization_id,
        event_type="MaintenanceEmergencyDetected" if life_safety else "MaintenanceEscalated",
        dedup_key=f"emergency:{escalation_id}",
        property_id=None,
        payload={"ticket_id": str(ticket_id), "escalation_id": str(escalation_id), "delivered_at": None},
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="maintenance.escalated",
        target_type="maintenance_ticket",
        target_id=ticket_id,
        target_version=None,
        request_id="maintenance",
        before_state=None,
        after_state={"escalation_id": str(escalation_id)},
    )
    return escalation_id


def _notification(session, organization_id, ticket_id, escalation_id, kind, when):
    destination = session.execute(
        text(
            """
            SELECT label, fail_next FROM escalation_destinations
            WHERE organization_id = :organization_id AND role = :role
            ORDER BY created_at LIMIT 1
            """
        ),
        {"organization_id": organization_id, "role": "primary" if kind == "primary" else "alternate"},
    ).mappings().first()
    status = "RECORDED" if destination else "DESTINATION_UNCONFIGURED"
    payload = redact(
        {
            "kind": kind,
            "destination": None if destination is None else destination["label"],
            "primary_failed": bool(destination and destination["fail_next"] and kind == "primary"),
            "delivered_at": None,
        }
    )
    session.execute(
        text(
            """
            INSERT INTO notification_jobs (
              id, organization_id, ticket_id, escalation_id, kind, status,
              destination_label, scheduled_for, payload
            ) VALUES (
              :id, :organization_id, :ticket_id, :escalation_id, :kind, :status,
              :destination_label, :scheduled_for, CAST(:payload AS jsonb)
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "ticket_id": ticket_id,
            "escalation_id": escalation_id,
            "kind": kind,
            "status": status,
            "destination_label": None if destination is None else destination["label"],
            "scheduled_for": when,
            "payload": json.dumps(payload),
        },
    )


def _set_field(session, organization_id, ticket_id, field_key, status, value, reason):
    session.execute(
        text(
            """
            INSERT INTO intake_fields (
              id, organization_id, ticket_id, field_key, status, value_text, reason
            ) VALUES (
              :id, :organization_id, :ticket_id, :field_key, :status, :value_text, :reason
            )
            ON CONFLICT (organization_id, ticket_id, field_key) DO UPDATE
            SET status = EXCLUDED.status, value_text = EXCLUDED.value_text, reason = EXCLUDED.reason
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "ticket_id": ticket_id,
            "field_key": field_key,
            "status": status,
            "value_text": value,
            "reason": reason,
        },
    )


def _questions(category: str, missing: list[str]) -> list[str]:
    book = PLAYBOOKS.get(category, PLAYBOOKS["general"])
    return [book[field] for field in missing if field in book]


def _category(description: str) -> str:
    text_value = description.lower()
    if any(word in text_value for word in ("sink", "leak", "drip", "pipe")):
        return "leak"
    if any(word in text_value for word in ("heat", "hvac", "air condition", "thermostat", "cooling")):
        return "hvac"
    if "outlet" in text_value or "electrical" in text_value or "breaker" in text_value:
        return "electrical"
    for category, terms in (
        ("appliance", ("dishwasher", "refrigerator", "fridge", "washer", "dryer", "oven", "stove", "freezer")),
        ("structural", ("ceiling", "wall", "roof", "foundation")),
        ("pest_mold", ("mold", "mould", "pest", "cockroach", "mice", "rats")),
        ("lock", ("lock", "door", "key")),
    ):
        if any(term in text_value for term in terms):
            return category
    return "general"


def _classify(description: str) -> tuple[bool, bool]:
    text_value = description.lower()
    life = any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text_value) for term in LIFE_SAFETY_TERMS)
    urgent = any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text_value) for term in URGENT_TERMS)
    return life, urgent


def _gas(description: str) -> bool:
    text_value = description.lower()
    return any(term in text_value for term in ("smell gas", "gas leak", "smell of gas", "rotten egg", "gas smell"))


def _handoff_requested(body: str) -> bool:
    text_value = body.lower()
    return any(phrase in text_value for phrase in ("hand off", "handoff", "that's all", "that is all", "stop asking"))


def _field_status(fields, key: str):
    for field in fields:
        if field["field_key"] == key:
            return field["status"]
    return None


def _lock_ticket(session, organization_id, ticket_id):
    row = session.execute(
        text("SELECT * FROM maintenance_tickets WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": ticket_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Ticket not found.")
    return row


def _lease_for_user(session, organization_id, user_id, unit_id, lease_id):
    row = session.execute(
        text(
            """
            SELECT l.id, l.unit_id
            FROM lease_parties AS lp
            JOIN leases AS l ON l.id = lp.lease_id AND l.organization_id = lp.organization_id
            WHERE lp.organization_id = :organization_id AND lp.user_id = :user_id
              AND (CAST(:lease_id AS uuid) IS NULL OR l.id = CAST(:lease_id AS uuid))
              AND (CAST(:unit_id AS uuid) IS NULL OR l.unit_id = CAST(:unit_id AS uuid))
            LIMIT 1
            """
        ),
        {"organization_id": organization_id, "user_id": user_id, "lease_id": lease_id, "unit_id": unit_id},
    ).mappings().first()
    return row


def _assignment_for_user(session, organization_id, assignment_id, user_id):
    row = session.execute(
        text(
            """
            SELECT a.id
            FROM assignments AS a
            JOIN contractor_profiles AS c
              ON c.id = a.contractor_profile_id AND c.organization_id = a.organization_id
            WHERE a.organization_id = :organization_id AND a.id = :assignment_id AND c.user_id = :user_id
            """
        ),
        {"organization_id": organization_id, "assignment_id": assignment_id, "user_id": user_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Assignment not found.")
    return row


def _caps(roles: tuple[str, ...]) -> set[str]:
    from grok_bot.auth.permissions import ROLE_CAPABILITIES

    granted = set()
    for role in roles:
        granted.update(ROLE_CAPABILITIES.get(role, ()))
    return granted


def save_quarantine(session, settings, organization_id, media_id, payload: bytes) -> dict:
    row = session.execute(
        text("SELECT storage_key, status FROM media_objects WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": media_id},
    ).mappings().first()
    if row is None or row["status"] != "QUARANTINED":
        problem(404, "NOT_FOUND", "Media not found.")
    path = safe_media_file(Path(settings.media_root), row["storage_key"], allow_missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    session.execute(
        text("UPDATE media_objects SET status = 'QUARANTINED', scan_code = NULL, rejection_reason = NULL WHERE id = :id"),
        {"id": media_id},
    )
    return {"id": str(media_id), "status": "QUARANTINED"}


def link_lease_party(session, organization_id, lease_id, user_id) -> dict:
    link_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO lease_parties (id, organization_id, lease_id, user_id)
            VALUES (:id, :organization_id, :lease_id, :user_id)
            """
        ),
        {"id": link_id, "organization_id": organization_id, "lease_id": lease_id, "user_id": user_id},
    )
    return {"id": str(link_id), "lease_id": str(lease_id), "user_id": str(user_id)}


def add_destination(session, organization_id, role: str, label: str, fail_next: bool) -> dict:
    if role not in {"primary", "alternate"}:
        problem(422, "VALIDATION_ERROR", "Destination role must be primary or alternate.")
    destination_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO escalation_destinations (id, organization_id, role, label, fail_next)
            VALUES (:id, :organization_id, :role, :label, :fail_next)
            """
        ),
        {
            "id": destination_id,
            "organization_id": organization_id,
            "role": role,
            "label": label,
            "fail_next": fail_next,
        },
    )
    return {"id": str(destination_id), "role": role, "label": label, "fail_next": fail_next, "delivered_at": None}


def request_escalation(session, organization_id, ticket_id, actor_id, when) -> dict:
    _lock_ticket(session, organization_id, ticket_id)
    escalation_id = _open_escalation(session, organization_id, ticket_id, actor_id, when, life_safety=False)
    return {"ticket_id": str(ticket_id), "escalation_id": str(escalation_id), "delivered_at": None}


def bind_tenant(session: Session, organization_id: UUID) -> None:
    set_tenant(session, organization_id, None)
