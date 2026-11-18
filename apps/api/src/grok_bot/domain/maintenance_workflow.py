import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from grok_bot.domain import idempotency
from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.maintenance_idempotency import find_replay, store_replay
from grok_bot.domain.maintenance_issues import apply_chat_updates, list_issues, mark_ticket_outcome, reconcile_ticket, sync_issues
from grok_bot.domain.maintenance_operations import recommend_workers
from grok_bot.domain.maintenance_scheduling import parse_chat_visit
from grok_bot.domain.maintenance_guidance import explicit_resolution, matching_families, tracked_issues
from grok_bot.domain.maintenance import _open_escalation, assign_contractor, can_view_ticket, create_appointment
from grok_bot.domain.records import write_audit
from grok_bot.errors import problem


def due_flags(ticket, assignment, work, appointments, now):
    if ticket["status"] in {"COMPLETED", "CLOSED", "CANCELED"}:
        return []
    appointments = [visit for visit in appointments if assignment and visit["assignment_id"] == assignment["id"]]
    flags = []
    if ticket["status"] == "WAITING_TENANT" and now - ticket.get("workflow_activity_at", ticket["created_at"]) >= timedelta(hours=24):
        flags.append("TENANT_REPLY_OVERDUE")
    if assignment and assignment["status"] == "PENDING" and now - assignment["created_at"] >= timedelta(hours=24):
        flags.append("ASSIGNMENT_RESPONSE_OVERDUE")
    if ticket["status"] == "COMPLETION_REVIEW" and work and work["completed_at"] and now - work["completed_at"] >= timedelta(hours=48):
        flags.append("COMPLETION_CONFIRMATION_OVERDUE")
    if work and not work["completed_at"] and any(a["status"] == "CONFIRMED" and a["ends_at"] < now for a in appointments):
        flags.append("VISIT_FOLLOW_UP_REQUIRED")
    if now - max([ticket.get("workflow_activity_at", ticket["created_at"]), *([assignment["updated_at"]] if assignment else []), *([work["updated_at"]] if work else []), *[a["updated_at"] for a in appointments]]) >= timedelta(hours=48) and not flags:
        flags.append("NO_RECENT_PROGRESS")
    return flags


def _records(session, org, ticket_id):
    params = {"org": org, "ticket": ticket_id}
    assignment = session.execute(text("SELECT * FROM assignments WHERE organization_id = :org AND ticket_id = :ticket AND id = (SELECT active_assignment_id FROM maintenance_tickets WHERE organization_id = :org AND id = :ticket)"), params).mappings().first()
    work = session.execute(text("SELECT * FROM work_orders WHERE organization_id = :org AND ticket_id = :ticket AND assignment_id = (SELECT active_assignment_id FROM maintenance_tickets WHERE organization_id = :org AND id = :ticket) ORDER BY created_at DESC,id DESC LIMIT 1"), params).mappings().first()
    appointments = session.execute(text("SELECT * FROM maintenance_appointments WHERE organization_id = :org AND ticket_id = :ticket ORDER BY starts_at DESC"), params).mappings().all()
    return assignment, work, appointments


def _actions(role, ticket, assignment, work, appointments, now):
    if role == "contractor" and assignment and assignment["status"] == "DECLINED":
        return []
    actions = ["message"]
    if ticket["status"] in {"COMPLETION_REVIEW", "COMPLETED", "CLOSED"}:
        return actions + (["confirm_completion", "reopen"] if role == "tenant" and ticket["status"] == "COMPLETION_REVIEW" else ["reopen"] if role == "tenant" else [])
    if ticket["status"] == "CANCELED":
        return actions
    if role == "manager":
        if not assignment or assignment["status"] == "DECLINED":
            actions.append("assign")
    if role == "tenant":
        if not assignment and not ticket["emergency"]:
            actions.append("resolve_self")
        if any(visit["status"] in {"REQUESTED", "CONFIRMED"} and visit["starts_at"] > now and assignment and visit["assignment_id"] == assignment["id"] for visit in appointments):
            actions.append("confirm_visit")
        actions.append("availability")
    if role == "contractor" and not assignment:
        if ticket["status"] in {"INTAKE_OPEN", "TRIAGE_PENDING", "WAITING_TENANT"}:
            return []
        return ["message", "accept", "arrange_repair"]
    if role == "contractor" and assignment:
        if assignment["status"] == "PENDING":
            actions.extend(["arrange_repair", "accept", "decline", "start_work", "complete"])
        if assignment["status"] == "ACCEPTED" and work:
            if not work["started_at"]:
                actions.extend(["arrange_repair", "propose_visit", "decline", "start_work", "complete"])
            elif not work["completed_at"]:
                actions.append("complete")
    return actions


def _contractors(session, org, role):
    if role != "manager":
        return []
    return [dict(row) for row in session.execute(text("SELECT id,name,trades FROM app_workflow_contractors()"), {"org": org}).mappings()]


def detail(session, principal, ticket_id, now):
    org = principal.organization_id
    role = can_view_ticket(session, org, ticket_id, principal.user_id, principal.roles)
    if role is None:
        problem(404, "NOT_FOUND", "Repair request not found.")
    ticket = session.execute(text("SELECT * FROM maintenance_tickets WHERE organization_id = :org AND id = :ticket"), {"org": org, "ticket": ticket_id}).mappings().one()
    assignment, work, appointments = _records(session, org, ticket_id)
    if role == "contractor" and assignment and not session.execute(text("SELECT 1 FROM contractor_profiles WHERE organization_id = :org AND id = :profile AND user_id = :actor"), {"org": org, "profile": assignment["contractor_profile_id"], "actor": principal.user_id}).scalar():
        problem(404, "NOT_FOUND", "Repair request not found.")
    messages = session.execute(text("SELECT id,body,author_role,sender_label,created_at,media_ids FROM ticket_messages WHERE organization_id = :org AND ticket_id = :ticket ORDER BY created_at,id"), {"org": org, "ticket": ticket_id}).mappings().all()
    media = session.execute(text("SELECT id,status,declared_content_type AS content_type FROM media_objects WHERE organization_id = :org AND ticket_id = :ticket AND status = 'READY' ORDER BY created_at"), {"org": org, "ticket": ticket_id}).mappings().all()
    home = session.execute(text("SELECT property_name,unit_label FROM app_workflow_home(:ticket)"), {"ticket": ticket_id}).mappings().first()
    activity = session.execute(text("SELECT max(created_at) FROM audit_events WHERE organization_id=:org AND target_id=:ticket AND action LIKE 'maintenance.workflow.%'"), {"org": org, "ticket": ticket_id}).scalar()
    ticket = {**dict(ticket), "workflow_activity_at": max([ticket["created_at"], *([activity] if activity else []), *[m["created_at"] for m in messages if m["author_role"] != "system"]])}
    actions = _actions(role, ticket, assignment, work, appointments, now)
    escalation = session.execute(text("SELECT id,state,created_at,acknowledged_at FROM escalations WHERE organization_id=:org AND ticket_id=:ticket ORDER BY created_at DESC,id DESC LIMIT 1"), {"org": org, "ticket": ticket_id}).mappings().first()
    issues = tracked_issues(ticket["description"], [message["body"] for message in messages if message["author_role"] == "tenant"])
    return jsonable_encoder({"issue_records": list_issues(session, org, ticket_id), "escalation": dict(escalation) if escalation else None, "issues": issues, "role": role, "available_actions": actions, "ticket": {"id": ticket_id, "ticket_number": ticket["ticket_number"], "description": ticket["description"], "status": ticket["status"], "verification": ticket["verification"], "priority": "EMERGENCY" if ticket["emergency"] else "URGENT" if ticket["urgent_triage"] else "ROUTINE", "home": dict(home) if home else None}, "assignment": dict(assignment) if assignment else None, "work_order": dict(work) if work else None, "appointments": [dict(a) for a in appointments], "availability": {"windows": ticket["availability_windows"]}, "messages": [dict(m) for m in messages], "media": [dict(m) for m in media], "completion_media": [dict(m) for m in media if work and str(m["id"]) in work["completion_media_ids"]], "follow_up_flags": due_flags(ticket, assignment, work, appointments, now), "contractors": [{"id": item["id"], "name": item["name"], "trades": ", ".join(item["service_categories"]) or "General maintenance"} for item in recommend_workers(session, org, ticket_id)] if role == "manager" else []})


def board(session, principal, now, view=None, before=None):
    if not any(principal.allows(capability) for capability in ("maintenance.manage", "maintenance.respond", "maintenance.report")):
        problem(403, "FORBIDDEN", "This account does not have access to repair jobs.")
    role = "manager" if principal.allows("maintenance.manage") else "contractor" if principal.allows("maintenance.respond") else "tenant"
    params = {"org": principal.organization_id, "actor": principal.user_id, "manager": role == "manager", "contractor": role == "contractor", "view": view, "priority": int(before.split(":")[0]) if before else None, "before": int(before.split(":")[1]) if before else None}
    rows = session.execute(text("""
        WITH visible AS (
            SELECT t.id,t.ticket_number,CASE WHEN t.status IN ('COMPLETED','CLOSED','CANCELED') THEN 3 WHEN t.emergency THEN 0 WHEN t.urgent_triage THEN 1 ELSE 2 END AS priority_order
            FROM maintenance_tickets t WHERE t.organization_id=:org
            AND (CAST(:view AS text) IS NULL OR (:view='past' AND t.status IN ('COMPLETED','CLOSED','CANCELED')) OR (:view='active' AND t.status NOT IN ('COMPLETED','CLOSED','CANCELED')))
            AND (:manager OR (NOT :contractor AND t.reporter_user_id=:actor) OR (:contractor AND (app_can_claim_maintenance_ticket(t.id) OR EXISTS (SELECT 1 FROM assignments a JOIN contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE a.organization_id=t.organization_id AND a.ticket_id=t.id AND c.user_id=:actor AND a.id=t.active_assignment_id))))
        )
        SELECT * FROM visible WHERE CAST(:priority AS integer) IS NULL OR priority_order>:priority OR (priority_order=:priority AND ticket_number<:before)
        ORDER BY priority_order,ticket_number DESC LIMIT 201
    """), params).mappings().all()
    items = []
    for row in rows[:200]:
        data = detail(session, principal, row["id"], now)
        next_step = next((a for a in data["available_actions"] if a != "message"), "Await the next update")
        if not data["assignment"] and data["ticket"]["status"] in {"INTAKE_OPEN", "TRIAGE_PENDING", "WAITING_TENANT"}:
            next_step = "Stevie is gathering details"
        work = data["work_order"]
        visits = [visit for visit in data["appointments"] if data["assignment"] and visit["assignment_id"] == data["assignment"]["id"] and visit["status"] in {"REQUESTED", "CONFIRMED"} and datetime.fromisoformat(visit["ends_at"]) > now]
        if data["ticket"]["status"] in {"COMPLETED", "CLOSED"}:
            next_step = "reopen"
        elif data["ticket"]["status"] == "CANCELED":
            next_step = "Request canceled"
        elif role == "contractor" and work and not work["started_at"]:
            next_step = "start_work"
        if role == "tenant" and next_step == "availability":
            next_step = "Waiting for the repair proposal"
        items.append({**data["ticket"], "job_status": data["assignment"]["status"] if data["assignment"] else "UNASSIGNED", "next_step": next_step, "due_flags": data["follow_up_flags"]})
    return jsonable_encoder({"role": role, "items": items, "next_cursor": f"{rows[199]['priority_order']}:{rows[199]['ticket_number']}" if len(rows) > 200 else None, "contractors": _contractors(session, principal.organization_id, role)})


def _handoff_recipient(body, last_question):
    normalized = " ".join(body.lower().replace("’", "'").split())
    choice = normalized.strip(" .!?")
    if last_question.startswith("Who should take over?") and re.fullmatch(r"[a-z][a-z .,'-]{0,99}", choice):
        return re.sub(r"[, ]*please$", "", choice).strip()
    for clause in re.split(r"[.!;\n]+", normalized):
        if re.search(r'["“”]|\b(?:maybe|might|perhaps|if|unless|considering|thinking|hoping|should we|should i|not yet|hold off|said|says|suggested)\b', clause):
            continue
        polite = re.match(r"\s*(?:can|could|would) you (?:please )?(?:pass|hand|send|assign|transfer|let|ask|get|have)\b", clause)
        if "?" in clause and not polite or re.search(r"\b(?:could|would)\b", clause) and not polite:
            continue
        if re.search(r"\b(?:don't|do not|can't|cannot|never|won't|will not|shouldn't|should not|not going to|not ready to|haven't|have not)\b|\b(?:is not|isn't|are not|aren't)\s+(?:passing|handing|sending|assigning|transferring|taking|handling)\b|\bnot\s+(?:pass(?:ing)?|hand(?:ing)?|send(?:ing)?|assign(?:ing)?|transfer(?:ring)?|take|taking|handle|handling)\b|\b(?:was|were)\s+(?:going to\s+)?(?:pass(?:ing)?|hand(?:ing)?|send(?:ing)?|assign(?:ing)?|transfer(?:ring)?|take|taking|handle|handling)\b|\bno (?:need|reason) to (?:pass|hand|send|assign|transfer)\b", clause):
            continue
        target = re.search(r"\b(?:pass(?:ing)?|hand(?:ing)?(?: off)?|handoff|turn(?:ing)?|transfer(?:ring)?|send(?:ing)?|assign(?:ing)?)\b(?P<object>.{0,70}?)\b(?:to|onto)\s+(?P<target>.+)", clause)
        lead = clause[:target.start()].strip(" ,:") if target else ""
        committed = re.fullmatch(r"(?:(?:thanks|okay|ok|alright|sure)[, ]+)?(?:please(?: go ahead and)?|stevie(?:[, ]+please)?|let's|let me|i|we|will|i(?:'m| am)(?: going to| ready to)?|i(?:'ll| will)(?: go ahead and)?|we(?:'re| are)(?: going to)?|we(?:'ll| will)|(?:i|we) (?:want|need) to|i(?:'ve| have) decided to|(?:can|could|would) you(?: please)?)?", lead)
        if target and committed and re.fullmatch(r"\s*(?:(?:over|off|on|along)\s+)?(?:(?:the|this|our)\s+)?(?:(?:conversation|communication|chat|request|repair|job|it|this|you)\s*)?(?:(?:over|off|on|along)\s*)?", target["object"]):
            return re.split(r",|\b(?:to take|to handle|to help|from here)\b", target["target"], maxsplit=1)[0].strip(" ?")
        target = re.fullmatch(r"\s*(?:please )?assign (?P<target>[a-z][a-z .'-]{0,99}?) to (?:this|the) (?:repair|request|job)\s*\??", clause)
        if target:
            return target["target"].strip()
        direct = re.sub(r"^\s*(?:can|could|would) you (?:please )?", "", clause) if polite else clause
        direct = re.sub(r"^\s*(?:(?:i(?:'ll| will)|we(?:'ll| will))\s+)?(?:let(?:'s)?(?: have| get)?|have|ask|get)\s+", "", direct)
        target = re.fullmatch(r"\s*(?:(?:i|we) (?:want|need) )?(?P<target>[a-z][a-z .'-]{0,99}?)\s*,?\s+(?:(?:please|should|will|can)\s+)?(?:to\s+)?(?:take (?:over|(?:it|this|the conversation) from here|a look)|handle (?:it|this|the repair|the request)|take care of (?:it|this|the repair|the request))(?:\s+(?:please|now|here))?\s*\??", direct)
        if target:
            return target["target"].strip()
        target = re.fullmatch(r"\s*(?:(?:i think|i believe|it looks like) )?(?:this|it|the repair|the request) (?:needs?|requires?) (?P<target>(?:a|the) (?:repairman|technician))\s*", clause)
        if target:
            return target["target"]
    return None


def execute(session, principal, ticket_id, command, key, now):
    org, actor, action = principal.organization_id, principal.user_id, command["action"]
    scoped_key = request_hash("POST", "workflow-key", {"actor": str(actor), "ticket": str(ticket_id), "action": action, "key": key})
    hashed = request_hash("POST", str(ticket_id), command)
    initial = detail(session, principal, ticket_id, now)
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"), {"scope": f"workflow-rate:{org}:{actor}"})
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"workflow:{org}:{scoped_key}"})
    replay = find_replay(session, org, actor, ticket_id, scoped_key, hashed)
    if replay:
        return replay["body"]
    if initial["role"] == "contractor" and initial["assignment"] is None and initial["ticket"]["status"] in {"INTAKE_OPEN", "TRIAGE_PENDING", "WAITING_TENANT"}:
        problem(409, "TRIAGE_IN_PROGRESS", "Stevie is gathering details from the tenant first.")
    if action in {"message", "accept", "arrange_repair"} and initial["role"] == "contractor" and initial["assignment"] is None:
        if session.execute(text("SELECT * FROM app_claim_maintenance_ticket(:ticket)"), {"ticket": ticket_id}).first() is None:
            problem(409, "ASSIGNMENT_CHANGED", "This repair is no longer available. Refresh your jobs.")
    params = {"org": org, "ticket": ticket_id, "actor": actor, "now": now}
    ticket = session.execute(text("SELECT * FROM maintenance_tickets WHERE organization_id = :org AND id = :ticket FOR UPDATE"), params).mappings().first()
    if ticket is None:
        problem(404, "NOT_FOUND", "Repair request not found.")
    current = detail(session, principal, ticket_id, now)
    if action == "message" and current["role"] == "tenant" and current["ticket"]["status"] in {"COMPLETION_REVIEW", "COMPLETED", "CLOSED"}:
        reported = command["body"]
        named = set(matching_families(reported))
        existing = {item["key"] for item in current["issues"]}
        recurrence = re.search(r"\b(?:broken|leaking|clogged|blocked|stuck|failed|not working|isn't working|isn’t working|came back|returned|happening again)\b", reported, re.IGNORECASE)
        reassured = re.search(r"\?|\b(?:not leaking|not broken|isn't broken|isn’t broken|no longer|no more|stopped leaking|if|maybe|might|said|says|heard|was|were|previously)\b", reported, re.IGNORECASE)
        if recurrence and not reassured and (named or len(existing) == 1):
            action = "reopen"
            command = {**command, "reason": reported}
    if action not in current["available_actions"]:
        problem(409, "WORKFLOW_ACTION_UNAVAILABLE", "This action is unavailable in the current repair stage or for your role.")
    assignment, work, appointments = _records(session, org, ticket_id)
    if current["role"] == "contractor" and action not in {"message", "accept", "decline", "arrange_repair", "start_work", "complete"} and (not assignment or assignment["status"] != "ACCEPTED"):
        problem(409, "ASSIGNMENT_REQUIRED", "Accept your assignment before changing the repair.")
    recent = session.execute(text("SELECT count(*) FROM audit_events WHERE organization_id = :org AND actor_id = :actor AND action LIKE 'maintenance.workflow.%' AND created_at > :now - interval '1 minute'"), params).scalar()
    if recent >= 30:
        problem(429, "RATE_LIMITED", "Please wait a minute before updating this repair again.")
    media_ids = command.get("media_ids", [])
    for media_id in media_ids:
        if not session.execute(text("SELECT 1 FROM media_objects WHERE organization_id = :org AND ticket_id = :ticket AND id = :media AND status = 'READY'"), {**params, "media": media_id}).scalar():
            problem(422, "MEDIA_NOT_READY", "Attach only successfully scanned photos from this request.")
    if action == "complete" and (not media_ids or not session.execute(text("SELECT 1 FROM media_objects WHERE organization_id = :org AND ticket_id = :ticket AND id = ANY(CAST(:media AS uuid[])) AND status = 'READY' AND COALESCE(detected_type,declared_content_type) LIKE 'image/%' LIMIT 1"), {**params, "media": media_ids}).scalar()):
        problem(422, "COMPLETION_PHOTO_REQUIRED", "Attach at least one successfully scanned completion photo.")
    if work and not work["workflow_managed"] and action not in {"message", "availability"}:
        session.execute(text("UPDATE work_orders SET workflow_managed = true WHERE organization_id = :org AND id = :work"), {**params, "work": work["id"]})
    if action == "arrange_repair":
        if assignment["status"] == "PENDING":
            execute(session, principal, ticket_id, {"action": "accept"}, f"{scoped_key}:accept", now)
        execute(session, principal, ticket_id, {"action": "propose_visit", "starts_at": command["starts_at"], "ends_at": command["ends_at"], "timezone": command["timezone"]}, f"{scoped_key}:visit", now)
        session.execute(text("UPDATE assignments SET scope=:scope WHERE organization_id=:org AND id=:assignment"), {**params, "assignment": assignment["id"], "scope": command["scope"]})
        result = detail(session, principal, ticket_id, now)
        write_audit(session, organization_id=org, actor_id=actor, action="maintenance.workflow.arrange_repair", target_type="maintenance_ticket", target_id=ticket_id, target_version=None, request_id=scoped_key, before_state={"status": ticket["status"]}, after_state={"status": result["ticket"]["status"], "command": command})
        store_replay(session, organization_id=org, actor_id=actor, ticket_id=ticket_id, key=scoped_key, hashed=hashed, status=200, body=result)
        return result
    status = ticket["status"]
    if action == "assign":
        if not any(str(profile["id"]) == command["contractor_profile_id"] for profile in _contractors(session, org, "manager")):
            problem(422, "CONTRACTOR_UNAVAILABLE", "Choose an approved professional with an active maintenance account.")
        if ticket["verification"] != "VERIFIED" or not ticket["unit_id"]:
            problem(409, "HOME_UNVERIFIED", "Verify the home before dispatching a repair.")
        result = assign_contractor(session, org, ticket_id, command["contractor_profile_id"], command["scope"], actor)
        session.execute(text("UPDATE work_orders SET workflow_managed = true WHERE organization_id = :org AND id = :work"), {**params, "work": result["work_order_id"]})
        status = "ASSIGNED"
    elif action in {"accept", "decline"}:
        session.execute(text("UPDATE assignments SET status = :status WHERE organization_id = :org AND id = :assignment"), {**params, "assignment": assignment["id"], "status": "ACCEPTED" if action == "accept" else "DECLINED"})
        if action == "decline":
            session.execute(text("UPDATE maintenance_appointments SET status = 'CANCELED' WHERE organization_id = :org AND ticket_id = :ticket AND assignment_id = :assignment AND status IN ('REQUESTED','CONFIRMED')"), {**params, "assignment": assignment["id"]})
            session.execute(text("UPDATE work_orders SET authorization_state = 'NONE',approved_version = NULL,spending_limit_cents = NULL,approved_by = NULL,approved_at = NULL WHERE organization_id = :org AND assignment_id = :assignment"), {**params, "assignment": assignment["id"]})
        status = "SCHEDULING" if action == "accept" else "ASSIGNMENT_PENDING"
    elif action == "availability":
        session.execute(text("UPDATE maintenance_tickets SET availability_windows = CAST(:windows AS jsonb) WHERE organization_id = :org AND id = :ticket"), {**params, "windows": json.dumps(command["windows"])})
    elif action == "propose_visit":
        if ticket["verification"] != "VERIFIED" or datetime.fromisoformat(command["starts_at"].replace("Z", "+00:00")) <= now:
            problem(409, "VISIT_INVALID", "A visit needs a verified home and a future time.")
        session.execute(text("UPDATE maintenance_appointments SET status = 'CANCELED' WHERE organization_id = :org AND ticket_id = :ticket AND status IN ('REQUESTED','CONFIRMED')"), params)
        visit = create_appointment(session, org, ticket_id, command["starts_at"], command["ends_at"], command["timezone"])
        session.execute(text("UPDATE maintenance_appointments SET assignment_id = :assignment,contractor_accepted = true WHERE organization_id = :org AND id = :visit"), {**params, "assignment": assignment["id"], "visit": visit["id"]})
        status = "SCHEDULING"
    elif action == "confirm_visit":
        visit = next((a for a in appointments if str(a["id"]) == command["appointment_id"]), None)
        if not visit or visit["status"] not in {"REQUESTED", "CONFIRMED"} or not visit["contractor_accepted"] or not assignment or assignment["status"] != "ACCEPTED" or visit["assignment_id"] != assignment["id"] or ticket["verification"] != "VERIFIED" or visit["starts_at"] <= now:
            problem(409, "VISIT_INVALID", "Choose a future visit proposed by the assigned professional.")
        granted = command["entry_permission"] == "GRANTED"
        session.execute(text("UPDATE maintenance_appointments SET status = :status,entry_permission = :permission,entry_granted_by = :actor,notice_evidence = :evidence WHERE organization_id = :org AND id = :visit"), {**params, "visit": visit["id"], "status": "CONFIRMED" if granted else "CANCELED", "permission": command["entry_permission"], "evidence": f"Resident {actor} explicitly {'granted' if granted else 'denied'} entry for this visit at {now.isoformat()}"})
        status = "SCHEDULED" if granted else "SCHEDULING"
    elif action == "estimate":
        session.execute(text("UPDATE work_orders SET estimate_cents = :amount,estimate_scope = :scope,estimate_version = estimate_version + 1,authorization_state = 'WAITING_APPROVAL',approved_version = NULL,spending_limit_cents = NULL,approved_by = NULL,approved_at = NULL WHERE organization_id = :org AND id = :work"), {**params, "work": work["id"], "amount": command["estimate_cents"], "scope": command["scope"]})
        status = "WAITING_APPROVAL"
    elif action == "approve_estimate":
        if command["estimate_version"] != work["estimate_version"] or command["spending_limit_cents"] < work["estimate_cents"]:
            problem(409, "ESTIMATE_CHANGED", "Approve the current estimate with a limit covering its amount.")
        session.execute(text("UPDATE work_orders SET authorization_state = 'APPROVED',approved_version = estimate_version,spending_limit_cents = :limit,approved_by = :actor,approved_at = :now WHERE organization_id = :org AND id = :work"), {**params, "work": work["id"], "limit": command["spending_limit_cents"]})
        status = "SCHEDULED" if any(a["status"] == "CONFIRMED" for a in appointments) else "SCHEDULING"
    elif action == "reject_estimate":
        session.execute(text("UPDATE work_orders SET authorization_state = 'REJECTED',approved_version = NULL,spending_limit_cents = NULL,approved_by = NULL,approved_at = NULL WHERE organization_id = :org AND id = :work"), {**params, "work": work["id"]})
        status = "SCHEDULING"
    elif action == "start_work":
        session.execute(text("UPDATE assignments SET status='ACCEPTED' WHERE organization_id=:org AND id=:assignment"), {**params, "assignment": assignment["id"]})
        session.execute(text("UPDATE work_orders SET started_at = :now WHERE organization_id = :org AND id = :work"), {**params, "work": work["id"]})
        status = "IN_PROGRESS"
    elif action == "complete":
        session.execute(text("UPDATE assignments SET status='ACCEPTED' WHERE organization_id=:org AND id=:assignment"), {**params, "assignment": assignment["id"]})
        session.execute(text("UPDATE work_orders SET started_at = COALESCE(started_at,:now),completion_notes = :notes,completion_media_ids = CAST(:media AS jsonb),completed_at = :now WHERE organization_id = :org AND id = :work"), {**params, "work": work["id"], "notes": command["notes"], "media": json.dumps(media_ids)})
        status = "COMPLETION_REVIEW"
    elif action == "confirm_completion":
        if not work or not work["completed_at"]:
            problem(409, "COMPLETION_REQUIRED", "The professional must report completion first.")
        session.execute(text("UPDATE work_orders SET confirmed_at = :now WHERE organization_id = :org AND id = :work"), {**params, "work": work["id"]})
        status = "COMPLETED"
    elif action == "resolve_self":
        if len(current["issues"]) > 1 and not re.search(r"\b(?:all|both|every(?:thing| issue| problem))\b.{0,50}\b(?:fixed|resolved|working)\b", command["reason"], re.IGNORECASE):
            problem(409, "CONFIRM_ALL_ISSUES", "Several problems were reported. Confirm that all issues are fixed, or describe which problem remains in the chat.")
        if re.search(r"\b(?:not|still|isn't|isnt|never)\b", command["reason"], re.IGNORECASE):
            problem(409, "ISSUE_STILL_OPEN", "Your reply indicates a problem may remain. Please describe it in the chat so it stays open.")
        status = "COMPLETED"
    elif action == "reopen":
        session.execute(text("UPDATE maintenance_appointments SET status='CANCELED' WHERE organization_id=:org AND ticket_id=:ticket AND status IN ('REQUESTED','CONFIRMED') AND starts_at>:now"), params)
        session.execute(text("UPDATE maintenance_tickets SET active_assignment_id=NULL,handoff=true,notification_event_id=NULL,notification_status='PENDING' WHERE organization_id=:org AND id=:ticket"), params)
        if ticket["urgent_triage"] or ticket["emergency"]:
            _open_escalation(session, org, ticket_id, actor, now, life_safety=ticket["emergency"])
        status = "ASSIGNMENT_PENDING"
    message = command.get("body") or command.get("reason") or command.get("notes")
    if message:
        session.execute(text("INSERT INTO ticket_messages (id,organization_id,ticket_id,body,author_id,author_role,sender_label,media_ids) VALUES (:id,:org,:ticket,:body,:actor,:role,:label,CAST(:media AS jsonb))"), {**params, "id": uuid4(), "body": message, "role": current["role"], "label": principal.display_name, "media": json.dumps(media_ids)})
    if action == "message" and current["role"] == "manager" and not assignment and ticket["status"] in {"INTAKE_OPEN", "MANAGER_REVIEW", "TRIAGE_PENDING", "WAITING_TENANT"}:
        status = "ASSIGNMENT_PENDING"
        session.execute(text("UPDATE maintenance_tickets SET handoff=true WHERE organization_id=:org AND id=:ticket"), params)
    observations = [item["body"] for item in current["messages"] if item["author_role"] == "tenant"]
    if message and current["role"] == "tenant":
        observations.append(message)
    if action != "decline" and (action != "message" or ticket["status"] not in {"COMPLETED", "CLOSED", "CANCELED"}):
        sync_issues(session, org, ticket_id, tracked_issues(ticket["description"], observations), actor, now)
    if action == "message" and ticket["status"] not in {"COMPLETED", "CLOSED", "CANCELED"}:
        records = apply_chat_updates(session, principal, ticket_id, message, now)
        pending = [item for item in records if item["status"] not in {"TENANT_CONFIRMED", "ASSUMED_RESOLVED"}]
        if pending and all(item["status"] == "WAITING_PARTS" for item in pending):
            status = "WAITING_PARTS"
        if records and not pending and all(item["status"] == "TENANT_CONFIRMED" for item in records) and current["role"] == "tenant" and not ticket["emergency"]:
            status = "COMPLETED"
            if work:
                session.execute(text("UPDATE work_orders SET confirmed_at=:now WHERE organization_id=:org AND id=:work"), {**params, "work": work["id"]})
    acknowledgment = " ".join((message or "").lower().replace("’", "'").split())
    uncertain_acknowledgment = re.search(r"\?|\b(?:not|no|never|cannot|unable|maybe|perhaps|might|if|unless|would|could|think|hope|probably|possibly|was|were|said|says|heard|kidding|joking)\b|\banother (?:job|property|request)\b|\b(?:can|won|don|isn|wasn|wouldn|couldn)'t\b", acknowledgment)
    accepts_responsibility = re.match(
        r"(?:(?:yes|ok|okay|sure|thanks)[,.! ]+)?(?:"
        r"i(?:'m| am) (?:on it|on my way|heading (?:over|there|out)|taking care of (?:it|this)|handling (?:it|this))|"
        r"i(?:'ll| will| can) (?:take (?:care of )?(?:it|this|the (?:repair|request|job))|handle (?:it|this|the (?:repair|request|job))|take a look|look (?:at|into) (?:it|this)|deal with (?:it|this)|get (?:it|this) (?:sorted|handled)|head over|come (?:over|by|out)|stop by|be (?:there|over)|check (?:it|this)(?: out)?)|"
        r"i(?:'ve| have) got (?:it|this)|leave (?:it|this) with me|on it|acknowledged"
        r")(?=$|[\s,.!])", acknowledgment,
    )
    acknowledges_urgent = (ticket["urgent_triage"] or ticket["emergency"]) and (
        action in {"start_work", "complete"} and current["role"] == "contractor"
        or action == "message" and current["role"] in {"manager", "contractor"}
        and accepts_responsibility and not uncertain_acknowledgment
    )
    if action == "message" and assignment and work and not work["started_at"] and ticket["status"] not in {"COMPLETION_REVIEW", "COMPLETED", "CLOSED", "CANCELED"} and not ticket["emergency"]:
        scheduling_reply = None
        if current["role"] == "contractor":
            parsed = parse_chat_visit(message, now, {"text": work["visit_draft"]} if work.get("visit_draft") else None)
            if parsed["offer"]:
                offer = parsed["offer"]
                if assignment["status"] == "PENDING":
                    execute(session, principal, ticket_id, {"action": "accept"}, f"{scoped_key}:chat-accept", now)
                execute(session, principal, ticket_id, {"action": "propose_visit", "starts_at": offer["starts_at"], "ends_at": offer["ends_at"], "timezone": offer["timezone"]}, f"{scoped_key}:chat-visit", now)
                session.execute(text("UPDATE work_orders SET visit_draft=NULL WHERE organization_id=:org AND id=:work"), {**params, "work": work["id"]})
                status = "SCHEDULING"
                scheduling_reply = f"The proposed visit is {offer['displaytext']}. Does that time work for you? Entry permission is still needed."
            elif parsed["question"]:
                session.execute(text("UPDATE work_orders SET visit_draft=:draft WHERE organization_id=:org AND id=:work"), {**params, "work": work["id"], "draft": parsed.get("draft_text", message[:1000])})
                scheduling_reply = parsed["question"]
        elif current["role"] == "tenant":
            visit = next((item for item in appointments if item["assignment_id"] == assignment["id"] and item["status"] == "REQUESTED" and item["starts_at"] > now), None)
            if visit:
                local_start = visit["starts_at"].astimezone(ZoneInfo(visit["timezone"]))
                local_end = visit["ends_at"].astimezone(ZoneInfo(visit["timezone"]))
                visit_label = f"{local_start:%a %b %d, %I:%M %p}–{local_end:%I:%M %p} {visit['timezone']}"
                permission_question = f"Do you give the repairman permission to enter for the visit on {visit_label}? Please reply yes or no."
                last_assistant = next((item for item in reversed(current["messages"]) if item["author_role"] == "system"), None)
                awaiting_permission = bool(last_assistant and last_assistant["body"] == permission_question)
                agrees = re.fullmatch(r"(?:yes|yes please|that works|that works for me|works for me|that time works|confirmed|sounds good|okay|ok)[.!]?", message.strip(), re.IGNORECASE)
                denies = re.search(r"\b(?:do not enter|don't enter|don’t enter|no entry|not allowed to enter)\b", message, re.IGNORECASE) or awaiting_permission and re.fullmatch(r"no[.!]?", message.strip(), re.IGNORECASE)
                explicitly_allows = re.fullmatch(r"(?:yes[,! ]+)?(?:i (?:give|grant) permission to enter|i allow entry|you (?:can|may) enter)(?: for (?:this|the proposed) visit)?[.!]?", message.strip(), re.IGNORECASE)
                conditional = re.search(r"\b(?:not|don't|don’t|cannot|can't|can’t|unless|if|maybe|might)\b|\?", message, re.IGNORECASE)
                grants = not conditional and (explicitly_allows or awaiting_permission and agrees)
                if grants or denies:
                    execute(session, principal, ticket_id, {"action": "confirm_visit", "appointment_id": str(visit["id"]), "entry_permission": "GRANTED" if grants else "DENIED"}, f"{scoped_key}:chat-entry", now)
                    status = "SCHEDULED" if grants else "SCHEDULING"
                    scheduling_reply = f"The visit is confirmed for {visit_label}, with your entry permission recorded." if grants else "Understood. Entry is not authorized for that visit. Please agree on another time here."
                elif agrees:
                    scheduling_reply = permission_question
        if current["role"] == "contractor" and not acknowledges_urgent and not any(item["author_role"] == "contractor" and datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")) >= assignment["created_at"] for item in current["messages"]):
            introduction = f"{principal.display_name} is the repairman helping with this request."
            scheduling_reply = introduction + "\n\n" + scheduling_reply if scheduling_reply else introduction + f" I will hand the communication over to {principal.display_name}."
        if scheduling_reply:
            session.execute(text("INSERT INTO ticket_messages (id,organization_id,ticket_id,body,author_role,sender_label) VALUES (:id,:org,:ticket,:body,'system','Stevie')"), {**params, "id": uuid4(), "body": scheduling_reply})
    urgent_acknowledged = False
    if acknowledges_urgent:
        escalations = session.execute(text("UPDATE escalations SET state='ACKNOWLEDGED',acknowledged_by=:actor,acknowledged_at=:now WHERE organization_id=:org AND ticket_id=:ticket AND state='OPEN' RETURNING id"), params).scalars().all()
        for escalation_id in escalations:
            write_audit(session, organization_id=org, actor_id=actor, action="maintenance.escalation_acknowledged", target_type="escalation", target_id=escalation_id, target_version=None, request_id=scoped_key, before_state={"state": "OPEN"}, after_state={"state": "ACKNOWLEDGED", "ticket_id": str(ticket_id)})
        urgent_acknowledged = bool(escalations)
        if urgent_acknowledged and action == "message" and current["role"] == "contractor" and assignment and assignment["status"] == "PENDING":
            session.execute(text("UPDATE assignments SET status='ACCEPTED' WHERE organization_id=:org AND id=:assignment"), {**params, "assignment": assignment["id"]})
            status = "SCHEDULING"
    outcome_reply = f"{principal.display_name} is handling this urgent request. They’ll share the next update here." if urgent_acknowledged else None
    if action == "message" and current["role"] == "manager" and "assign" in current["available_actions"]:
        last_question = next((item["body"] for item in reversed(current["messages"]) if item["author_role"] == "system"), "")
        recipient = _handoff_recipient(message, last_question)
        if recipient:
            candidates = current["contractors"]
            generic = re.fullmatch(r"(?:(?:the|a|our) )?(?:repairman|technician|repair team|maintenance team)(?: please| now)?", recipient)
            selected = candidates if generic else [worker for worker in candidates if re.fullmatch(re.escape(worker["name"].lower()) + r"(?: please| now)?", recipient)]
            if ticket["verification"] != "VERIFIED":
                outcome_reply = "Please confirm the home before handing this repair to a repairman."
            elif len(selected) == 1:
                handed_off = execute(session, principal, ticket_id, {"action": "assign", "contractor_profile_id": selected[0]["id"], "scope": "\n".join([ticket["description"], *[f"{item['title']}: {item['evidence']}" for item in list_issues(session, org, ticket_id) if item["status"] not in {"TENANT_CONFIRMED", "ASSUMED_RESOLVED"}]])[:5000]}, f"{scoped_key}:chat-handoff", now)
                status = handed_off["ticket"]["status"]
            elif candidates:
                outcome_reply = "Who should take over? Available repairmen: " + ", ".join(worker["name"] for worker in candidates) + ". Reply with a name."
            else:
                outcome_reply = "No eligible repairman is available for this request yet. Check the repair team's account, coverage, and workload before handing it over."
    if action == "assign":
        worker_name = next((worker["name"] for worker in current["contractors"] if worker["id"] == command["contractor_profile_id"]), "the repairman")
        outcome_reply = f"The property manager has asked {worker_name} to help with this repair. They’ll join you here."
    elif action == "reopen":
        outcome_reply = "I’ve reopened this request. The property manager will take another look here."
    elif action == "complete":
        outcome_reply = "Tenant: the repairman reports the work is finished. When it is safe, check normal operation and tell us whether every reported problem is fixed. If something is still broken, name it, and describe what still needs attention. If we don’t hear from you within 24 hours, we’ll mark the request resolved."
    if action == "message" and current["role"] == "tenant" and ticket["status"] == "COMPLETION_REVIEW" and work and work["completed_at"]:
        short_confirmation = re.fullmatch(r"(?:(?:yes[,!. ]+)?(?:confirmed|i (?:can )?confirm|all good|everything (?:is )?(?:good|fine)|all (?:is )?(?:good|fine))|yes)[.!]?(?:[, ]+(?:thanks|thank you)[.!]?)?", message.strip(), re.IGNORECASE) is not None
        affirmative = explicit_resolution(message) or short_confirmation
        all_confirmed = short_confirmation or re.match(r"(?:yes[,!. ]+)?(?:i (?:can )?confirm(?: that)? )?(?:all|both|everything)\b", message.strip(), re.IGNORECASE)

        confirmed_keys = set(matching_families(message))
        existing_keys = {issue["key"] for issue in current["issues"]}
        confirms_this_request = not confirmed_keys or bool(confirmed_keys & existing_keys)
        if status == "COMPLETED" or affirmative and confirms_this_request and (len(current["issues"]) <= 1 or all_confirmed):
            session.execute(text("UPDATE work_orders SET confirmed_at=:now WHERE organization_id=:org AND id=:work"), {**params, "work": work["id"]})
            status = "COMPLETED"
            outcome_reply = "Thanks. Your confirmation that the reported problems are fixed is recorded. If anything returns, describe it here and reopen the request."
        elif affirmative:
            outcome_reply = "Please name the problem that is fixed and any problem that remains. If every reported problem is resolved, say 'All issues are fixed' so we can close the request accurately."
    if action == "message" and current["role"] == "tenant" and status == "COMPLETED" and ticket["status"] not in {"COMPLETED", "CLOSED"} and outcome_reply is None:
        outcome_reply = "Glad to hear everything is working. I’ve marked the reported problems resolved. Let us know if anything comes back."
    if action == "message" and current["role"] == "tenant":
        from grok_bot.domain.maintenance import GAS_GUIDANCE, SAFETY_MESSAGE, _classify, _gas, _mark_emergency

        life_safety, fresh_urgent = _classify(message)
        _, contextual_urgent = _classify(" ".join([ticket["description"], *observations]))
        urgent = fresh_urgent and contextual_urgent
        if life_safety:
            _mark_emergency(session, org, ticket_id, actor, now, safety_context="gas" if _gas(message) else "")
            outcome_reply = GAS_GUIDANCE if _gas(message) else SAFETY_MESSAGE
        elif urgent and not ticket["emergency"] and not ticket["urgent_triage"]:
            session.execute(text("UPDATE maintenance_tickets SET urgent_triage=true WHERE organization_id=:org AND id=:ticket"), params)
            _open_escalation(session, org, ticket_id, actor, now, life_safety=False)
            outcome_reply = "This needs prompt attention from the property manager. Please avoid trying repairs yourself."
        if life_safety or urgent:
            if status in {"COMPLETED", "CLOSED", "CANCELED"}:
                session.execute(text("UPDATE maintenance_appointments SET status='CANCELED' WHERE organization_id=:org AND ticket_id=:ticket AND status IN ('REQUESTED','CONFIRMED') AND starts_at>:now"), params)
                session.execute(text("UPDATE maintenance_tickets SET active_assignment_id=NULL,handoff=true,notification_event_id=NULL,notification_status='PENDING' WHERE organization_id=:org AND id=:ticket"), params)
                sync_issues(session, org, ticket_id, tracked_issues(ticket["description"], observations), actor, now)
                mark_ticket_outcome(session, org, ticket_id, actor, "OPEN", now, message)
                status = "ASSIGNMENT_PENDING"
    if status == "COMPLETED" and (action in {"confirm_completion", "resolve_self"} or action == "message" and current["role"] == "tenant" and ticket["status"] not in {"COMPLETED", "CLOSED"}):
        mark_ticket_outcome(session, org, ticket_id, actor, "TENANT_CONFIRMED", now, message or "Tenant confirmed all reported issues resolved")
    elif action == "complete":
        mark_ticket_outcome(session, org, ticket_id, actor, "RESOLUTION_REPORTED", now, command["notes"])
    elif action == "reopen":
        mark_ticket_outcome(session, org, ticket_id, actor, "OPEN", now, command["reason"])
    if outcome_reply:
        session.execute(text("INSERT INTO ticket_messages (id,organization_id,ticket_id,body,author_role,sender_label,media_ids) VALUES (:id,:org,:ticket,:body,'system','Stevie','[]'::jsonb)"), {**params, "id": uuid4(), "body": outcome_reply})
    session.execute(text("UPDATE maintenance_tickets SET status = :status WHERE organization_id = :org AND id = :ticket"), {**params, "status": status})
    if status != ticket["status"]:
        session.execute(text("INSERT INTO maintenance_status_updates (id,organization_id,ticket_id,status,reason) VALUES (:id,:org,:ticket,:status,:reason)"), {**params, "id": uuid4(), "status": status, "reason": command.get("reason")})
    if action != "decline":
        status = reconcile_ticket(session, org, ticket_id, actor, now)
    write_audit(session, organization_id=org, actor_id=actor, action=f"maintenance.workflow.{action}", target_type="maintenance_ticket", target_id=ticket_id, target_version=None, request_id=scoped_key, before_state={"status": ticket["status"], "work_order": jsonable_encoder(dict(work)) if work else None}, after_state={"status": status, "command": command})
    if action == "decline":
        result = current
        result["available_actions"] = []
        result["ticket"]["status"] = status
        result["assignment"]["status"] = "DECLINED"
        if result["work_order"]:
            result["work_order"].update(authorization_state="NONE", approved_version=None, spending_limit_cents=None, approved_by=None, approved_at=None)
        for visit in result["appointments"]:
            if visit["assignment_id"] == result["assignment"]["id"]:
                visit["status"] = "CANCELED"
    else:
        result = detail(session, principal, ticket_id, now)
    store_replay(session, organization_id=org, actor_id=actor, ticket_id=ticket_id, key=scoped_key, hashed=hashed, status=200, body=result)
    if action == "decline" and not session.execute(text("SELECT app_workflow_release_assignment(:ticket,:assignment)"), {"ticket": ticket_id, "assignment": assignment["id"]}).scalar_one():
        problem(409, "ASSIGNMENT_CHANGED", "The assignment changed before it could be released.")
    return result


def close_unanswered_repairs(session, principal, now):
    if not principal.allows("maintenance.manage"):
        problem(403, "FORBIDDEN", "Maintenance management is required.")
    params = {"org": principal.organization_id, "actor": principal.user_id, "now": now}
    rows = session.execute(text("""
        SELECT t.id,w.id AS work_id,w.completed_at FROM maintenance_tickets t
        JOIN work_orders w ON w.organization_id=t.organization_id AND w.ticket_id=t.id AND w.assignment_id=t.active_assignment_id
        WHERE t.organization_id=:org AND t.status='COMPLETION_REVIEW'
        AND w.id=(SELECT latest.id FROM work_orders latest WHERE latest.organization_id=t.organization_id AND latest.assignment_id=t.active_assignment_id ORDER BY latest.created_at DESC,latest.id DESC LIMIT 1)
        AND w.completed_at<=:now - interval '24 hours'
        AND NOT EXISTS (SELECT 1 FROM ticket_messages m WHERE m.organization_id=t.organization_id AND m.ticket_id=t.id AND m.author_role='tenant' AND m.created_at>=w.completed_at)
        ORDER BY w.completed_at,t.id LIMIT 100 FOR UPDATE OF t SKIP LOCKED
    """), params).mappings().all()
    for row in rows:
        if session.execute(text("SELECT 1 FROM ticket_messages WHERE organization_id=:org AND ticket_id=:ticket AND author_role='tenant' AND created_at>=:completed LIMIT 1"), {"org": principal.organization_id, "ticket": row["id"], "completed": row["completed_at"]}).first():
            continue
        key = request_hash("POST", "maintenance-silence-close", {"ticket": str(row["id"]), "work": str(row["work_id"]), "completed_at": row["completed_at"].isoformat()})
        if idempotency.find_replay(session, principal.organization_id, key, key):
            continue
        record = {**params, "ticket": row["id"]}
        mark_ticket_outcome(session, principal.organization_id, row["id"], principal.user_id, "ASSUMED_RESOLVED", now, "No tenant response for 24 hours after reported completion")
        session.execute(text("UPDATE maintenance_tickets SET status='COMPLETED' WHERE organization_id=:org AND id=:ticket"), record)
        session.execute(text("INSERT INTO maintenance_status_updates (id,organization_id,ticket_id,status,reason) VALUES (:id,:org,:ticket,'COMPLETED','TENANT_SILENCE_24H')"), {**record, "id": uuid4()})
        session.execute(text("INSERT INTO ticket_messages (id,organization_id,ticket_id,body,author_role,sender_label) VALUES (:id,:org,:ticket,:body,'system','Stevie')"), {**record, "id": uuid4(), "body": "We haven’t heard back in 24 hours since the repair was reported finished, so we’re marking it resolved. If something is still wrong, you can reopen the request here."})
        write_audit(session, organization_id=principal.organization_id, actor_id=principal.user_id, action="maintenance.assumed_resolved", target_type="maintenance_ticket", target_id=row["id"], target_version=None, request_id=key, before_state={"status": "COMPLETION_REVIEW"}, after_state={"status": "COMPLETED", "reason": "TENANT_SILENCE_24H", "tenant_confirmed": False, "work_id": str(row["work_id"])})
        idempotency.store_replay(session, organization_id=principal.organization_id, key=key, hashed=key, status=200, body={"status": "COMPLETED", "reason": "TENANT_SILENCE_24H"})


def follow_up_candidates(session, principal, now):
    candidates = []
    labels = {
        "TENANT_REPLY_OVERDUE": "Tenant: is the problem still happening? Tell us what you observed after the suggested check, or ask for a repairman if you prefer. The request stays open until you confirm the outcome.",
        "ASSIGNMENT_RESPONSE_OVERDUE": "The assigned professional has not accepted or declined the repair after 24 hours.",
        "ESTIMATE_APPROVAL_OVERDUE": "The repair estimate has been awaiting manager approval for 48 hours.",
        "COMPLETION_CONFIRMATION_OVERDUE": "Tenant: the repairman reported the work finished. Has normal operation been restored for every reported problem? Please tell us which issue, if any, still needs attention.",
        "VISIT_FOLLOW_UP_REQUIRED": "The confirmed visit window ended without a completion update.",
        "NO_RECENT_PROGRESS": "Repair team: this request needs an update. Please confirm who owns the next action and share progress in this chat; advice, delivery, or a promised visit does not confirm a fix.",
    }
    items = []
    cursor = None
    while True:
        page = board(session, principal, now, view="active", before=cursor)
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    for item in items:
        if not item["due_flags"]:
            continue
        assignment, work, appointments = _records(session, principal.organization_id, item["id"])
        for code in item["due_flags"]:
            anchor = f"{item['status']}:{assignment['id'] if assignment else item['id']}"
            if work:
                anchor += f":{work['id']}:{work['estimate_version']}:{work['updated_at'].isoformat()}"
            if code in {"NO_RECENT_PROGRESS", "TENANT_REPLY_OVERDUE"}:
                latest_message = session.execute(text("SELECT max(created_at) FROM ticket_messages WHERE organization_id = :org AND ticket_id = :ticket AND author_role <> 'system'"), {"org": principal.organization_id, "ticket": item["id"]}).scalar()
                if latest_message:
                    anchor += f":{latest_message.isoformat()}"
                latest_action = session.execute(text("SELECT max(created_at) FROM audit_events WHERE organization_id=:org AND target_id=:ticket AND action LIKE 'maintenance.workflow.%'"), {"org": principal.organization_id, "ticket": item["id"]}).scalar()
                if latest_action:
                    anchor += f":{latest_action.isoformat()}"
            if code == "VISIT_FOLLOW_UP_REQUIRED":
                anchor = str(next(a["id"] for a in appointments if assignment and a["assignment_id"] == assignment["id"] and a["status"] == "CONFIRMED" and a["ends_at"] < now))
            candidates.append({"ticket_id": item["id"], "code": code, "message": labels[code], "anchor": anchor})
    return candidates
