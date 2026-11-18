from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from grok_bot.domain.maintenance_phone import audit
from grok_bot.errors import problem


def process_urgent_escalations(session, settings, principal, now):
    org = principal.organization_id
    if not session.execute(text("SELECT public.app_actor_is_manager() AND NULLIF(current_setting('app.organization_id',true),'')::uuid=:org"), {"org": org}).scalar_one():
        problem(403, "FORBIDDEN", "A scoped maintenance manager is required.")
    if settings.twilio_configured and org != settings.twilio_organization_id:
        problem(403, "FORBIDDEN", "The phone service belongs to another organization.")
    cutoff = now - timedelta(minutes=settings.maintenance_urgent_ack_minutes)
    tickets = session.execute(text("SELECT t.id,t.ticket_number,t.verification,t.emergency,t.active_assignment_id FROM maintenance_tickets t JOIN LATERAL (SELECT id,state,created_at FROM escalations WHERE organization_id=t.organization_id AND ticket_id=t.id ORDER BY created_at DESC,id DESC LIMIT 1) e ON true WHERE t.organization_id=:org AND (t.urgent_triage OR t.emergency) AND t.status NOT IN ('COMPLETED','CLOSED','CANCELED') AND e.state='OPEN' AND (NOT EXISTS (SELECT 1 FROM maintenance_phone_events p WHERE p.organization_id=:org AND p.provider_key=:urgent_prefix||e.id::text||:primary_suffix AND (p.status!='BLOCKED' OR NOT CASE WHEN t.verification!='VERIFIED' OR t.active_assignment_id IS NULL THEN :manager_ready ELSE :primary_ready END)) OR e.created_at<=:cutoff AND NOT EXISTS (SELECT 1 FROM maintenance_phone_events p WHERE p.organization_id=:org AND p.provider_key=:urgent_prefix||e.id::text||:backup_suffix AND (p.status!='BLOCKED' OR NOT :backup_ready))) ORDER BY e.created_at,t.id LIMIT 100 FOR UPDATE OF t SKIP LOCKED"), {"org": org, "cutoff": cutoff, "urgent_prefix": "notify:urgent:", "primary_suffix": ":primary", "backup_suffix": ":backup", "primary_ready": bool(settings.twilio_configured and settings.twilio_maintenance_notify_number), "manager_ready": bool(settings.twilio_configured and settings.maintenance_manager_notify_number), "backup_ready": bool(settings.maintenance_backup_notify_number)}).mappings().all()
    for ticket in tickets:
        escalation = session.execute(text("SELECT id,state,created_at FROM escalations WHERE organization_id=:org AND ticket_id=:ticket ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE"), {"org": org, "ticket": ticket["id"]}).mappings().first()
        if escalation is None or escalation["state"] != "OPEN":
            continue
        manager_required = ticket["verification"] != "VERIFIED" or ticket["active_assignment_id"] is None
        primary_name = "the property manager" if manager_required else "Johnny"
        primary_number = settings.maintenance_manager_notify_number if manager_required else settings.twilio_maintenance_notify_number
        recipients = [("primary", primary_number)]
        if escalation["created_at"] <= cutoff:
            recipients.append(("backup", settings.maintenance_backup_notify_number))
        for kind, recipient in recipients:
            if kind == "backup" and not recipient:
                status = "BLOCKED"
                message = "The urgent request is still unacknowledged. The backup contact needs setup; no backup text was sent."
            elif not settings.twilio_configured:
                status = "SIMULATED"
                message = f"Demo: urgent alert recorded for {primary_name}; no real text sent." if kind == "primary" else "Demo: backup urgent alert recorded because nobody acknowledged the request; no real text sent."
            elif not recipient:
                status = "BLOCKED"
                message = f"The urgent alert for {primary_name} is blocked because the contact number needs setup; no text was sent."
            else:
                status = "QUEUED"
                message = f"An urgent alert is queued for {primary_name}. Acknowledgment is still pending." if kind == "primary" else "No acknowledgment arrived in time. An urgent alert is queued for the backup contact."
            alert_body = f"Urgent maintenance request #{ticket['ticket_number']}. " + ("A manager must review this request. Open the manager maintenance queue and reply I'm on it in the ticket chat." if manager_required else "Open the maintenance queue and reply I'm on it in the ticket chat.")
            event_id = session.execute(text("INSERT INTO maintenance_phone_events (id,organization_id,actor_id,ticket_id,channel,direction,from_number,to_number,body,status,provider_key,created_at) VALUES (:id,:org,:actor,:ticket,'SMS','OUTBOUND',:sender,:recipient,:body,:status,:key,:now) ON CONFLICT (organization_id,provider_key) DO UPDATE SET from_number=EXCLUDED.from_number,to_number=EXCLUDED.to_number,body=EXCLUDED.body,status=EXCLUDED.status WHERE maintenance_phone_events.status='BLOCKED' AND EXCLUDED.status IN ('QUEUED','SIMULATED') AND :recover_ready RETURNING id"), {"id": uuid4(), "org": org, "actor": principal.user_id, "ticket": ticket["id"], "sender": settings.twilio_phone_number or "", "recipient": recipient or "", "body": alert_body, "status": status, "key": f"notify:urgent:{escalation['id']}:{kind}", "now": now, "recover_ready": bool(recipient and (kind == "backup" or settings.twilio_configured))}).scalar_one_or_none()
            if event_id is None:
                continue
            session.execute(text("INSERT INTO ticket_messages (id,organization_id,ticket_id,body,author_role,sender_label) VALUES (:id,:org,:ticket,:body,'system','Stevie')"), {"id": uuid4(), "org": org, "ticket": ticket["id"], "body": message})
            session.execute(text("UPDATE maintenance_tickets SET notification_event_id=:event,notification_status=:status WHERE organization_id=:org AND id=:ticket"), {"org": org, "ticket": ticket["id"], "event": event_id, "status": status})
            audit(session, org, principal.user_id, ticket["id"], "maintenance-urgent", "maintenance.urgent_" + kind, status)
