import base64
from contextlib import ExitStack
import hashlib
import hmac
import json
import re
from time import monotonic
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4
from xml.etree.ElementTree import Element, SubElement, tostring

import httpx
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.db import set_tenant
from grok_bot.domain.maintenance import _classify, _open_escalation, add_message, request_upload, save_quarantine, store_and_scan
from grok_bot.domain.maintenance_phone import audit, inbound, lock_phone, notify_maintenance
from grok_bot.errors import problem


async def signed_form(request):
    settings = request.app.state.settings
    if not settings.twilio_configured:
        problem(503, "PHONE_UNAVAILABLE", "The phone integration is not configured.")
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
        problem(415, "VALIDATION_ERROR", "Expected a form callback.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            problem(413, "VALIDATION_ERROR", "Callback too large.")
    try:
        values = parse_qs(raw.decode("utf-8"), keep_blank_values=True, max_num_fields=100, strict_parsing=True)
    except (ValueError, UnicodeError):
        problem(400, "VALIDATION_ERROR", "Invalid callback form.")
    url = settings.twilio_public_url + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    payload = url + "".join(name + value for name in sorted(values) for value in sorted(set(values[name])))
    signature = base64.b64encode(hmac.new(settings.twilio_auth_token.get_secret_value().encode(), payload.encode(), hashlib.sha1).digest()).decode()
    supplied_signature = request.headers.get("x-twilio-signature", "")
    if not supplied_signature.isascii() or not hmac.compare_digest(signature, supplied_signature):
        problem(403, "FORBIDDEN", "Invalid callback signature.")
    if any(len(value) != 1 for value in values.values()):
        problem(400, "VALIDATION_ERROR", "Duplicate callback fields.")
    form = {name: value[0] for name, value in values.items()}
    if form.get("AccountSid") != settings.twilio_account_sid:
        problem(403, "FORBIDDEN", "Invalid callback account.")
    return form


def service_scope(session, settings):
    set_tenant(session, settings.twilio_organization_id, settings.twilio_service_user_id)
    if not session.execute(text("SELECT public.app_actor_is_manager()")).scalar_one():
        problem(503, "PHONE_UNAVAILABLE", "The phone service account needs an active manager grant.")


def sid(value, prefix):
    if not re.fullmatch(prefix + r"[0-9a-fA-F]{32}", value or ""):
        problem(400, "VALIDATION_ERROR", "Invalid callback identifier.")
    return value


def twiml(settings, kind):
    root = Element("Response")
    if kind == "voice":
        SubElement(root, "Say").text = "This maintenance line is not monitored for emergencies. If you are in immediate danger, call emergency services. After the beep, your message will be recorded and transcribed for the property manager. Please describe the problem and give your property address. Do not include entry codes."
        SubElement(root, "Record", {"maxLength": "119", "transcribe": "true", "transcribeCallback": settings.twilio_public_url + "/v1/maintenance-phone/twilio/transcription", "action": settings.twilio_public_url + "/v1/maintenance-phone/twilio/recording", "method": "POST", "playBeep": "true"})
        SubElement(root, "Hangup")
    elif kind == "recording":
        SubElement(root, "Say").text = "Thank you. Your message has been saved for review. No repair has been dispatched."
        SubElement(root, "Hangup")
    return tostring(root, encoding="unicode")


def callback(session, request, form, kind):
    settings = request.app.state.settings
    service_scope(session, settings)
    org = settings.twilio_organization_id
    actor = settings.twilio_service_user_id
    request_id = request.state.request_id
    lock_phone(session, org)
    if kind == "status":
        event_id = request.query_params.get("event")
        try:
            event_id = UUID(event_id)
        except (ValueError, TypeError):
            problem(400, "VALIDATION_ERROR", "Invalid delivery event.")
        message_sid = sid(form.get("MessageSid"), "(?:SM|MM)")
        status = form.get("MessageStatus")
        mapping = {"accepted": "ACCEPTED", "queued": "ACCEPTED", "sending": "SENDING", "sent": "SENT", "delivered": "DELIVERED", "undelivered": "UNDELIVERED", "failed": "FAILED"}
        if status not in mapping:
            return
        row = session.execute(text("SELECT * FROM maintenance_phone_events WHERE organization_id=:org AND id=:id AND direction='OUTBOUND' FOR UPDATE"), {"org": org, "id": event_id}).mappings().first()
        if row is None or form.get("To") != row["to_number"] or form.get("From") != settings.twilio_phone_number or row["provider_sid"] not in {None, message_sid}:
            problem(403, "FORBIDDEN", "Invalid delivery callback.")
        ranks = {"QUEUED": 0, "DELIVERY_UNKNOWN": 0, "ACCEPTED": 1, "SENDING": 2, "SENT": 3, "DELIVERED": 4, "UNDELIVERED": 4, "FAILED": 4}
        if ranks.get(row["status"], 0) < ranks[mapping[status]]:
            session.execute(text("UPDATE maintenance_phone_events SET status=:status,provider_sid=:sid WHERE organization_id=:org AND id=:id"), {"org": org, "id": event_id, "status": mapping[status], "sid": message_sid})
        session.execute(text("UPDATE maintenance_tickets t SET notification_status=e.status FROM maintenance_phone_events e WHERE t.organization_id=:org AND e.organization_id=t.organization_id AND t.notification_event_id=e.id AND e.id=:id"), {"org": org, "id": event_id})
        return
    if form.get("To") != settings.twilio_phone_number:
        problem(403, "FORBIDDEN", "Invalid callback destination.")
    sender = form.get("From", "")
    if not re.fullmatch(r"\+[1-9]\d{7,14}", sender):
        sender = "anonymous"
    if kind == "messages":
        message_sid = sid(form.get("MessageSid"), "(?:SM|MM)")
        body = form.get("Body", "").strip()
        if len(body) > 5000:
            problem(400, "VALIDATION_ERROR", "Message too long.")
        try:
            count = int(form.get("NumMedia", "0"))
        except ValueError:
            problem(400, "VALIDATION_ERROR", "Invalid attachment count.")
        if not 0 <= count <= 10:
            problem(400, "VALIDATION_ERROR", "Invalid attachment count.")
        result, created = inbound(session, settings, org, actor, "SMS", sender, body or "Photo message received; describe the problem to the property manager.", settings.twilio_account_sid + ":" + message_sid, "RECEIVED", request.app.state.clock.now(), request_id)
        if created and count:
            jobs = [{"url": form.get(f"MediaUrl{index}", ""), "type": form.get(f"MediaContentType{index}", ""), "status": "PENDING"} for index in range(count)]
            session.execute(text("UPDATE maintenance_phone_events SET media_jobs=CAST(:jobs AS jsonb),status='MEDIA_PENDING' WHERE organization_id=:org AND id=:id"), {"org": org, "id": result["id"], "jobs": json.dumps(jobs)})
        return
    call_sid = sid(form.get("CallSid"), "CA")
    result, _ = inbound(session, settings, org, actor, "VOICEMAIL", sender, "Phone call received. Awaiting voicemail transcription; caller identity and property are unverified.", settings.twilio_account_sid + ":" + call_sid, "AWAITING_RECORDING", request.app.state.clock.now(), request_id)
    if kind == "voice":
        return
    recording_sid = sid(form.get("RecordingSid"), "RE")
    row = session.execute(text("SELECT * FROM maintenance_phone_events WHERE organization_id=:org AND id=:id FOR UPDATE"), {"org": org, "id": result["id"]}).mappings().one()
    if row["recording_sid"] not in {None, recording_sid}:
        problem(409, "CALLBACK_CONFLICT", "Call already has another recording.")
    session.execute(text("UPDATE maintenance_phone_events SET recording_sid=:sid,status=CASE WHEN transcript_received THEN status ELSE 'AWAITING_TRANSCRIPTION' END WHERE organization_id=:org AND id=:id"), {"org": org, "id": result["id"], "sid": recording_sid})
    if kind == "recording" and not row["transcript_received"]:
        try:
            duration = float(form.get("RecordingDuration", "0"))
        except ValueError:
            duration = 0
        if duration <= 2 or duration >= 120:
            session.execute(text("UPDATE maintenance_phone_events SET status='TRANSCRIPTION_UNAVAILABLE' WHERE organization_id=:org AND id=:id"), {"org": org, "id": result["id"]})
            notify_maintenance(session, settings, org, actor, row["ticket_id"], "Voicemail transcription is unavailable. Review the recording in the authenticated Twilio console.", settings.twilio_account_sid + ":" + call_sid + ":unavailable", request_id)
    if kind != "transcription" or row["transcript_received"]:
        return
    body = form.get("TranscriptionText", "").strip()[:5000]
    status = "TRANSCRIBED" if form.get("TranscriptionStatus") == "completed" and body else "TRANSCRIPTION_FAILED"
    if status == "TRANSCRIPTION_FAILED":
        body = "Voicemail transcription failed. Review the recording in the authenticated Twilio console and contact the caller."
    add_message(session, org, row["ticket_id"], body, None, settings.session_secret, request.app.state.clock, actor, origin="resident_phone")
    session.execute(text("UPDATE maintenance_tickets SET handoff=true,asked_fields='[]'::jsonb WHERE organization_id=:org AND id=:ticket"), {"org": org, "ticket": row["ticket_id"]})
    session.execute(text("UPDATE maintenance_phone_events SET body=:body,status=:status,transcript_received=true WHERE organization_id=:org AND id=:id"), {"org": org, "id": result["id"], "body": body, "status": status})
    audit(session, org, actor, row["ticket_id"], request_id, "phone.transcription", status)
    notify_maintenance(session, settings, org, actor, row["ticket_id"], body, settings.twilio_account_sid + ":" + call_sid, request_id)


def download_media(settings, job, stop):
    parsed = urlsplit(job["url"])
    pattern = r"/2010-04-01/Accounts/" + re.escape(settings.twilio_account_sid) + r"/Messages/(?:SM|MM)[0-9a-fA-F]{32}/Media/ME[0-9a-fA-F]{32}"
    if parsed.scheme != "https" or parsed.netloc != "api.twilio.com" or parsed.query or parsed.fragment or not re.fullmatch(pattern, parsed.path):
        raise ValueError("Invalid media URL")
    if job["type"] not in {"image/jpeg", "image/png", "image/heic", "image/heif", "video/mp4", "video/quicktime"}:
        raise ValueError("Unsupported phone attachment")
    for attempt in range(3):
        try:
            with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False) as client:
                with ExitStack() as resources:
                    response = resources.enter_context(client.stream("GET", job["url"], auth=(settings.twilio_account_sid, settings.twilio_auth_token.get_secret_value())))
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location", "")
                        redirect = urlsplit(location)
                        if redirect.scheme != "https" or redirect.netloc != "mms.twiliocdn.com" or redirect.fragment:
                            raise ValueError("Invalid media redirect")
                        response = resources.enter_context(client.stream("GET", location))
                    response.raise_for_status()
                    payload = bytearray()
                    for chunk in response.iter_bytes():
                        payload.extend(chunk)
                        if len(payload) > 20 * 1024 * 1024:
                            raise ValueError("Phone attachment too large")
                    return bytes(payload)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code != 429 and exc.response.status_code < 500:
                raise
            if attempt == 2 or stop.wait(0.25 * 2 ** attempt):
                raise


def worker_loop(engine, settings, stop):
    from grok_bot.domain.maintenance_phone import logger

    from grok_bot.domain.maintenance_health import record_health

    next_follow_up = 0
    next_health = 0
    while not stop.is_set():
        try:
            if monotonic() >= next_follow_up:
                next_follow_up = monotonic() + 60
                process_follow_ups(engine, settings)
            route_web_requests(engine, settings)
            if settings.twilio_configured:
                process_pending(engine, settings, stop)
            if monotonic() >= next_health:
                record_health(engine, settings)
                next_health = monotonic() + 30
        except Exception as exc:
            logger.error(json.dumps({"event": "maintenance_phone_worker_failed", "phone_status": "WORKER_ERROR", "error_type": type(exc).__name__, "sqlstate": getattr(getattr(exc, "orig", None), "sqlstate", None)}))
            try:
                record_health(engine, settings, type(exc).__name__)
            except Exception:
                logger.error(json.dumps({"event": "maintenance_health_write_failed"}))
        stop.wait(2)


def process_follow_ups(engine, settings):
    from grok_bot.auth.permissions import Principal
    from grok_bot.domain.clock import SystemClock
    from grok_bot.domain.idempotency import find_replay, request_hash, store_replay
    from grok_bot.domain.maintenance_phone import queue_reply
    from grok_bot.domain.maintenance_workflow import close_unanswered_repairs, detail, follow_up_candidates
    from grok_bot.domain.maintenance_urgent import process_urgent_escalations

    with Session(engine) as session:
        if settings.twilio_configured:
            service_scope(session, settings)
            org, actor = settings.twilio_organization_id, settings.twilio_service_user_id
            name = session.execute(text("SELECT display_name FROM users WHERE organization_id=:org AND id=:id"), {"org": org, "id": actor}).scalar_one()
        elif settings.allows_demo_session:
            manager = session.execute(text("SELECT organization_id,user_id,display_name FROM app_demo_sample_session('property_manager')")).mappings().first()
            if manager is None:
                return
            org, actor, name = manager["organization_id"], manager["user_id"], manager["display_name"]
            set_tenant(session, org, actor)
        else:
            return
        principal = Principal(user_id=actor, organization_id=org, display_name=name, roles=("property_manager",), auth_method="maintenance_worker")
        candidates = follow_up_candidates(session, principal, SystemClock().now())
        lock_phone(session, org)
        from grok_bot.domain.maintenance_issues import backfill_issues

        from grok_bot.domain.maintenance_analysis import correct_appliance_urgency

        correct_appliance_urgency(session, principal, settings, SystemClock().now())
        backfill_issues(session, org, actor, SystemClock().now())
        close_unanswered_repairs(session, principal, SystemClock().now())
        process_urgent_escalations(session, settings, principal, SystemClock().now())
        for candidate in candidates:
            session.execute(text("SELECT id FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket FOR UPDATE"), {"org": org, "ticket": candidate["ticket_id"]}).scalar_one()
            if candidate["code"] not in detail(session, principal, candidate["ticket_id"], SystemClock().now())["follow_up_flags"]:
                continue
            key = request_hash("POST", "maintenance-follow-up", candidate)
            if find_replay(session, org, key, key):
                continue
            body = "Follow-up needed: " + candidate["message"]
            prefix = "follow-up:" if settings.twilio_configured else "simulated:follow-up:"
            notify_maintenance(session, settings, org, actor, candidate["ticket_id"], body, prefix + key, "maintenance-follow-up")
            session.execute(text("INSERT INTO ticket_messages (id,organization_id,ticket_id,body,author_role,sender_label) VALUES (:id,:org,:ticket,:body,'system','Stevie')"), {"id": uuid4(), "org": org, "ticket": candidate["ticket_id"], "body": body})
            if candidate["code"] in {"COMPLETION_CONFIRMATION_OVERDUE", "VISIT_FOLLOW_UP_REQUIRED"}:
                queue_reply(session, settings, org, actor, candidate["ticket_id"], body, "follow-up-resident:" + key, "maintenance-follow-up")
            store_replay(session, organization_id=org, key=key, hashed=key, status=200, body={"status": "RECORDED"})
            audit(session, org, actor, candidate["ticket_id"], "maintenance-follow-up", "maintenance.follow_up", candidate["code"])
        session.commit()


def route_web_requests(engine, settings):
    from grok_bot.domain.clock import SystemClock
    from grok_bot.domain.maintenance_plan import PLAN_VERSION

    with Session(engine) as session:
        if settings.twilio_configured:
            service_scope(session, settings)
            org, actor = settings.twilio_organization_id, settings.twilio_service_user_id
        elif settings.allows_demo_session:
            manager = session.execute(text("SELECT organization_id,user_id FROM app_demo_sample_session('property_manager')")).mappings().first()
            if manager is None:
                return
            org, actor = manager["organization_id"], manager["user_id"]
            set_tenant(session, org, actor)
        else:
            return
        unplanned = session.execute(text("SELECT t.id FROM maintenance_tickets t WHERE t.organization_id=:org AND t.status IN ('INTAKE_OPEN','MANAGER_REVIEW','TRIAGE_PENDING','WAITING_TENANT','ASSIGNMENT_PENDING') AND NOT EXISTS (SELECT 1 FROM ticket_messages human WHERE human.organization_id=t.organization_id AND human.ticket_id=t.id AND human.author_role IN ('manager','contractor')) AND NOT EXISTS (SELECT 1 FROM maintenance_analyses a WHERE a.organization_id=t.organization_id AND a.ticket_id=t.id AND a.result->>'plan_version'=:plan_version AND a.created_at >= COALESCE((SELECT max(m.created_at) FROM ticket_messages m WHERE m.organization_id=t.organization_id AND m.ticket_id=t.id AND m.author_role!='system'),t.created_at) AND a.created_at >= COALESCE((SELECT max(m.created_at) FROM media_objects m WHERE m.organization_id=t.organization_id AND m.ticket_id=t.id AND m.status='READY'),t.created_at)) ORDER BY t.created_at DESC FOR UPDATE SKIP LOCKED LIMIT 1"), {"org": org, "plan_version": str(PLAN_VERSION)}).scalar_one_or_none()
        if unplanned is not None:
            from grok_bot.auth.permissions import Principal
            from grok_bot.domain.maintenance import get_ticket
            from grok_bot.domain.maintenance_analysis import analyze, fingerprint

            name = session.execute(text("SELECT display_name FROM users WHERE organization_id=:org AND id=:id"), {"org": org, "id": actor}).scalar_one()
            principal = Principal(user_id=actor, organization_id=org, display_name=name, roles=("property_manager",), auth_method="maintenance_worker")
            details = get_ticket(session, org, unplanned, settings.session_secret, "manager")
            try:
                analyze(session, settings, principal, details, f"auto-plan:{PLAN_VERSION}:{unplanned}:{fingerprint(details)}", "maintenance-planning", SystemClock().now())
            except HTTPException as exc:
                if exc.status_code != 429:
                    raise
                session.rollback()
                set_tenant(session, org, actor)
            else:
                session.commit()
                return
        lock_phone(session, org)
        ticket = session.execute(text("SELECT * FROM maintenance_tickets WHERE organization_id=:org AND notification_status='PENDING' AND notification_event_id IS NULL AND (handoff OR urgent_triage OR emergency OR status NOT IN ('INTAKE_OPEN','MANAGER_REVIEW','TRIAGE_PENDING','WAITING_TENANT')) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"), {"org": org}).mappings().first()
        if ticket is None:
            return
        if ticket["status"] in {"CANCELED", "CLOSED", "COMPLETED"}:
            session.execute(text("UPDATE maintenance_tickets SET notification_status='SUPPRESSED' WHERE organization_id=:org AND id=:id"), {"org": org, "id": ticket["id"]})
            audit(session, org, actor, ticket["id"], "maintenance-routing", "maintenance.notification_suppressed", "SUPPRESSED")
            session.commit()
            return
        _, urgent = _classify(ticket["description"])
        session.execute(text("UPDATE maintenance_tickets SET urgent_triage=urgent_triage OR :urgent WHERE organization_id=:org AND id=:id"), {"org": org, "id": ticket["id"], "urgent": urgent})
        if urgent or ticket["urgent_triage"] or ticket["emergency"]:
            escalation = session.execute(text("SELECT state FROM escalations WHERE organization_id=:org AND ticket_id=:ticket ORDER BY created_at DESC,id DESC LIMIT 1"), {"org": org, "ticket": ticket["id"]}).scalar_one_or_none()
            if escalation is None:
                _open_escalation(session, org, ticket["id"], actor, SystemClock().now(), life_safety=ticket["emergency"])
            elif escalation == "ACKNOWLEDGED":
                session.execute(text("UPDATE maintenance_tickets SET notification_status='SUPPRESSED' WHERE organization_id=:org AND id=:ticket"), {"org": org, "ticket": ticket["id"]})
            session.commit()
            return
        if settings.twilio_configured and not (settings.maintenance_manager_notify_number if ticket["active_assignment_id"] is None else settings.twilio_maintenance_notify_number):
            session.execute(text("UPDATE maintenance_tickets SET notification_status='BLOCKED' WHERE organization_id=:org AND id=:id"), {"org": org, "id": ticket["id"]})
        else:
            cycle = session.scalar(text("SELECT id FROM audit_events WHERE organization_id=:org AND target_id=:ticket AND action='maintenance.workflow.reopen' ORDER BY created_at DESC,id DESC LIMIT 1"), {"org": org, "ticket": ticket["id"]})
            prefix = "web:" if settings.twilio_configured else "simulated:web:"
            route_key = prefix + str(ticket["id"]) + (":" + str(cycle) if cycle else "")
            notify_maintenance(session, settings, org, actor, ticket["id"], ticket["description"], route_key, "maintenance-routing")
        session.commit()


def process_pending(engine, settings, stop):
    with Session(engine) as session:
        service_scope(session, settings)
        lock_phone(session, settings.twilio_organization_id)
        session.execute(text("UPDATE maintenance_phone_events SET status='ATTACHMENT_FAILED' WHERE organization_id=:org AND status='MEDIA_PROCESSING' AND processing_at < clock_timestamp()-interval '10 minutes'"), {"org": settings.twilio_organization_id})
        unavailable = session.execute(text("UPDATE maintenance_phone_events SET status='TRANSCRIPTION_UNAVAILABLE' WHERE organization_id=:org AND status='AWAITING_TRANSCRIPTION' AND created_at < clock_timestamp()-interval '1 hour' RETURNING ticket_id,provider_key"), {"org": settings.twilio_organization_id}).mappings().all()
        for voicemail in unavailable:
            notify_maintenance(session, settings, settings.twilio_organization_id, settings.twilio_service_user_id, voicemail["ticket_id"], "Voicemail transcription did not arrive. Review the recording in the authenticated Twilio console.", voicemail["provider_key"] + ":unavailable", "phone-worker")
        candidate = session.execute(text("SELECT id,ticket_id FROM maintenance_phone_events WHERE organization_id=:org AND status IN ('QUEUED','MEDIA_PENDING') ORDER BY created_at,id LIMIT 1"), {"org": settings.twilio_organization_id}).mappings().first()
        if candidate is None:
            session.commit()
            return
        ticket_state = session.execute(text("SELECT status,verification,emergency,active_assignment_id FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket FOR UPDATE"), {"org": settings.twilio_organization_id, "ticket": candidate["ticket_id"]}).mappings().one()
        ticket_status = ticket_state["status"]
        row = session.execute(text("SELECT * FROM maintenance_phone_events WHERE organization_id=:org AND id=:id AND status IN ('QUEUED','MEDIA_PENDING') FOR UPDATE SKIP LOCKED"), {"org": settings.twilio_organization_id, "id": candidate["id"]}).mappings().first()
        if row is None:
            session.commit()
            return
        row = dict(row)
        if row["provider_key"].startswith("notify:urgent:"):
            escalation = session.execute(text("SELECT id,state FROM escalations WHERE organization_id=:org AND ticket_id=:ticket ORDER BY created_at DESC,id DESC LIMIT 1"), {"org": row["organization_id"], "ticket": row["ticket_id"]}).mappings().first()
            if ticket_status in {"COMPLETED", "CLOSED", "CANCELED"} or escalation is None or escalation["state"] != "OPEN" or str(escalation["id"]) != row["provider_key"].split(":")[2]:
                session.execute(text("UPDATE maintenance_phone_events SET status='SUPPRESSED' WHERE organization_id=:org AND id=:id"), {"org": row["organization_id"], "id": row["id"]})
                session.execute(text("UPDATE maintenance_tickets SET notification_status='SUPPRESSED' WHERE organization_id=:org AND notification_event_id=:id"), {"org": row["organization_id"], "id": row["id"]})
                audit(session, row["organization_id"], row["actor_id"], row["ticket_id"], "maintenance-urgent", "maintenance.urgent_suppressed", "SUPPRESSED")
                session.commit()
                return
        if row["provider_key"].startswith("notify:") and (ticket_state["verification"] != "VERIFIED" or ticket_state["active_assignment_id"] is None) and row["to_number"] != settings.maintenance_manager_notify_number:
            if not settings.maintenance_manager_notify_number:
                session.execute(text("UPDATE maintenance_phone_events SET status='BLOCKED' WHERE organization_id=:org AND id=:id"), {"org": row["organization_id"], "id": row["id"]})
                session.execute(text("UPDATE maintenance_tickets SET notification_status='BLOCKED' WHERE organization_id=:org AND notification_event_id=:id"), {"org": row["organization_id"], "id": row["id"]})
                audit(session, row["organization_id"], row["actor_id"], row["ticket_id"], "maintenance-routing", "maintenance.manager_reroute", "BLOCKED")
                session.commit()
                return
            row["to_number"] = settings.maintenance_manager_notify_number
            session.execute(text("UPDATE maintenance_phone_events SET to_number=:recipient WHERE organization_id=:org AND id=:id"), {"org": row["organization_id"], "id": row["id"], "recipient": row["to_number"]})
            audit(session, row["organization_id"], row["actor_id"], row["ticket_id"], "maintenance-routing", "maintenance.manager_reroute", "QUEUED")
        outbound = row["direction"] == "OUTBOUND"
        session.execute(text("UPDATE maintenance_phone_events SET status=:status,processing_at=clock_timestamp() WHERE organization_id=:org AND id=:id"), {"org": row["organization_id"], "id": row["id"], "status": "DELIVERY_UNKNOWN" if outbound else "MEDIA_PROCESSING"})
        if outbound:
            session.execute(text("UPDATE maintenance_tickets SET notification_status='DELIVERY_UNKNOWN' WHERE organization_id=:org AND notification_event_id=:id"), {"org": row["organization_id"], "id": row["id"]})
        session.commit()
    if outbound:
        send_reply(engine, settings, row)
        return
    jobs = row["media_jobs"]
    for job in jobs:
        try:
            payload = download_media(settings, job, stop)
            with Session(engine) as session:
                service_scope(session, settings)
                upload = request_upload(session, row["organization_id"], row["ticket_id"], job["type"], len(payload), "phone-photo", hashlib.sha256(payload).hexdigest())
                save_quarantine(session, settings, row["organization_id"], upload["id"], payload)
                result = store_and_scan(session, settings, row["organization_id"], upload["id"], None)
                session.commit()
                job["status"] = result["status"]
        except (httpx.HTTPError, ValueError, OSError, HTTPException):
            job["status"] = "FAILED"
    status = "RECEIVED" if all(job["status"] == "READY" for job in jobs) else "ATTACHMENT_FAILED"
    with Session(engine) as session:
        service_scope(session, settings)
        session.execute(text("UPDATE maintenance_phone_events SET media_jobs=CAST(:jobs AS jsonb),status=:status WHERE organization_id=:org AND id=:id"), {"org": row["organization_id"], "id": row["id"], "jobs": json.dumps(jobs), "status": status})
        audit(session, row["organization_id"], row["actor_id"], row["ticket_id"], "phone-worker", "phone.attachments", status)
        session.commit()


def send_reply(engine, settings, row):
    status = "DELIVERY_UNKNOWN"
    provider_sid = None
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False) as client:
            response = client.post(f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json", auth=(settings.twilio_account_sid, settings.twilio_auth_token.get_secret_value()), data={"From": settings.twilio_phone_number, "To": row["to_number"], "Body": row["body"], "StatusCallback": settings.twilio_public_url + "/v1/maintenance-phone/twilio/status?event=" + str(row["id"])})
        if response.status_code == 201:
            payload = response.json()
            provider_sid = payload.get("sid")
            if not re.fullmatch(r"(?:SM|MM)[0-9a-fA-F]{32}", provider_sid or ""):
                raise ValueError("Invalid message response")
            status = "ACCEPTED"
        elif 400 <= response.status_code < 500:
            status = "FAILED"
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    with Session(engine) as session:
        service_scope(session, settings)
        session.execute(text("UPDATE maintenance_phone_events SET status=:status,provider_sid=:sid WHERE organization_id=:org AND id=:id AND status='DELIVERY_UNKNOWN'"), {"org": row["organization_id"], "id": row["id"], "status": status, "sid": provider_sid})
        session.execute(text("UPDATE maintenance_tickets t SET notification_status=e.status FROM maintenance_phone_events e WHERE t.organization_id=:org AND e.organization_id=t.organization_id AND t.notification_event_id=e.id AND e.id=:id"), {"org": row["organization_id"], "id": row["id"]})
        audit(session, row["organization_id"], row["actor_id"], row["ticket_id"], "phone-worker", "phone.delivery", status)
        session.commit()
