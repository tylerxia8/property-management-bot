import hashlib
import logging
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlsplit
import time
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, require_capability, require_idempotency_key
from grok_bot.api.success import ERROR_RESPONSES
from grok_bot.auth.permissions import Principal
from grok_bot.auth.tokens import TokenError, _sign, verify_token
from grok_bot.db import set_tenant
from grok_bot.domain import idempotency
from grok_bot.domain.maintenance import _classify, _create_ticket
from grok_bot.domain.records import write_audit
from grok_bot.errors import problem

logger = logging.getLogger(__name__)
router = APIRouter(responses=ERROR_RESPONSES)
_attempts = defaultdict(deque)
_attempts_lock = Lock()


class BridgeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConnectionBody(BridgeBody):
    source: Literal["guest_recovery", "cleaner_scheduler"]


class ConnectionOut(BaseModel):
    token: str
    expires_at: datetime
    organization_id: UUID
    source: str
    mode: Literal["demo", "workspace"]


class PropertyLinkBody(BridgeBody):
    external_property_id: UUID
    unit_id: UUID


class UnlinkBody(BridgeBody):
    external_property_id: UUID


class UnlinkOut(BaseModel):
    removed: bool


class PropertyLinkOut(PropertyLinkBody):
    name: str
    label: str


class BridgeOut(BaseModel):
    organization_id: UUID
    source: str
    expires_at: datetime
    mode: Literal["demo", "workspace"]
    properties: list[PropertyLinkOut]


class ImportBody(BridgeBody):
    issue_id: str = Field(min_length=1, max_length=200)
    external_property_id: UUID
    reservation_id: str = Field(min_length=1, max_length=200)
    conversation_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class RepairOut(BaseModel):
    ticket_id: UUID
    ticket_number: int
    status: str
    priority: str
    updated_at: datetime


class SourceRepairOut(RepairOut):
    issue_id: str
    source_fingerprint: str


class PropertyRepairsOut(BaseModel):
    external_property_id: UUID
    repairs: list[RepairOut]
    has_more: bool


class WorkspaceAppBody(BridgeBody):
    project: Literal["guest_recovery", "cleaner_scheduler"]
    url: str = Field(min_length=1, max_length=500)

    @field_validator("url")
    @classmethod
    def valid_origin(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.port not in {None, 443}:
            raise ValueError("Use the app's HTTPS origin without a path, credentials, or query.")
        return value.rstrip("/")


class WorkspaceOut(BaseModel):
    mode: Literal["demo", "workspace"]
    properties: list[PropertyLinkOut]
    units: list[dict[str, str]]
    apps: list[WorkspaceAppBody]


def bridge_principal(request: Request, session: Session = Depends(get_session, scope="function")) -> Principal:
    with _attempts_lock:
        now = time.monotonic()
        for host in list(_attempts):
            while _attempts[host] and _attempts[host][0] <= now - 60:
                _attempts[host].popleft()
            if not _attempts[host]:
                del _attempts[host]
        host = request.client.host if request.client else "unknown"
        if len(_attempts) >= 4096 and host not in _attempts or len(_attempts[host]) >= 120:
            problem(429, "RATE_LIMITED", "Wait before making more maintenance connection requests.")
        _attempts[host].append(now)
    raw = request.headers.get("authorization", "")
    if not raw.startswith("Bearer "):
        problem(401, "UNAUTHENTICATED", "A maintenance connection token is required.")
    settings = request.app.state.settings
    try:
        payload = verify_token(raw[7:], settings.session_secret)
        if payload.get("amr") != "maintenance_bridge" or payload.get("env") != settings.app_env or payload.get("source") not in {"guest_recovery", "cleaner_scheduler"}:
            raise ValueError()
        org, actor = UUID(payload["org"]), UUID(payload["sub"])
    except (TokenError, ValueError, TypeError, KeyError, OverflowError, AttributeError):
        problem(401, "UNAUTHENTICATED", "The maintenance connection is invalid or expired.")
    set_tenant(session, org, actor)
    if not session.scalar(text("SELECT public.app_actor_is_manager()")):
        problem(403, "FORBIDDEN", "The maintenance connection's manager no longer has access.")
    logger.info("maintenance_bridge_authenticated", extra={"organization_id": str(org), "source": payload["source"], "request_id": getattr(request.state, "request_id", "")})
    request.state.maintenance_connection = payload
    return Principal(user_id=actor, organization_id=org, display_name="Connected workspace", roles=("property_manager",), auth_method="maintenance_bridge")


def mutate(session, principal, key, action, payload, change):
    org = principal.organization_id
    scoped = "maintenance-bridge:" + hashlib.sha256(f"{principal.user_id}:{key}".encode()).hexdigest()
    hashed = idempotency.request_hash("POST", action, payload)
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"), {"scope": f"maintenance-bridge:{org}"})
    replay = idempotency.find_replay(session, org, scoped, hashed)
    if replay:
        return replay["body"]
    if session.scalar(text("SELECT count(*) FROM audit_events WHERE organization_id=:org AND actor_id=:actor AND action LIKE 'maintenance.bridge.%' AND created_at>clock_timestamp()-interval '1 minute'"), {"org": org, "actor": principal.user_id}) >= 30:
        problem(429, "RATE_LIMITED", "Wait before making more maintenance connection changes.")
    result = change()
    write_audit(session, organization_id=org, actor_id=principal.user_id, action="maintenance.bridge." + action, target_type="organization", target_id=org, target_version=None, request_id=str(uuid4()), before_state=None, after_state={"action": action})
    idempotency.store_replay(session, organization_id=org, key=scoped, hashed=hashed, status=200, body=result)
    return result


def linked_properties(session, org):
    return [dict(row) for row in session.execute(text("SELECT l.external_property_id,l.unit_id,p.name,u.label FROM maintenance_property_links l JOIN units u ON u.organization_id=l.organization_id AND u.id=l.unit_id JOIN properties p ON p.organization_id=u.organization_id AND p.id=u.property_id WHERE l.organization_id=:org ORDER BY p.name,u.label"), {"org": org}).mappings()]


@router.get("/maintenance-workspace", response_model=WorkspaceOut)
def workspace(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    return {"mode": "demo" if request.app.state.settings.allows_demo_session else "workspace", "properties": linked_properties(session, principal.organization_id), "apps": [dict(row) for row in session.execute(text("SELECT project,url FROM maintenance_workspace_apps WHERE organization_id=:org ORDER BY project"), {"org": principal.organization_id}).mappings()], "units": [dict(row) for row in session.execute(text("SELECT u.id::text AS id,p.name,u.label FROM units u JOIN properties p ON p.organization_id=u.organization_id AND p.id=u.property_id WHERE u.organization_id=:org ORDER BY p.name,u.label"), {"org": principal.organization_id}).mappings()]}


@router.post("/maintenance-workspace/apps", response_model=WorkspaceAppBody)
def workspace_app(body: WorkspaceAppBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "maintenance.manage")
    def save():
        session.execute(text("INSERT INTO maintenance_workspace_apps(organization_id,project,url) VALUES(:org,:project,:url) ON CONFLICT (organization_id,project) DO UPDATE SET url=EXCLUDED.url"), {"org": principal.organization_id, **body.model_dump()})
        return body.model_dump()
    return mutate(session, principal, require_idempotency_key(key), "workspace_app", body.model_dump(), save)


@router.post("/maintenance-connections", response_model=ConnectionOut)
def connection(body: ConnectionBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "maintenance.manage")
    def create():
        expires = int(time.time()) + 86400
        token = _sign({"amr": "maintenance_bridge", "env": request.app.state.settings.app_env, "org": str(principal.organization_id), "sub": str(principal.user_id), "source": body.source, "exp": expires, "v": 1}, request.app.state.settings.session_secret)
        return {"token": token, "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(), "organization_id": str(principal.organization_id), "source": body.source, "mode": "demo" if request.app.state.settings.allows_demo_session else "workspace"}
    return mutate(session, principal, require_idempotency_key(key), "connection", body.model_dump(mode="json"), create)


@router.post("/maintenance-property-links", response_model=PropertyLinkOut)
def link_property(body: PropertyLinkBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "maintenance.manage")
    def create():
        existing = session.execute(text("SELECT external_property_id,unit_id FROM maintenance_property_links WHERE organization_id=:org AND (external_property_id=:external OR unit_id=:unit) FOR UPDATE"), {"org": principal.organization_id, "external": body.external_property_id, "unit": body.unit_id}).mappings().first()
        if existing and (existing["external_property_id"] != body.external_property_id or existing["unit_id"] != body.unit_id):
            problem(409, "PROPERTY_MAPPING_CONFLICT", "This property or unit is already linked. Review the existing mapping.")
        unit = session.execute(text("SELECT p.name,u.label FROM units u JOIN properties p ON p.organization_id=u.organization_id AND p.id=u.property_id WHERE u.organization_id=:org AND u.id=:unit"), {"org": principal.organization_id, "unit": body.unit_id}).mappings().first()
        if unit is None:
            problem(404, "NOT_FOUND", "The maintenance home was not found.")
        session.execute(text("INSERT INTO maintenance_property_links(organization_id,external_property_id,unit_id) VALUES(:org,:external,:unit) ON CONFLICT DO NOTHING"), {"org": principal.organization_id, "external": body.external_property_id, "unit": body.unit_id})
        return {**body.model_dump(mode="json"), **dict(unit)}
    return mutate(session, principal, require_idempotency_key(key), "property_link", body.model_dump(mode="json"), create)


@router.post("/maintenance-property-links/unlink", response_model=UnlinkOut)
def unlink_property(body: UnlinkBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "maintenance.manage")
    def remove():
        params = {"org": principal.organization_id, "external": body.external_property_id}
        if session.scalar(text("SELECT 1 FROM maintenance_source_requests WHERE organization_id=:org AND external_property_id=:external LIMIT 1"), params):
            problem(409, "PROPERTY_IN_USE", "This mapping has imported repairs and cannot be removed.")
        removed = session.execute(text("DELETE FROM maintenance_property_links WHERE organization_id=:org AND external_property_id=:external RETURNING external_property_id"), params).scalar()
        return {"removed": removed is not None}
    return mutate(session, principal, require_idempotency_key(key), "property_unlink", body.model_dump(mode="json"), remove)


@router.get("/maintenance-bridge", response_model=BridgeOut)
def bridge(request: Request, principal: Principal = Depends(bridge_principal), session: Session = Depends(get_session, scope="function")):
    payload = request.state.maintenance_connection
    return {"organization_id": principal.organization_id, "source": payload["source"], "expires_at": datetime.fromtimestamp(payload["exp"], timezone.utc), "mode": "demo" if request.app.state.settings.allows_demo_session else "workspace", "properties": linked_properties(session, principal.organization_id)}


def source_repair(session, org, issue_id):
    row = session.execute(text("SELECT r.issue_id,r.source_fingerprint,t.id AS ticket_id,t.ticket_number,t.status,CASE WHEN t.emergency THEN 'EMERGENCY' WHEN t.urgent_triage THEN 'URGENT' ELSE 'ROUTINE' END AS priority,t.updated_at FROM maintenance_source_requests r JOIN maintenance_tickets t ON t.organization_id=r.organization_id AND t.id=r.ticket_id WHERE r.organization_id=:org AND r.source='guest_recovery' AND r.issue_id=:issue"), {"org": org, "issue": issue_id}).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "This guest issue has not been opened in maintenance.")
    return SourceRepairOut.model_validate(dict(row)).model_dump(mode="json")


@router.post("/maintenance-bridge/requests", response_model=SourceRepairOut)
def import_request(body: ImportBody, request: Request, principal: Principal = Depends(bridge_principal), session: Session = Depends(get_session, scope="function"), key: str | None = Header(default=None, alias="Idempotency-Key")):
    if request.state.maintenance_connection["source"] != "guest_recovery":
        problem(403, "FORBIDDEN", "Only Guest Recovery can hand off guest requests.")
    if request.app.state.settings.allows_demo_session:
        problem(409, "DEMO_WORKSPACE", "Connect a maintenance workspace with real accounts and homes before importing guest issues.")
    def create():
        existing = session.scalar(text("SELECT ticket_id FROM maintenance_source_requests WHERE organization_id=:org AND source='guest_recovery' AND issue_id=:issue"), {"org": principal.organization_id, "issue": body.issue_id})
        if existing:
            return source_repair(session, principal.organization_id, body.issue_id)
        unit = session.scalar(text("SELECT unit_id FROM maintenance_property_links WHERE organization_id=:org AND external_property_id=:external"), {"org": principal.organization_id, "external": body.external_property_id})
        if unit is None:
            problem(409, "PROPERTY_NOT_LINKED", "Link this Hospitable property to its maintenance home first.")
        if _classify(body.description)[0]:
            problem(409, "SAFETY_REVIEW_REQUIRED", "Keep this hazard in the existing safety workflow; do not create duplicate safety responses.")
        now = request.app.state.clock.now()
        ticket = _create_ticket(session, principal.organization_id, request.app.state.settings.session_secret, description=body.description, verification="VERIFIED", unit_id=unit, lease_id=None, reporter_user_id=None, identity_status="PROVIDED", when=now, intake={}, category=None)
        session.execute(text("UPDATE maintenance_tickets SET status='ASSIGNMENT_PENDING',handoff=true WHERE organization_id=:org AND id=:ticket"), {"org": principal.organization_id, "ticket": ticket["id"]})
        session.execute(text("INSERT INTO maintenance_source_requests(organization_id,source,issue_id,external_property_id,ticket_id,reservation_id,conversation_id,source_fingerprint) VALUES(:org,'guest_recovery',:issue,:external,:ticket,:reservation,:conversation,:fingerprint)"), {"org": principal.organization_id, "issue": body.issue_id, "external": body.external_property_id, "ticket": ticket["id"], "reservation": body.reservation_id, "conversation": body.conversation_id, "fingerprint": body.source_fingerprint})
        return source_repair(session, principal.organization_id, body.issue_id)
    return mutate(session, principal, require_idempotency_key(key), "import", body.model_dump(mode="json"), create)


@router.get("/maintenance-bridge/requests/{issue_id:path}", response_model=SourceRepairOut)
def request_status(issue_id: str, request: Request, principal: Principal = Depends(bridge_principal), session: Session = Depends(get_session, scope="function")):
    if request.state.maintenance_connection["source"] != "guest_recovery":
        problem(403, "FORBIDDEN", "This connection cannot read guest request links.")
    if not 0 < len(issue_id) <= 200:
        problem(422, "VALIDATION_ERROR", "Invalid guest issue identifier.")
    return source_repair(session, principal.organization_id, issue_id)


@router.get("/maintenance-bridge/properties/{external_property_id}/repairs", response_model=PropertyRepairsOut)
def property_repairs(external_property_id: UUID, request: Request, principal: Principal = Depends(bridge_principal), session: Session = Depends(get_session, scope="function")):
    if request.state.maintenance_connection["source"] != "cleaner_scheduler":
        problem(403, "FORBIDDEN", "Only Cleaner Scheduling can read property-wide repair status.")
    if not session.scalar(text("SELECT 1 FROM maintenance_property_links WHERE organization_id=:org AND external_property_id=:external"), {"org": principal.organization_id, "external": external_property_id}):
        problem(404, "PROPERTY_NOT_LINKED", "This property has not been linked to maintenance.")
    rows = session.execute(text("SELECT t.id AS ticket_id,t.ticket_number,t.status,CASE WHEN t.emergency THEN 'EMERGENCY' WHEN t.urgent_triage THEN 'URGENT' ELSE 'ROUTINE' END AS priority,t.updated_at FROM maintenance_tickets t JOIN maintenance_property_links l ON l.organization_id=t.organization_id AND l.unit_id=t.unit_id WHERE t.organization_id=:org AND l.external_property_id=:external AND t.status NOT IN ('COMPLETED','CLOSED','CANCELED') ORDER BY t.ticket_number DESC LIMIT 201"), {"org": principal.organization_id, "external": external_property_id}).mappings().all()
    return {"external_property_id": external_property_id, "repairs": [dict(row) for row in rows[:200]], "has_more": len(rows) > 200}
