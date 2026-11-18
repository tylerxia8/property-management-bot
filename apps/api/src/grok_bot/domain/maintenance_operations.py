from datetime import timedelta
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from grok_bot.domain import idempotency
from grok_bot.domain.records import write_audit
from grok_bot.domain.maintenance_health import worker_health
from grok_bot.errors import problem


WORKERS = """
    SELECT c.id,coalesce(u.display_name,p.display_name) AS name,c.user_id,c.approved,
           c.service_property_ids,c.service_categories,c.accepting_work,
           c.availability_note,c.max_open_jobs,c.version,
           (SELECT count(*) FROM assignments a JOIN maintenance_tickets t
             ON t.organization_id=a.organization_id AND t.active_assignment_id=a.id
             WHERE a.organization_id=c.organization_id AND a.contractor_profile_id=c.id
               AND a.status <> 'DECLINED' AND t.status NOT IN ('COMPLETED','CLOSED','CANCELED')) AS open_jobs,
           public.app_maintenance_worker_active(c.id) AS active
    FROM contractor_profiles c LEFT JOIN users u ON u.organization_id=c.organization_id AND u.id=c.user_id
    JOIN parties p ON p.organization_id=c.organization_id AND p.id=c.party_id
    WHERE c.organization_id=:org ORDER BY open_jobs,name,c.id
"""


def recommend_workers(session, organization_id, ticket_id):
    if not session.scalar(text("SELECT app_actor_is_manager()")):
        problem(403, "FORBIDDEN", "Only managers can recommend repair workers.")
    ticket = session.execute(text("SELECT t.category,u.property_id FROM maintenance_tickets t LEFT JOIN units u ON u.organization_id=t.organization_id AND u.id=t.unit_id WHERE t.organization_id=:org AND t.id=:ticket"), {"org": organization_id, "ticket": ticket_id}).mappings().first()
    if ticket is None:
        problem(404, "NOT_FOUND", "Repair request not found.")
    return jsonable_encoder([dict(worker) for worker in session.execute(text(WORKERS), {"org": organization_id}).mappings() if worker["approved"] and worker["active"] and worker["accepting_work"] and worker["open_jobs"] < worker["max_open_jobs"] and (not worker["service_property_ids"] or ticket["property_id"] in worker["service_property_ids"]) and (not worker["service_categories"] or ticket["category"] in worker["service_categories"])])


def operations(session, principal, now, settings):
    if not principal.allows("maintenance.manage"):
        problem(403, "FORBIDDEN", "Only managers can view maintenance operations.")
    params = {"org": principal.organization_id, "now": now}
    rows = session.execute(text("""
        SELECT t.id,t.ticket_number,t.description,t.status,t.emergency,t.urgent_triage,
          t.notification_status,t.created_at,t.updated_at,a.status AS assignment_status,
          a.created_at AS assigned_at,u.display_name AS owner_name,
          greatest(t.created_at,
            (SELECT max(m.created_at) FROM ticket_messages m WHERE m.organization_id=t.organization_id AND m.ticket_id=t.id AND m.author_role<>'system'),
            (SELECT max(e.created_at) FROM audit_events e WHERE e.organization_id=t.organization_id AND e.target_id=t.id AND e.action LIKE 'maintenance.workflow.%')) AS activity_at,
          EXISTS (SELECT 1 FROM escalations e WHERE e.organization_id=t.organization_id AND e.ticket_id=t.id AND e.state='OPEN') AS unacknowledged,
          EXISTS (SELECT 1 FROM maintenance_appointments v WHERE v.organization_id=t.organization_id AND v.ticket_id=t.id AND v.assignment_id=t.active_assignment_id AND v.status='CONFIRMED' AND v.ends_at<:now) AS overdue_visit
        FROM maintenance_tickets t
        LEFT JOIN assignments a ON a.organization_id=t.organization_id AND a.id=t.active_assignment_id
        LEFT JOIN contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id
        LEFT JOIN users u ON u.organization_id=c.organization_id AND u.id=c.user_id
        WHERE t.organization_id=:org AND t.status NOT IN ('COMPLETED','CLOSED','CANCELED')
        ORDER BY t.emergency DESC,t.urgent_triage DESC,t.created_at,t.id
    """), params).mappings()
    requests = []
    for row in rows:
        reasons = []
        if row["unacknowledged"] and (row["urgent_triage"] or row["emergency"]):
            reasons.append("URGENT_UNACKNOWLEDGED")
        if row["status"] not in {"INTAKE_OPEN", "TRIAGE_PENDING", "WAITING_TENANT"} and (row["assignment_status"] is None or row["assignment_status"] == "DECLINED"):
            reasons.append("NO_OWNER")
        if row["notification_status"] in {"FAILED", "UNDELIVERED", "BLOCKED"}:
            reasons.append("NOTIFICATION_FAILED")
        if row["notification_status"] == "DELIVERY_UNKNOWN":
            reasons.append("NOTIFICATION_UNKNOWN")
        if row["overdue_visit"] and row["status"] != "COMPLETION_REVIEW":
            reasons.append("VISIT_OVERDUE")
        if row["status"] == "WAITING_PARTS" or session.scalar(text("SELECT 1 FROM maintenance_issues WHERE organization_id=:org AND ticket_id=:ticket AND status='WAITING_PARTS' LIMIT 1"), {"org": principal.organization_id, "ticket": row["id"]}):
            reasons.append("WAITING_PARTS")
        if row["status"] == "WAITING_TENANT" and now - row["activity_at"] >= timedelta(hours=24):
            reasons.append("TENANT_REPLY_OVERDUE")
        if row["assignment_status"] == "PENDING" and now - row["assigned_at"] >= timedelta(hours=24):
            reasons.append("WORKER_REPLY_OVERDUE")
        actions = {"URGENT_UNACKNOWLEDGED": "Confirm who is handling the urgent request", "NO_OWNER": "Assign an available repair worker", "NOTIFICATION_FAILED": "Review failed notification and contact the worker", "NOTIFICATION_UNKNOWN": "Verify notification receipt before retrying", "VISIT_OVERDUE": "Request a visit outcome", "WAITING_PARTS": "Confirm parts arrival and next visit", "TENANT_REPLY_OVERDUE": "Follow up with the resident", "WORKER_REPLY_OVERDUE": "Confirm worker availability or reassign"}
        requests.append({"id": row["id"], "ticket_number": row["ticket_number"], "description": row["description"], "status": row["status"], "priority": "EMERGENCY" if row["emergency"] else "URGENT" if row["urgent_triage"] else "ROUTINE", "owner_name": row["owner_name"], "next_action": actions[reasons[0]] if reasons else "Monitor the next update", "reason_codes": reasons, "notification_status": row["notification_status"], "last_activity_at": max(row["activity_at"], row["updated_at"])})
    counts = session.execute(text("SELECT status,count(*) AS count FROM maintenance_phone_events WHERE organization_id=:org AND direction='OUTBOUND' GROUP BY status"), params).mappings().all()
    statuses = {row["status"]: row["count"] for row in counts}
    return jsonable_encoder({"background_worker": worker_health(session, principal.organization_id, now), "requests": requests, "workers": [dict(row) for row in session.execute(text(WORKERS), params).mappings()], "properties": [dict(row) for row in session.execute(text("SELECT id,name FROM properties WHERE organization_id=:org ORDER BY name,id"), params).mappings()], "worker_health": {"phone_configured": settings.twilio_configured and settings.twilio_organization_id == principal.organization_id, "history_configured": bool(settings.maintenance_history_path) and settings.maintenance_history_organization_id == principal.organization_id, "pending_notifications": sum(statuses.get(status, 0) for status in ("PENDING", "QUEUED", "ACCEPTED", "SENDING")), "failed_notifications": sum(statuses.get(status, 0) for status in ("FAILED", "UNDELIVERED", "BLOCKED")), "unknown_notifications": statuses.get("DELIVERY_UNKNOWN", 0)}})


def update_worker(session, principal, profile_id, changes, key, now):
    if not principal.allows("maintenance.manage"):
        problem(403, "FORBIDDEN", "Only managers can configure repair workers.")
    org = principal.organization_id
    scoped_key = idempotency.request_hash("PATCH", "maintenance-worker-key", {"actor": str(principal.user_id), "key": key})
    hashed = idempotency.request_hash("PATCH", str(profile_id), changes)
    params = {"org": org, "id": profile_id, "actor": principal.user_id, "now": now}
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"), {"scope": f"maintenance-workers:{org}:{principal.user_id}"})
    replay = idempotency.find_replay(session, org, scoped_key, hashed)
    if replay:
        return replay["body"]
    recent = session.scalar(text("SELECT count(*) FROM audit_events WHERE organization_id=:org AND actor_id=:actor AND action='maintenance.worker_updated' AND created_at>:now-interval '1 minute'"), params)
    if recent >= 30:
        problem(429, "RATE_LIMITED", "Too many worker updates. Try again shortly.")
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"), {"scope": f"maintenance-worker:{profile_id}"})
    before = session.execute(text("SELECT service_property_ids,service_categories,accepting_work,availability_note,max_open_jobs,approved,version FROM contractor_profiles WHERE organization_id=:org AND id=:id FOR UPDATE"), params).mappings().first()
    if before is None:
        problem(404, "NOT_FOUND", "Repair worker not found.")
    if before["version"] != changes["version"]:
        problem(409, "VERSION_CONFLICT", "This worker changed. Refresh before saving.")
    values = {**dict(before), **changes}
    property_ids = [UUID(value) for value in values["service_property_ids"]] if "service_property_ids" in changes else values["service_property_ids"]
    if property_ids:
        found = session.scalars(text("SELECT id FROM properties WHERE organization_id=:org AND id=ANY(CAST(:ids AS uuid[]))"), {"org": org, "ids": property_ids}).all()
        if set(found) != set(property_ids):
            problem(422, "VALIDATION_ERROR", "Choose properties in this organization.")
    session.execute(text("UPDATE contractor_profiles SET service_property_ids=CAST(:service_property_ids AS uuid[]),service_categories=CAST(:service_categories AS text[]),accepting_work=:accepting_work,availability_note=:availability_note,max_open_jobs=:max_open_jobs,approved=:approved,version=version+1,updated_at=:now WHERE organization_id=:org AND id=:id"), {**params, **values, "service_property_ids": property_ids})
    result = next(dict(row) for row in session.execute(text(WORKERS), params).mappings() if row["id"] == profile_id)
    result = jsonable_encoder(result)
    write_audit(session, organization_id=org, actor_id=principal.user_id, action="maintenance.worker_updated", target_type="contractor_profile", target_id=profile_id, target_version=result["version"], request_id=scoped_key, before_state=jsonable_encoder(dict(before)), after_state=result)
    idempotency.store_replay(session, organization_id=org, key=scoped_key, hashed=hashed, status=200, body=result)
    return result
