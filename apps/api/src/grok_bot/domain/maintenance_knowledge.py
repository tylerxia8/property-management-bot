import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.deps import require_capability
from grok_bot.auth.permissions import Principal
from grok_bot.domain import idempotency
from grok_bot.domain.records import write_audit
from grok_bot.domain.maintenance_guidance import FAMILIES
from grok_bot.errors import problem

APPROVED_INSTRUCTIONS = (
    "Observe the appliance display from a safe distance and report any visible error message. Do not open covers or touch damaged equipment.",
    "Read the thermostat display and report its current mode and temperature. Use only its normal external controls if there is no sign of damage, heat, smoke, or leaking water.",
    "Observe whether nearby fixtures are affected and report what you see. Do not dismantle fixtures or attempt repairs.",
    "Photograph the visible model label only if it is accessible without moving equipment, climbing, or removing covers.",
    "Report the location and symptoms to the property manager. Leave the equipment untouched until a qualified technician responds.",
)


def listing(session: Session, principal: Principal) -> dict:
    require_capability(principal, "maintenance.manage")
    params = {"org": principal.organization_id}
    entries = session.execute(text("SELECT id,property_id,title,problem_key,model,part_details,instructions,reference_media_ids,verified,verified_at,verified_by,version,active,created_at,updated_at FROM maintenance_knowledge WHERE organization_id=:org ORDER BY title,id"), params).mappings().all()
    properties = session.execute(text("SELECT id,name FROM properties WHERE organization_id=:org ORDER BY name,id"), params).mappings().all()
    reference_media = session.execute(text("SELECT m.id,u.property_id,m.detected_type AS content_type,m.created_at FROM media_objects m JOIN maintenance_tickets t ON t.organization_id=m.organization_id AND t.id=m.ticket_id JOIN units u ON u.organization_id=t.organization_id AND u.id=t.unit_id JOIN properties p ON p.organization_id=u.organization_id AND p.id=u.property_id WHERE m.organization_id=:org AND m.status='READY' AND m.detected_type IN ('image/jpeg','image/png','image/heic','image/heif') AND m.derivative_key IS NOT NULL ORDER BY m.created_at DESC,m.id"), params).mappings().all()
    return {"entries": [dict(row) for row in entries], "properties": [dict(row) for row in properties], "reference_media": [dict(row) for row in reference_media], "approved_instructions": list(APPROVED_INSTRUCTIONS), "problem_keys": list(FAMILIES)}


def save(session: Session, principal: Principal, entry_id: UUID | None, body: dict, key: str, now: datetime) -> dict:
    require_capability(principal, "maintenance.manage")
    org = principal.organization_id
    actor = principal.user_id
    scoped_key = "maintenance-knowledge:" + hashlib.sha256(f"{actor}:{key}".encode()).hexdigest()
    hashed = idempotency.request_hash("PATCH" if entry_id else "POST", f"/maintenance-knowledge/{entry_id or ''}", body)
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": f"{org}:{scoped_key}"})
    replay = idempotency.find_replay(session, org, scoped_key, hashed)
    if replay:
        return replay["body"]
    recent = session.scalar(text("SELECT count(*) FROM audit_events WHERE organization_id=:org AND actor_id=:actor AND action='maintenance.knowledge.saved' AND created_at>:now-interval '1 minute'"), {"org": org, "actor": actor, "now": now})
    if recent >= 30:
        problem(429, "RATE_LIMITED", "Wait before updating more maintenance knowledge.")
    before = None
    if entry_id:
        current = session.execute(text("SELECT * FROM maintenance_knowledge WHERE organization_id=:org AND id=:id FOR UPDATE"), {"org": org, "id": entry_id}).mappings().first()
        if current is None:
            problem(404, "NOT_FOUND", "Maintenance knowledge was not found.")
        if current["version"] != body["version"]:
            problem(409, "VERSION_CONFLICT", "Maintenance knowledge has changed. Reload before editing.")
        before = dict(current)
        values = {**before, **body, "version": current["version"] + 1}
        changed = any(name in body and body[name] != current[name] for name in ("title", "problem_key", "model", "part_details", "instructions"))
        if "reference_media_ids" in body and body["reference_media_ids"] != [str(value) for value in current["reference_media_ids"]]:
            changed = True
        values["verified"] = body.get("verified", False if changed else current["verified"])
    else:
        exists = session.scalar(text("SELECT id FROM properties WHERE organization_id=:org AND id=:id"), {"org": org, "id": body["property_id"]})
        if exists is None:
            problem(404, "NOT_FOUND", "Property was not found.")
        values = {**body, "id": uuid4(), "version": 1, "active": True, "created_at": now}
    references = values["reference_media_ids"]
    if references:
        available = session.execute(text("SELECT m.id FROM media_objects m JOIN maintenance_tickets t ON t.organization_id=m.organization_id AND t.id=m.ticket_id JOIN units u ON u.organization_id=t.organization_id AND u.id=t.unit_id WHERE m.organization_id=:org AND u.property_id=:property AND m.id=ANY(CAST(:ids AS uuid[])) AND m.status='READY' AND m.detected_type IN ('image/jpeg','image/png','image/heic','image/heif') AND m.derivative_key IS NOT NULL FOR SHARE OF m"), {"org": org, "property": values["property_id"], "ids": references}).scalars().all()
        if len(available) != len(references):
            problem(422, "INVALID_REFERENCE_MEDIA", "Choose ready image references from this property's maintenance requests.")
    values.update(organization_id=org, updated_at=now)
    values["verified_at"] = now if values["verified"] and (before is None or "verified" in body) else before["verified_at"] if values["verified"] else None
    values["verified_by"] = actor if values["verified"] and (before is None or "verified" in body) else before["verified_by"] if values["verified"] else None
    if entry_id:
        session.execute(text("UPDATE maintenance_knowledge SET title=:title,problem_key=:problem_key,model=:model,part_details=:part_details,instructions=:instructions,reference_media_ids=CAST(:reference_media_ids AS uuid[]),verified=:verified,verified_at=:verified_at,verified_by=:verified_by,version=:version,active=:active,updated_at=:updated_at WHERE organization_id=:organization_id AND id=:id"), values)
    else:
        session.execute(text("INSERT INTO maintenance_knowledge(id,organization_id,property_id,title,problem_key,model,part_details,instructions,reference_media_ids,verified,verified_at,verified_by,version,active,created_at,updated_at) VALUES(:id,:organization_id,:property_id,:title,:problem_key,:model,:part_details,:instructions,CAST(:reference_media_ids AS uuid[]),:verified,:verified_at,:verified_by,:version,:active,:created_at,:updated_at)"), values)
    result = jsonable_encoder({name: value for name, value in values.items() if name != "organization_id"})
    write_audit(session, organization_id=org, actor_id=actor, action="maintenance.knowledge.saved", target_type="maintenance_knowledge", target_id=values["id"], target_version=values["version"], request_id=scoped_key, before_state=jsonable_encoder(before), after_state=result)
    idempotency.store_replay(session, organization_id=org, key=scoped_key, hashed=hashed, status=200, body=result)
    return result


def verified_for_ticket(session: Session, organization_id: UUID, ticket_id: UUID, problem_keys: list[str]) -> list[dict]:
    rows = session.execute(text("SELECT k.* FROM app_verified_maintenance_knowledge(:ticket,CAST(:keys AS text[])) k WHERE NULLIF(current_setting('app.organization_id',true),'')::uuid=:org"), {"org": organization_id, "ticket": ticket_id, "keys": problem_keys}).mappings().all()
    return [dict(row) for row in rows]
