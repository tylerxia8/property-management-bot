import re
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.maintenance import can_view_ticket
from grok_bot.domain.maintenance_guidance import FAMILIES, HVAC_CONTEXT, explicit_resolution, matching_families, tracked_issues
from grok_bot.domain.maintenance_idempotency import find_replay, store_replay
from grok_bot.domain.records import write_audit
from grok_bot.errors import problem


def list_issues(session, org, ticket_id):
    return [dict(row) for row in session.execute(text("SELECT * FROM maintenance_issues WHERE organization_id=:org AND ticket_id=:ticket AND status<>'DISMISSED' ORDER BY created_at,key"), {"org": org, "ticket": ticket_id}).mappings()]


def _change(session, org, ticket_id, issue, status, evidence, actor_id, now, source, note):
    if issue["status"] == status and issue["evidence"] == evidence:
        return
    version = issue["version"] + 1
    params = {"org": org, "ticket": ticket_id, "id": issue["id"], "status": status, "evidence": evidence, "actor": actor_id, "now": now, "version": version}
    session.execute(text("UPDATE maintenance_issues SET status=:status,evidence=:evidence,version=:version,updated_at=:now,confirmed_by=CASE WHEN :status='TENANT_CONFIRMED' THEN CAST(:actor AS uuid) END,confirmed_at=CASE WHEN :status='TENANT_CONFIRMED' THEN CAST(:now AS timestamptz) END WHERE organization_id=:org AND ticket_id=:ticket AND id=:id"), params)
    _event(session, params, issue["status"], source, note)


def _event(session, params, before, source, note):
    event_id = uuid4()
    session.execute(text("INSERT INTO maintenance_issue_events (id,organization_id,ticket_id,issue_id,actor_id,version,before_status,status,source,note,created_at) VALUES (:event,:org,:ticket,:id,:actor,:version,:before,:status,:source,:note,:now)"), {**params, "event": event_id, "before": before, "source": source, "note": note})
    write_audit(session, organization_id=params["org"], actor_id=params["actor"], action="maintenance.issue.changed", target_type="maintenance_ticket", target_id=params["ticket"], target_version=params["version"], request_id=str(event_id), before_state={"status": before}, after_state={"issue_id": str(params["id"]), "status": params["status"], "source": source, "note": note})


def sync_issues(session, org, ticket_id, candidates, actor_id, now):
    session.execute(text("SELECT id FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket FOR UPDATE"), {"org": org, "ticket": ticket_id}).scalar_one()
    existing = {issue["key"]: dict(issue) for issue in session.execute(text("SELECT * FROM maintenance_issues WHERE organization_id=:org AND ticket_id=:ticket FOR UPDATE"), {"org": org, "ticket": ticket_id}).mappings()}
    candidate_keys = {item["key"] for item in candidates}
    for key, issue in existing.items():
        if key in candidate_keys or issue["status"] == "DISMISSED":
            continue
        corrected_keys = set(matching_families(issue["evidence"]))
        contextual_appliance = key == "hvac" and candidate_keys and candidate_keys.issubset({"microwave", "oven", "dishwasher", "fridge", "laundry", "hot_water"}) and not re.search(HVAC_CONTEXT, issue["evidence"], re.I)
        if contextual_appliance or key not in corrected_keys and corrected_keys.intersection(candidate_keys) or (explicit_resolution(issue["evidence"]) or re.search(r"\b(?:works (?:fine|normally|properly)|(?:is|are) (?:fine|okay|ok|working (?:fine|normally|properly)))\s*$", issue["evidence"].strip(), re.I)) and issue["status"] == "OPEN":
            _change(session, org, ticket_id, issue, "DISMISSED", issue["evidence"], actor_id, now, "observation", "Corrected an issue inferred from incidental equipment words rather than a separate reported defect.")
    for candidate in candidates:
        key, evidence = candidate["key"], candidate["evidence"]
        if key not in FAMILIES or not isinstance(evidence, str) or not 0 < len(evidence) <= 5000 or candidate["status"] not in {"open", "reported_resolved"}:
            raise ValueError("Invalid maintenance issue observation")
        status = "RESOLUTION_REPORTED" if candidate["status"] == "reported_resolved" else "OPEN"
        issue = existing.get(key)
        if issue:
            if issue["evidence"] != evidence or issue["status"] == "DISMISSED":
                _change(session, org, ticket_id, issue, status, evidence, actor_id, now, "observation", evidence)
            continue
        params = {"id": uuid4(), "org": org, "ticket": ticket_id, "key": key, "title": FAMILIES[key][1], "status": status, "evidence": evidence, "actor": actor_id, "now": now, "version": 1}
        session.execute(text("INSERT INTO maintenance_issues (id,organization_id,ticket_id,key,title,status,evidence,created_at,updated_at) VALUES (:id,:org,:ticket,:key,:title,:status,:evidence,:now,:now)"), params)
        _event(session, params, None, "observation", evidence)
        existing[key] = {**params, "version": 1}
    return list_issues(session, org, ticket_id)


def mark_ticket_outcome(session, org, ticket_id, actor_id, status, now, note):
    if status not in {"OPEN", "RESOLUTION_REPORTED", "TENANT_CONFIRMED", "ASSUMED_RESOLVED"} or not isinstance(note, str) or len(note) > 5000:
        raise ValueError("Invalid maintenance issue outcome")
    ticket = session.execute(text("SELECT reporter_user_id FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket FOR UPDATE"), {"org": org, "ticket": ticket_id}).mappings().one()
    if status == "TENANT_CONFIRMED" and (actor_id is None or actor_id != ticket["reporter_user_id"]):
        problem(403, "FORBIDDEN", "Only the reporting resident can confirm resolution.")
    named = set(matching_families(note)) if status == "OPEN" else set()
    existing = list_issues(session, org, ticket_id)
    scope = named & {item["key"] for item in existing}
    for issue in existing:
        if status == "OPEN" and scope and issue["key"] not in scope:
            continue
        if status == "OPEN" or issue["status"] not in {"TENANT_CONFIRMED", "ASSUMED_RESOLVED"}:
            _change(session, org, ticket_id, issue, status, issue["evidence"], actor_id, now, "ticket_outcome", note)
    return list_issues(session, org, ticket_id)


def apply_chat_updates(session, principal, ticket_id, body, now):
    org, actor = principal.organization_id, principal.user_id
    role = can_view_ticket(session, org, ticket_id, actor, principal.roles)
    if role not in {"tenant", "contractor"}:
        return list_issues(session, org, ticket_id)
    ticket = session.execute(text("SELECT reporter_user_id,active_assignment_id FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket FOR UPDATE"), {"org": org, "ticket": ticket_id}).mappings().one()
    if role == "tenant" and ticket["reporter_user_id"] != actor:
        return list_issues(session, org, ticket_id)
    if role == "contractor" and not session.scalar(text("SELECT 1 FROM assignments a JOIN contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE a.organization_id=:org AND a.id=:assignment AND c.user_id=:actor AND a.status IN ('PENDING','ACCEPTED')"), {"org": org, "assignment": ticket["active_assignment_id"], "actor": actor}):
        return list_issues(session, org, ticket_id)
    issues = list_issues(session, org, ticket_id)
    clauses = re.split(r"[.!?;\n]+|\bbut\b", body, flags=re.IGNORECASE)
    unresolved_pattern = r"\b(?:still broken|still leaking|not working|isn't working|isn’t working|leaking again|came back|returned|happening again|broken|failed|clogged|blocked|stuck)\b"
    unresolved_keys = set()
    if not re.search(r"\?|\b(?:no longer|not broken|if|maybe|might|said|says|heard)\b", body, re.IGNORECASE):
        for clause in clauses:
            if re.search(unresolved_pattern, clause, re.IGNORECASE):
                unresolved_keys.update(matching_families(clause) or [item["key"] for item in issues])
    for clause in clauses:
        named = set(matching_families(clause))
        confirmed = explicit_resolution(clause) and "?" not in body
        global_confirmation = confirmed and re.match(r"(?:yes[,!. ]+)?(?:i (?:can )?confirm(?: that)? )?(?:all|both|everything)\b", clause.strip(), re.IGNORECASE)
        waiting = role == "contractor" and re.search(r"\b(?:waiting (?:for|on)|need to order|ordered)\b.{0,60}\b(?:parts?|replacement)\b", clause, re.IGNORECASE)
        unresolved = re.search(unresolved_pattern, clause, re.IGNORECASE) and bool(unresolved_keys)
        for issue in issues:
            if issue["key"] not in named and not global_confirmation and not (not named and len(issues) == 1):
                continue
            status = "OPEN" if unresolved or confirmed and issue["key"] in unresolved_keys else "TENANT_CONFIRMED" if confirmed and role == "tenant" else "RESOLUTION_REPORTED" if confirmed else "WAITING_PARTS" if waiting else None
            if status and issue["status"] != status and not (issue["status"] == "TENANT_CONFIRMED" and role == "contractor"):
                _change(session, org, ticket_id, issue, status, issue["evidence"], actor, now, "update", clause.strip()[:5000])
                issue["status"] = status
                issue["version"] += 1
    return list_issues(session, org, ticket_id)


def backfill_issues(session, org, actor, now):
    tickets = session.execute(text("SELECT t.id,t.description FROM maintenance_tickets t WHERE t.organization_id=:org AND t.status NOT IN ('COMPLETED','CLOSED','CANCELED') AND NOT EXISTS (SELECT 1 FROM maintenance_issues i WHERE i.organization_id=t.organization_id AND i.ticket_id=t.id) ORDER BY t.created_at,t.id LIMIT 50 FOR UPDATE OF t SKIP LOCKED"), {"org": org}).mappings().all()
    for ticket in tickets:
        messages = session.scalars(text("SELECT body FROM ticket_messages WHERE organization_id=:org AND ticket_id=:ticket AND author_role='tenant' ORDER BY created_at,id"), {"org": org, "ticket": ticket["id"]}).all()
        sync_issues(session, org, ticket["id"], tracked_issues(ticket["description"], messages), actor, now)


def reconcile_ticket(session, org, ticket_id, actor, now):
    params = {"org": org, "ticket": ticket_id, "actor": actor, "now": now}
    ticket = session.execute(text("SELECT status,emergency,reporter_user_id,active_assignment_id FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket FOR UPDATE"), params).mappings().one()
    status = ticket["status"]
    if status in {"COMPLETED", "CLOSED", "CANCELED"}:
        return status
    issues = list_issues(session, org, ticket_id)
    pending = [item for item in issues if item["status"] not in {"TENANT_CONFIRMED", "ASSUMED_RESOLVED"}]
    if issues and all(item["status"] == "TENANT_CONFIRMED" for item in issues) and actor == ticket["reporter_user_id"] and not ticket["emergency"]:
        status = "COMPLETED"
        session.execute(text("UPDATE work_orders SET confirmed_at=:now WHERE organization_id=:org AND ticket_id=:ticket AND assignment_id=:assignment"), {**params, "assignment": ticket["active_assignment_id"]})
    elif pending and (all(item["status"] == "WAITING_PARTS" for item in pending) or status == "COMPLETION_REVIEW" and any(item["status"] in {"OPEN", "WAITING_PARTS"} for item in pending)):
        status = "WAITING_PARTS" if any(item["status"] == "WAITING_PARTS" for item in pending) else "IN_PROGRESS"
        session.execute(text("UPDATE work_orders SET completed_at=NULL,confirmed_at=NULL,completion_notes=NULL,completion_media_ids='[]'::jsonb WHERE organization_id=:org AND ticket_id=:ticket AND assignment_id=:assignment AND completed_at IS NOT NULL"), {**params, "assignment": ticket["active_assignment_id"]})
    if status != ticket["status"]:
        session.execute(text("UPDATE maintenance_tickets SET status=:status WHERE organization_id=:org AND id=:ticket"), {**params, "status": status})
        session.execute(text("INSERT INTO maintenance_status_updates(id,organization_id,ticket_id,status,reason) VALUES(:id,:org,:ticket,:status,'ISSUE_STATUS_CHANGED')"), {**params, "id": uuid4(), "status": status})
        write_audit(session, organization_id=org, actor_id=actor, action="maintenance.issue_lifecycle", target_type="maintenance_ticket", target_id=ticket_id, target_version=None, request_id=str(uuid4()), before_state={"status": ticket["status"]}, after_state={"status": status})
    return status


def detail(session, principal, ticket_id):
    if can_view_ticket(session, principal.organization_id, ticket_id, principal.user_id, principal.roles) is None:
        problem(404, "NOT_FOUND", "Repair request not found.")
    events = session.execute(text("SELECT * FROM maintenance_issue_events WHERE organization_id=:org AND ticket_id=:ticket ORDER BY created_at,issue_id,version"), {"org": principal.organization_id, "ticket": ticket_id}).mappings()
    return jsonable_encoder({"items": list_issues(session, principal.organization_id, ticket_id), "events": [dict(event) for event in events]})


def update(session, principal, ticket_id, issue_id, command, key, now):
    org, actor = principal.organization_id, principal.user_id
    role = can_view_ticket(session, org, ticket_id, actor, principal.roles)
    if role is None:
        problem(404, "NOT_FOUND", "Repair request not found.")
    scoped = request_hash("POST", "issue-key", {"actor": str(actor), "ticket": str(ticket_id), "key": key})
    hashed = request_hash("POST", str(issue_id), command)
    params = {"org": org, "ticket": ticket_id, "actor": actor, "now": now}
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"), {"scope": f"issue-rate:{org}:{actor}"})
    replay = find_replay(session, org, actor, ticket_id, scoped, hashed)
    if replay:
        return replay["body"]
    session.execute(text("SELECT id FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket FOR UPDATE"), params).scalar_one()
    ticket_status = session.scalar(text("SELECT status FROM maintenance_tickets WHERE organization_id=:org AND id=:ticket"), params)
    if ticket_status in {"COMPLETED", "CLOSED", "CANCELED"}:
        problem(409, "REQUEST_CLOSED", "Reopen the request in the conversation before changing its issues.")
    if role == "contractor" and not session.scalar(text("SELECT 1 FROM maintenance_tickets t JOIN assignments a ON a.organization_id=t.organization_id AND a.id=t.active_assignment_id JOIN contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE t.organization_id=:org AND t.id=:ticket AND c.user_id=:actor AND a.status IN ('PENDING','ACCEPTED')"), params):
        problem(403, "FORBIDDEN", "Only the currently assigned professional can update an issue.")
    allowed = {"OPEN", "TENANT_CONFIRMED"} if role == "tenant" else {"OPEN", "WAITING_PARTS", "RESOLUTION_REPORTED"}
    if command["status"] not in allowed:
        problem(403, "FORBIDDEN", "This account cannot set that issue status.")
    if role == "manager" and not command.get("note"):
        problem(422, "REASON_REQUIRED", "Include a reason for the issue update.")
    recent = session.scalar(text("SELECT count(*) FROM maintenance_issue_events WHERE organization_id=:org AND actor_id=:actor AND created_at>:now - interval '1 minute'"), params)
    if recent >= 30:
        problem(429, "RATE_LIMITED", "Please wait a minute before updating issues again.")
    issue = next((row for row in list_issues(session, org, ticket_id) if row["id"] == issue_id), None)
    if issue is None:
        problem(404, "NOT_FOUND", "Maintenance issue not found.")
    if issue["version"] != command["version"]:
        problem(409, "VERSION_CONFLICT", "This issue changed. Refresh before updating it.")
    _change(session, org, ticket_id, issue, command["status"], issue["evidence"], actor, now, "update", command.get("note") or "")
    reconcile_ticket(session, org, ticket_id, actor, now)
    result = detail(session, principal, ticket_id)
    store_replay(session, organization_id=org, actor_id=actor, ticket_id=ticket_id, key=scoped, hashed=hashed, status=200, body=result)
    return result
