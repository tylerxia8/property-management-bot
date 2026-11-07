from datetime import datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from grok_bot.domain.records import write_audit, write_outbox
from grok_bot.errors import problem

REMINDER_OFFSETS = (24 * 60, 2 * 60)


def publish_schedule(session, organization_id, property_id, body: dict) -> dict:
    if body.get("fixture") and not str(body.get("label", "")).startswith("fixture:"):
        problem(422, "VALIDATION_ERROR", "A fixture schedule must use a fixture: label.")
    if isinstance(body.get("open_weekdays"), list):
        body["open_weekdays"] = "{" + ",".join(str(int(day)) for day in body["open_weekdays"]) + "}"
    schedule_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO schedule_configs (
              id, organization_id, property_id, duration_minutes, buffer_minutes, hold_minutes,
              min_notice_minutes, day_start, day_end, open_weekdays, timezone, fixture, label
            ) VALUES (
              :id, :organization_id, :property_id, :duration_minutes, :buffer_minutes, :hold_minutes,
              :min_notice_minutes, :day_start, :day_end, CAST(:open_weekdays AS integer[]), :timezone, :fixture, :label
            )
            """
        ),
        {"id": schedule_id, "organization_id": organization_id, "property_id": property_id, **body},
    )
    return {"id": str(schedule_id), "fixture": bool(body.get("fixture"))}


def add_resource(session, organization_id, property_id, display_name: str) -> dict:
    resource_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO scheduling_resources (id, organization_id, property_id, kind, display_name)
            VALUES (:id, :organization_id, :property_id, 'AGENT', :display_name)
            """
        ),
        {"id": resource_id, "organization_id": organization_id, "property_id": property_id, "display_name": display_name},
    )
    return {"id": str(resource_id), "kind": "AGENT"}


def list_slots(session, organization_id, property_id, clock) -> dict:
    schedule = _schedule(session, organization_id, property_id)
    resource = _resource(session, organization_id, property_id)
    tz = ZoneInfo(schedule["timezone"])
    now = clock.now().astimezone(tz)
    slots = []
    day = now.date()
    for offset in range(14):
        current = day + timedelta(days=offset)
        if current.isoweekday() not in schedule["open_weekdays"]:
            continue
        start = datetime.combine(current, schedule["day_start"], tz)
        end = datetime.combine(current, schedule["day_end"], tz)
        cursor = start
        while cursor + timedelta(minutes=schedule["duration_minutes"]) <= end:
            if cursor >= now + timedelta(minutes=schedule["min_notice_minutes"]):
                slots.append(
                    {
                        "resource_id": str(resource["id"]),
                        "starts_at": cursor.isoformat(),
                        "ends_at": (cursor + timedelta(minutes=schedule["duration_minutes"])).isoformat(),
                        "timezone": schedule["timezone"],
                    }
                )
            cursor += timedelta(minutes=schedule["duration_minutes"] + schedule["buffer_minutes"])
            if len(slots) >= 8:
                return {"items": slots, "timezone": schedule["timezone"], "configuration": "fixture" if schedule["fixture"] else "published"}
    if not slots:
        problem(409, "CONFIGURATION_REQUIRED", "No tour slots are available in the published schedule.")
    return {"items": slots, "timezone": schedule["timezone"], "configuration": "fixture" if schedule["fixture"] else "published"}


def create_hold(session, organization_id, body: dict, clock) -> dict:
    prospect = _prospect_row(session, organization_id, body["prospect_id"])
    allowed_state = prospect["state"] in {
        "PRELIMINARILY_QUALIFIED",
        "TOUR_REQUESTED",
        "TOUR_CONFIRMED",
        "TOUR_CANCELED",
    }
    if not allowed_state and not prospect["booking_exception"]:
        problem(409, "HUMAN_REVIEW_REQUIRED", "This prospect needs a person before a tour can be held.")
    schedule = _schedule(session, organization_id, body["property_id"])
    starts, ends = resolve_window(body["local_start"], body.get("local_end"), body["timezone"], body.get("dst_resolution"), schedule["duration_minutes"])
    _expire_holds(session, organization_id, body["resource_id"], clock.now())
    buffer = timedelta(minutes=schedule["buffer_minutes"])
    appointment_id = uuid4()
    try:
        session.execute(
            text(
                """
                INSERT INTO tour_appointments (
                  id, organization_id, prospect_id, property_id, unit_id, resource_id,
                  starts_at, ends_at, blocked_starts_at, blocked_ends_at, timezone, status, expires_at
                ) VALUES (
                  :id, :organization_id, :prospect_id, :property_id, :unit_id, :resource_id,
                  :starts_at, :ends_at, :blocked_starts_at, :blocked_ends_at, :timezone, 'HELD', :expires_at
                )
                """
            ),
            {
                "id": appointment_id,
                "organization_id": organization_id,
                "prospect_id": body["prospect_id"],
                "property_id": body["property_id"],
                "unit_id": body.get("unit_id") or prospect["unit_id"],
                "resource_id": body["resource_id"],
                "starts_at": starts,
                "ends_at": ends,
                "blocked_starts_at": starts - buffer,
                "blocked_ends_at": ends + buffer,
                "timezone": body["timezone"],
                "expires_at": clock.now() + timedelta(minutes=schedule["hold_minutes"]),
            },
        )
    except IntegrityError as exc:
        if "tour_appointments_no_overlap" in str(exc):
            problem(409, "SLOT_UNAVAILABLE", "That resource already has an active hold or tour in this window.")
        raise
    session.execute(
        text("UPDATE prospects SET state = 'TOUR_REQUESTED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": prospect["id"]},
    )
    return _appointment(session, organization_id, appointment_id)


def confirm_tour(session, organization_id, appointment_id, actor_id, manager_local: bool) -> dict:
    row = _lock_tour(session, organization_id, appointment_id)
    if row["status"] in {"CONFIRMATION_PENDING", "MANAGER_CONFIRMED"}:
        return _appointment(session, organization_id, appointment_id)
    if _unit_occupied(session, organization_id, row["unit_id"], row["starts_at"]) and not (row["access_evidence"] or "").strip():
        problem(409, "ACCESS_NOT_RECORDED", "An occupied unit cannot be confirmed without recorded access evidence.")
    status = "MANAGER_CONFIRMED" if manager_local else "CONFIRMATION_PENDING"
    event_key = row["external_event_key"] or f"local-{appointment_id}"
    session.execute(
        text(
            """
            UPDATE tour_appointments
            SET status = :status, external_event_key = :event_key, external_event_created = false, expires_at = NULL
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"status": status, "event_key": event_key, "organization_id": organization_id, "id": appointment_id},
    )
    write_outbox(
        session,
        organization_id=organization_id,
        event_type="CalendarSyncRequested",
        dedup_key=f"calendar:{appointment_id}:{row['version']}",
        property_id=row["property_id"],
        payload={"appointment_id": str(appointment_id), "external_event_key": event_key, "external_event_created": False},
    )
    _reminders(session, organization_id, appointment_id, row["version"], row["prospect_id"])
    if status == "MANAGER_CONFIRMED":
        session.execute(
            text("UPDATE prospects SET state = 'TOUR_CONFIRMED' WHERE organization_id = :organization_id AND id = :id"),
            {"organization_id": organization_id, "id": row["prospect_id"]},
        )
    del actor_id
    return _appointment(session, organization_id, appointment_id)


def reschedule(session, organization_id, appointment_id, body: dict, clock) -> dict:
    row = _lock_tour(session, organization_id, appointment_id)
    _suppress(session, organization_id, appointment_id)
    session.execute(
        text("UPDATE tour_appointments SET status = 'CANCELED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": appointment_id},
    )
    created = create_hold(session, organization_id, {**body, "prospect_id": row["prospect_id"], "property_id": row["property_id"], "resource_id": row["resource_id"], "unit_id": row["unit_id"]}, clock)
    return {"previous_id": str(appointment_id), "appointment": created, "previous_reminders": "SUPPRESSED"}


def cancel_tour(session, organization_id, appointment_id) -> dict:
    _lock_tour(session, organization_id, appointment_id)
    _suppress(session, organization_id, appointment_id)
    session.execute(
        text("UPDATE tour_appointments SET status = 'CANCELED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": appointment_id},
    )
    return {"id": str(appointment_id), "status": "CANCELED", "reminders": "SUPPRESSED"}


def complete_tour(session, organization_id, appointment_id, actor_id) -> dict:
    row = _lock_tour(session, organization_id, appointment_id)
    session.execute(
        text("UPDATE tour_appointments SET status = 'COMPLETED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": appointment_id},
    )
    session.execute(
        text("UPDATE prospects SET state = 'TOUR_COMPLETED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": row["prospect_id"]},
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="tour.completed",
        target_type="tour_appointment",
        target_id=appointment_id,
        target_version=row["version"],
        request_id="tour",
        before_state={"status": row["status"]},
        after_state={"status": "COMPLETED"},
    )
    return {"id": str(appointment_id), "status": "COMPLETED"}


def invite_application(session, organization_id, prospect_id, actor_id, external_reference: str | None) -> dict:
    tour = session.execute(
        text(
            """
            SELECT id FROM tour_appointments
            WHERE organization_id = :organization_id AND prospect_id = :prospect_id AND status = 'COMPLETED'
            ORDER BY created_at DESC LIMIT 1
            """
        ),
        {"organization_id": organization_id, "prospect_id": prospect_id},
    ).scalar()
    if tour is None:
        problem(409, "TOUR_NOT_COMPLETED", "An application invitation requires a completed tour.")
    invitation_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO application_invitations (
              id, organization_id, prospect_id, appointment_id, invited_by, external_reference, status, report_ordered
            ) VALUES (
              :id, :organization_id, :prospect_id, :appointment_id, :invited_by, :external_reference, 'INVITED', false
            )
            """
        ),
        {
            "id": invitation_id,
            "organization_id": organization_id,
            "prospect_id": prospect_id,
            "appointment_id": tour,
            "invited_by": actor_id,
            "external_reference": external_reference,
        },
    )
    session.execute(
        text("UPDATE prospects SET state = 'APPLICATION_INVITED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": prospect_id},
    )
    return {"id": str(invitation_id), "report_ordered": False, "formal_screening_permitted": False}


def record_access(session, organization_id, appointment_id, evidence: str) -> dict:
    if not evidence.strip():
        problem(422, "VALIDATION_ERROR", "Access evidence cannot be empty.")
    session.execute(
        text("UPDATE tour_appointments SET access_evidence = :evidence WHERE organization_id = :organization_id AND id = :id"),
        {"evidence": evidence, "organization_id": organization_id, "id": appointment_id},
    )
    return {"id": str(appointment_id), "access_recorded": True}


def resolve_window(local_start: str, local_end: str | None, timezone_name: str, dst_resolution: str | None, duration_minutes: int):
    tz = ZoneInfo(timezone_name)
    naive = datetime.fromisoformat(local_start)
    if naive.tzinfo is not None:
        naive = naive.replace(tzinfo=None)
    kind, starts = classify_local(naive, tz, dst_resolution)
    if kind == "nonexistent":
        problem(409, "NONEXISTENT_LOCAL_TIME", "That local time does not exist. Choose a different time.")
    if kind == "ambiguous":
        problem(409, "AMBIGUOUS_LOCAL_TIME", "That local time happens twice. Choose earlier or later.")
    if local_end:
        end_naive = datetime.fromisoformat(local_end)
        if end_naive.tzinfo is not None:
            end_naive = end_naive.replace(tzinfo=None)
        end_kind, ends = classify_local(end_naive, tz, dst_resolution)
        if end_kind != "unique":
            problem(409, "AMBIGUOUS_LOCAL_TIME" if end_kind == "ambiguous" else "NONEXISTENT_LOCAL_TIME", "The end time needs a real local instant.")
    else:
        ends = starts + timedelta(minutes=duration_minutes)
    return starts, ends


def classify_local(naive: datetime, tz: ZoneInfo, dst_resolution: str | None):
    utc = ZoneInfo("UTC")
    first = naive.replace(tzinfo=tz, fold=0)
    back = first.astimezone(utc).astimezone(tz)
    if back.replace(tzinfo=None) != naive:
        return "nonexistent", None
    second = naive.replace(tzinfo=tz, fold=1)
    if first.utcoffset() != second.utcoffset():
        if dst_resolution == "earlier":
            return "unique", first if first.utcoffset() > second.utcoffset() else second
        if dst_resolution == "later":
            return "unique", first if first.utcoffset() < second.utcoffset() else second
        return "ambiguous", None
    return "unique", first


def _reminders(session, organization_id, appointment_id, version, prospect_id) -> None:
    consents = {
        row["channel"]: row["allowed"]
        for row in session.execute(
            text("SELECT channel, allowed FROM prospect_consents WHERE organization_id = :organization_id AND prospect_id = :prospect_id"),
            {"organization_id": organization_id, "prospect_id": prospect_id},
        ).mappings()
    }
    for offset in REMINDER_OFFSETS:
        for channel in ("email", "sms"):
            allowed = consents.get(channel, False)
            session.execute(
                text(
                    """
                    INSERT INTO reminder_jobs (
                      id, organization_id, appointment_id, appointment_version, offset_minutes, channel, status
                    ) VALUES (
                      :id, :organization_id, :appointment_id, :appointment_version, :offset_minutes, :channel, :status
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "appointment_id": appointment_id,
                    "appointment_version": version,
                    "offset_minutes": offset,
                    "channel": channel,
                    "status": "SCHEDULED" if allowed else "OPTED_OUT",
                },
            )


def _suppress(session, organization_id, appointment_id) -> None:
    session.execute(
        text(
            """
            UPDATE reminder_jobs
            SET status = 'SUPPRESSED'
            WHERE organization_id = :organization_id AND appointment_id = :appointment_id AND status = 'SCHEDULED'
            """
        ),
        {"organization_id": organization_id, "appointment_id": appointment_id},
    )


def _expire_holds(session, organization_id, resource_id, now: datetime) -> None:
    session.execute(
        text(
            """
            UPDATE tour_appointments
            SET status = 'EXPIRED'
            WHERE organization_id = :organization_id AND resource_id = :resource_id
              AND status = 'HELD' AND expires_at <= :now
            """
        ),
        {"organization_id": organization_id, "resource_id": resource_id, "now": now},
    )


def _unit_occupied(session, organization_id, unit_id, starts_at) -> bool:
    if unit_id is None:
        return False
    return session.execute(
        text(
            """
            SELECT id FROM leases
            WHERE organization_id = :organization_id AND unit_id = :unit_id
              AND start_date <= CAST(:starts_at AS date) AND end_date > CAST(:starts_at AS date)
            LIMIT 1
            """
        ),
        {"organization_id": organization_id, "unit_id": unit_id, "starts_at": starts_at},
    ).scalar() is not None


def _exception(session, organization_id, prospect_id) -> bool:
    return session.execute(
        text(
            """
            SELECT id FROM human_reviews
            WHERE organization_id = :organization_id AND prospect_id = :prospect_id AND exception_granted = true
            LIMIT 1
            """
        ),
        {"organization_id": organization_id, "prospect_id": prospect_id},
    ).scalar() is not None


def _schedule(session, organization_id, property_id):
    row = session.execute(
        text("SELECT * FROM schedule_configs WHERE organization_id = :organization_id AND property_id = :property_id"),
        {"organization_id": organization_id, "property_id": property_id},
    ).mappings().first()
    if row is None:
        problem(409, "CONFIGURATION_REQUIRED", "This property has no published tour schedule.")
    return row


def _resource(session, organization_id, property_id):
    row = session.execute(
        text(
            """
            SELECT id FROM scheduling_resources
            WHERE organization_id = :organization_id AND property_id = :property_id
            ORDER BY created_at LIMIT 1
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).mappings().first()
    if row is None:
        problem(409, "CONFIGURATION_REQUIRED", "This property has no scheduling resource.")
    return row


def _prospect_row(session, organization_id, prospect_id):
    row = session.execute(
        text("SELECT * FROM prospects WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": prospect_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Prospect not found.")
    return row


def _lock_tour(session, organization_id, appointment_id):
    row = session.execute(
        text("SELECT * FROM tour_appointments WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": appointment_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Tour not found.")
    return row


def _appointment(session, organization_id, appointment_id) -> dict:
    row = _lock_tour(session, organization_id, appointment_id)
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "starts_at": row["starts_at"].isoformat(),
        "ends_at": row["ends_at"].isoformat(),
        "timezone": row["timezone"],
        "expires_at": None if row["expires_at"] is None else row["expires_at"].isoformat(),
        "external_event_key": row["external_event_key"],
        "external_event_created": row["external_event_created"],
        "version": row["version"],
    }
