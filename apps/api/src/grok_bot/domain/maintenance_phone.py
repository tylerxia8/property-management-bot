import logging
from uuid import uuid4

from sqlalchemy import text

from grok_bot.domain.idempotency import find_replay, request_hash, store_replay
from grok_bot.domain.clock import FrozenClock
from grok_bot.domain.maintenance import add_message, create_unverified_ticket
from grok_bot.domain.records import write_audit
from grok_bot.errors import problem

logger = logging.getLogger(__name__)


def events(session, organization_id):
    rows = session.execute(text("SELECT e.*, t.ticket_number FROM maintenance_phone_events e JOIN maintenance_tickets t ON t.organization_id=e.organization_id AND t.id=e.ticket_id WHERE e.organization_id=:org ORDER BY e.created_at DESC, e.id DESC LIMIT 100"), {"org": organization_id}).mappings().all()
    return [present(row) for row in rows]


def present(row):
    return {"id": str(row["id"]), "channel": row["channel"], "direction": row["direction"], "recipient_kind": "MAINTENANCE" if row["provider_key"].startswith("notify:") else "RESIDENT", "body": row["body"], "from_number": row["from_number"], "to_number": row["to_number"], "ticket_id": str(row["ticket_id"]), "ticket_number": row["ticket_number"], "status": row["status"], "created_at": row["created_at"].isoformat()}


def lock_phone(session, organization_id):
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"), {"scope": f"maintenance-phone:{organization_id}"})


def rate_limit(session, organization_id, actor_id, sender):
    row = session.execute(text("SELECT count(*) AS total, count(*) FILTER (WHERE from_number=:sender OR actor_id=:actor AND provider_key LIKE 'simulated:%') AS sender_total FROM maintenance_phone_events WHERE organization_id=:org AND created_at > clock_timestamp()-interval '1 minute'"), {"org": organization_id, "actor": actor_id, "sender": sender}).mappings().one()
    if row["total"] >= 60 or row["sender_total"] >= 10:
        problem(429, "RATE_LIMITED", "Please wait before sending another phone request.")


def inbound(session, settings, organization_id, actor_id, channel, sender, body, provider_key, status, now, request_id):
    lock_phone(session, organization_id)
    existing = session.execute(text("SELECT e.*, t.ticket_number FROM maintenance_phone_events e JOIN maintenance_tickets t ON t.organization_id=e.organization_id AND t.id=e.ticket_id WHERE e.organization_id=:org AND provider_key=:key"), {"org": organization_id, "key": provider_key}).mappings().first()
    if existing is not None:
        return present(existing), False
    rate_limit(session, organization_id, actor_id, sender)
    ticket = None
    if sender != "anonymous" and channel == "SMS" and not body.lower().startswith("new:"):
        ticket = session.execute(text("SELECT t.id,t.ticket_number FROM maintenance_phone_events e JOIN maintenance_tickets t ON t.organization_id=e.organization_id AND t.id=e.ticket_id WHERE e.organization_id=:org AND e.from_number=:sender AND e.direction='INBOUND' AND (e.provider_key LIKE 'simulated:%')=:simulated AND t.status NOT IN ('CLOSED','COMPLETED','CANCELED') ORDER BY e.created_at DESC LIMIT 1"), {"org": organization_id, "sender": sender, "simulated": provider_key.startswith("simulated:")}).mappings().first()
    if ticket is None:
        ticket = create_unverified_ticket(session, organization_id, body, settings.session_secret, now)
    else:
        add_message(session, organization_id, ticket["id"], body, None, settings.session_secret, FrozenClock(now), actor_id, origin="resident_phone")
    session.execute(text("UPDATE maintenance_tickets SET handoff=true, asked_fields='[]'::jsonb WHERE organization_id=:org AND id=:ticket"), {"org": organization_id, "ticket": ticket["id"]})
    row = session.execute(text("INSERT INTO maintenance_phone_events (id,organization_id,actor_id,ticket_id,channel,direction,from_number,to_number,body,status,provider_key) VALUES (:id,:org,:actor,:ticket,:channel,'INBOUND',:sender,:recipient,:body,:status,:key) RETURNING *"), {"id": uuid4(), "org": organization_id, "actor": actor_id, "ticket": ticket["id"], "channel": channel, "sender": sender, "recipient": settings.twilio_phone_number or "+15550100000", "body": body, "status": status, "key": provider_key}).mappings().one()
    audit(session, organization_id, actor_id, ticket["id"], request_id, "phone.received", status)
    if channel == "SMS" and sender != "anonymous":
        queue_reply(session, settings, organization_id, actor_id, ticket["id"], "Your maintenance message is saved. Next we work out the problem and repair plan. No repair has been dispatched. This line is not monitored for emergencies; if in immediate danger, call emergency services. Start a separate request with NEW: followed by the problem.", "ack:" + provider_key, request_id)
    if channel == "SMS" or provider_key.startswith("simulated:"):
        notify_maintenance(session, settings, organization_id, actor_id, ticket["id"], body, provider_key, request_id)
    return present({**row, "ticket_number": ticket["ticket_number"]}), True


def simulate(session, settings, principal, body, key, now, request_id):
    lock_phone(session, principal.organization_id)
    scoped_key = request_hash("POST", "maintenance-phone-simulate", {"actor": str(principal.user_id), "key": key})
    hashed = request_hash("POST", "maintenance-phone-simulate", body)
    replay = find_replay(session, principal.organization_id, scoped_key, hashed)
    if replay:
        return replay["body"]
    result, _ = inbound(session, settings, principal.organization_id, principal.user_id, body["channel"], body["from_number"], body["body"], "simulated:" + scoped_key, "SIMULATED", now, request_id)
    store_replay(session, organization_id=principal.organization_id, key=scoped_key, hashed=hashed, status=201, body=result)
    return result


def reply(session, settings, principal, body, key, request_id):
    lock_phone(session, principal.organization_id)
    scoped_key = request_hash("POST", "maintenance-phone-reply", {"actor": str(principal.user_id), "key": key})
    hashed = request_hash("POST", "maintenance-phone-reply", body)
    replay = find_replay(session, principal.organization_id, scoped_key, hashed)
    if replay:
        return replay["body"]
    original = session.execute(text("SELECT e.*,t.ticket_number FROM maintenance_phone_events e JOIN maintenance_tickets t ON t.organization_id=e.organization_id AND t.id=e.ticket_id WHERE e.organization_id=:org AND e.ticket_id=:ticket AND e.direction='INBOUND' ORDER BY e.created_at LIMIT 1"), {"org": principal.organization_id, "ticket": body["ticket_id"]}).mappings().first()
    if original is None:
        problem(404, "NOT_FOUND", "Phone request not found.")
    if original["from_number"] == "anonymous":
        problem(422, "PHONE_UNAVAILABLE", "The caller did not provide a reply number.")
    rate_limit(session, principal.organization_id, principal.user_id, original["from_number"])
    result = queue_reply(session, settings, principal.organization_id, principal.user_id, body["ticket_id"], body["body"], "reply:" + scoped_key, request_id)
    store_replay(session, organization_id=principal.organization_id, key=scoped_key, hashed=hashed, status=201, body=result)
    audit(session, principal.organization_id, principal.user_id, body["ticket_id"], request_id, "phone.reply_requested", result["status"])
    return result


def audit(session, organization_id, actor_id, ticket_id, request_id, action, status):
    write_audit(session, organization_id=organization_id, actor_id=actor_id, action=action, target_type="maintenance_ticket", target_id=ticket_id, target_version=None, request_id=request_id, before_state=None, after_state={"status": status})
    logger.info("maintenance_phone", extra={"request_id": request_id, "phone_action": action, "phone_status": status})


def queue_reply(session, settings, organization_id, actor_id, ticket_id, body, key, request_id):
    lock_phone(session, organization_id)
    existing = session.execute(text("SELECT e.*,t.ticket_number FROM maintenance_phone_events e JOIN maintenance_tickets t ON t.organization_id=e.organization_id AND t.id=e.ticket_id WHERE e.organization_id=:org AND e.provider_key=:key"), {"org": organization_id, "key": key}).mappings().first()
    if existing:
        return present(existing)
    original = session.execute(text("SELECT e.*,t.ticket_number FROM maintenance_phone_events e JOIN maintenance_tickets t ON t.organization_id=e.organization_id AND t.id=e.ticket_id WHERE e.organization_id=:org AND e.ticket_id=:ticket AND e.direction='INBOUND' ORDER BY e.created_at LIMIT 1"), {"org": organization_id, "ticket": ticket_id}).mappings().first()
    if original is None or original["from_number"] == "anonymous":
        return None
    status = "QUEUED" if settings.twilio_configured and settings.twilio_organization_id == organization_id and not original["provider_key"].startswith("simulated:") else "SIMULATED"
    row = session.execute(text("INSERT INTO maintenance_phone_events (id,organization_id,actor_id,ticket_id,channel,direction,from_number,to_number,body,status,provider_key) VALUES (:id,:org,:actor,:ticket,'SMS','OUTBOUND',:sender,:recipient,:body,:status,:key) RETURNING *"), {"id": uuid4(), "org": organization_id, "actor": actor_id, "ticket": ticket_id, "sender": original["to_number"], "recipient": original["from_number"], "body": body, "key": key, "status": status}).mappings().one()
    session.execute(text("INSERT INTO ticket_messages (id,organization_id,ticket_id,body,classifier_result,author_role,sender_label) VALUES (:id,:org,:ticket,:body,NULL,'system','Stevie')"), {"id": uuid4(), "org": organization_id, "ticket": ticket_id, "body": ("Simulated SMS reply: " if status == "SIMULATED" else "SMS reply queued: ") + body})
    audit(session, organization_id, actor_id, ticket_id, request_id, "phone.reply_queued", status)
    return present({**row, "ticket_number": original["ticket_number"]})


def notify_maintenance(session, settings, organization_id, actor_id, ticket_id, body, key, request_id):
    simulated = key.startswith("simulated:")
    ticket = session.execute(text("SELECT ticket_number,verification,active_assignment_id FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket"), {"org": organization_id, "ticket": ticket_id}).mappings().one()
    recipient = "+15550100200" if simulated else settings.maintenance_manager_notify_number if ticket["verification"] != "VERIFIED" or ticket["active_assignment_id"] is None else settings.twilio_maintenance_notify_number
    if not recipient:
        session.execute(text("UPDATE maintenance_tickets SET notification_status='BLOCKED' WHERE organization_id=:org AND id=:ticket"), {"org": organization_id, "ticket": ticket_id})
        return
    verification = "Caller and home are unverified. " if ticket["verification"] != "VERIFIED" else ""
    message = f"Maintenance request #{ticket['ticket_number']}: {body[:1250]}\n{verification}Review the maintenance queue before arranging work."
    inserted = session.execute(text("INSERT INTO maintenance_phone_events (id,organization_id,actor_id,ticket_id,channel,direction,from_number,to_number,body,status,provider_key) VALUES (:id,:org,:actor,:ticket,'SMS','OUTBOUND',:sender,:recipient,:body,:status,:key) ON CONFLICT (organization_id,provider_key) DO NOTHING RETURNING id"), {"id": uuid4(), "org": organization_id, "actor": actor_id, "ticket": ticket_id, "sender": settings.twilio_phone_number or "+15550100000", "recipient": recipient, "body": message, "status": "SIMULATED" if simulated else "QUEUED", "key": "notify:" + key}).scalar_one_or_none()
    if inserted:
        session.execute(text("UPDATE maintenance_tickets SET notification_event_id=:event,notification_status=:status WHERE organization_id=:org AND id=:ticket"), {"org": organization_id, "ticket": ticket_id, "event": inserted, "status": "SIMULATED" if simulated else "QUEUED"})
        audit(session, organization_id, actor_id, ticket_id, request_id, "phone.maintenance_notified", "SIMULATED" if simulated else "QUEUED")
