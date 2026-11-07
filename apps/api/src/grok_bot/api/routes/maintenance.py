import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, principal_from_request, request_id_of, require_capability
from grok_bot.api.routes.accounting import InvoiceBody
from grok_bot.auth.permissions import Principal
from grok_bot.auth.tokens import TokenError, _sign, verify_token
from grok_bot.db import set_tenant
from grok_bot.domain.maintenance import (
    acknowledge,
    add_destination,
    add_message,
    advance_escalations,
    assign_contractor,
    can_view_ticket,
    complete_work,
    safe_media_file,
    confirm_appointment,
    create_appointment,
    create_contractor_profile,
    create_unverified_ticket,
    create_verified_ticket,
    deescalate,
    get_ticket,
    link_lease_party,
    mint_org_token,
    record_estimate,
    request_escalation,
    request_upload,
    respond_assignment,
    save_quarantine,
    set_category,
    set_intake,
    store_accommodation,
    store_and_scan,
    store_entry_code,
    submit_work_invoice,
    transition_ticket,
)
from grok_bot.errors import problem
from grok_bot.domain.maintenance_workspace import homes, ticket_list, report_once
from grok_bot.domain.idempotency import request_hash
from grok_bot.api.deps import require_idempotency_key
from grok_bot.api.success import MaintenanceContextOut, MaintenancePageOut
from grok_bot.api.success import (
    ERROR_RESPONSES,
    AckOut,
    AdvanceOut,
    AssignmentOut,
    CompletionOut,
    DeescalateOut,
    DownloadOut,
    EscalationDestinationOut,
    EscalationOut,
    EstimateOut,
    IntakeLinkOut,
    InvoiceOut,
    LeasePartyOut,
    MaintenanceAppointmentOut,
    MaintenanceConfirmOut,
    ProfileOut,
    QuarantineOut,
    RespondOut,
    ScanOut,
    StoredOut,
    TicketOut,
    TransitionOut,
    UploadOut,
)

router = APIRouter(responses=ERROR_RESPONSES)


class TicketBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=5000)
    unit_id: UUID | None = None
    lease_id: UUID | None = None
    category: str | None = None
    location: str | None = None
    onset: str | None = None
    frequency: str | None = None
    contact_id: str | None = None
    contact: str | None = None
    media_status: str | None = None
    media_reason: str | None = None
    preferred_access_windows: list[str] | None = None
    entry_permission: str | None = None
    safety_concerns: str | None = None

    @field_validator("description")
    @classmethod
    def meaningful_description(cls, value):
        if not value.strip():
            raise ValueError("Describe the problem before sending your request.")
        return value.strip()


class UnverifiedBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1)
    unit_id: UUID | None = None
    phone: str | None = None


class MessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=5000)
    classifier_result: str | None = None
    field_key: str | None = None

    @field_validator("body")
    @classmethod
    def meaningful_body(cls, value):
        if not value.strip():
            raise ValueError("Write a follow-up before sending it.")
        return value.strip()


class IntakeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_key: str | None = None
    status: str | None = None
    value: str | None = None
    reason: str | None = None
    category: str | None = None


class UploadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party_id: UUID
    user_id: UUID | None = None
    approved: bool = False
    trades: str = ""


class AssignmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contractor_profile_id: UUID
    scope: str = Field(min_length=1)


class RespondBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accept: bool


class CompletionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str = ""


class EstimateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estimate_cents: int = Field(ge=0)


class TransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    reason: str | None = None
    duplicate_of_id: UUID | None = None
    status: str | None = None


class SecretBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1)


class NoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=1)


class AppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime
    timezone: str


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_permission: str
    notice_evidence: str | None = None
    contractor_accepted: bool = False


class DestinationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    label: str
    fail_next: bool = False


class LeasePartyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID


class ReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = ""


@router.post("/maintenance-intake-links", response_model=IntakeLinkOut)
def post_intake_link(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    del session
    return {"token": mint_org_token(request.app.state.settings.session_secret, principal.organization_id), "request_id": request_id_of(request)}


@router.get("/maintenance-context", response_model=MaintenanceContextOut)
def get_context(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    _require_workspace(principal)
    return {"homes": homes(session, principal.organization_id, principal.user_id), "can_manage": principal.allows("maintenance.manage"), "photos_enabled": request.app.state.settings.fixture_media_scanner_allowed, "request_id": request_id_of(request)}


@router.get("/maintenance-tickets", response_model=MaintenancePageOut)
def list_tickets(request: Request, limit: int = Query(default=30, ge=1, le=100), before: int | None = Query(default=None, ge=1), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    _require_workspace(principal)
    result = ticket_list(session, principal.organization_id, principal.user_id, principal.allows("maintenance.manage"), limit, before)
    return {**result, "request_id": request_id_of(request)}


def _require_workspace(principal):
    if not (principal.allows("maintenance.report") or principal.allows("maintenance.manage")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")


@router.post("/maintenance-tickets", response_model=TicketOut, status_code=201)
def post_ticket(body: TicketBody, request: Request, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    if not (principal.allows("maintenance.report") or principal.allows("maintenance.manage")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    def create():
        return create_verified_ticket(
            session,
            principal.organization_id,
            principal.user_id,
            body.model_dump(),
            request.app.state.settings.session_secret,
            request.app.state.clock.now(),
        )
    if idempotency_key is not None:
        key = require_idempotency_key(idempotency_key)
        hashed = request_hash("POST", "/v1/maintenance-tickets", {**body.model_dump(mode="json"), "actor": str(principal.user_id)})
        result = report_once(session, principal, key, hashed, create, lambda ticket_id: get_ticket(session, principal.organization_id, ticket_id, request.app.state.settings.session_secret, "tenant"))
    else:
        result = create()
    result["request_id"] = request_id_of(request)
    return JSONResponse(status_code=201, content=result)


@router.post("/maintenance-tickets/unverified", response_model=TicketOut, status_code=201)
def post_unverified(body: UnverifiedBody, request: Request, session: Session = Depends(get_session, scope="function")):
    payload = _bearer_payload(request)
    if payload.get("amr") != "intake_org" or payload.get("env") != "ticket":
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    organization_id = UUID(payload["org"])
    set_tenant(session, organization_id, None, access_mode="unverified")
    del body.unit_id, body.phone
    result = create_unverified_ticket(
        session,
        organization_id,
        body.description,
        request.app.state.settings.session_secret,
        request.app.state.clock.now(),
    )
    result["request_id"] = request_id_of(request)
    return JSONResponse(status_code=201, content=result)


@router.get("/maintenance-tickets/{ticket_id}", response_model=TicketOut)
def get_one(ticket_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    viewer = can_view_ticket(session, principal.organization_id, ticket_id, principal.user_id, principal.roles)
    if viewer is None:
        problem(404, "NOT_FOUND", "Ticket not found.")
    result = get_ticket(session, principal.organization_id, ticket_id, request.app.state.settings.session_secret, viewer)
    result["request_id"] = request_id_of(request)
    return result


@router.patch("/maintenance-tickets/{ticket_id}", response_model=TicketOut)
def patch_one(ticket_id: UUID, body: IntakeBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    viewer = can_view_ticket(session, principal.organization_id, ticket_id, principal.user_id, principal.roles)
    if viewer not in {"manager", "tenant"}:
        problem(404, "NOT_FOUND", "Ticket not found.")
    if body.category is not None:
        if viewer != "manager":
            problem(403, "FORBIDDEN", "You do not have access to this action.")
        set_category(session, principal.organization_id, ticket_id, body.category)
    if body.field_key is not None:
        if body.status is None:
            problem(422, "VALIDATION_ERROR", "An intake update needs a status.")
        set_intake(session, principal.organization_id, ticket_id, body.field_key, body.status, body.value, body.reason)
    result = get_ticket(session, principal.organization_id, ticket_id, request.app.state.settings.session_secret, viewer, persist_questions=False)
    result["request_id"] = request_id_of(request)
    return result


@router.post("/maintenance-tickets/{ticket_id}/messages", response_model=TicketOut)
def post_message(ticket_id: UUID, body: MessageBody, request: Request, session: Session = Depends(get_session, scope="function")):
    actor, organization_id = _ticket_actor(request, session, ticket_id)
    add_message(
        session,
        organization_id,
        ticket_id,
        body.body,
        body.classifier_result,
        request.app.state.settings.session_secret,
        request.app.state.clock,
        None if actor is None else actor.user_id,
        field_key=body.field_key,
    )
    viewer = "public" if actor is None else can_view_ticket(session, organization_id, ticket_id, actor.user_id, actor.roles)
    if viewer is None:
        problem(404, "NOT_FOUND", "Ticket not found.")
    result = get_ticket(session, organization_id, ticket_id, request.app.state.settings.session_secret, viewer, persist_questions=False)
    result["request_id"] = request_id_of(request)
    return result


@router.post("/maintenance-tickets/{ticket_id}/media-uploads", response_model=UploadOut, status_code=201)
def post_upload(ticket_id: UUID, body: UploadBody, request: Request, session: Session = Depends(get_session, scope="function")):
    actor, organization_id = _ticket_actor(request, session, ticket_id)
    if actor is not None and can_view_ticket(session, organization_id, ticket_id, actor.user_id, actor.roles) is None:
        problem(404, "NOT_FOUND", "Ticket not found.")
    created = request_upload(session, organization_id, ticket_id, body.content_type, body.size_bytes, body.filename, body.sha256)
    token = _scoped_token(request, organization_id, created["id"], "media_upload", ticket_id)
    return JSONResponse(
        status_code=201,
        content={
            "id": created["id"],
            "status": "QUARANTINED",
            "upload_url": f"/v1/media/{created['id']}/bytes?token={token}",
            "expires_in_seconds": 300,
            "required_headers": {"Content-Type": body.content_type},
            "ticket_id": str(ticket_id),
            "request_id": request_id_of(request),
        },
    )


@router.post("/media/{media_id}/bytes", response_model=QuarantineOut)
async def post_bytes(media_id: UUID, request: Request, token: str, session: Session = Depends(get_session, scope="function")):
    payload = _media_payload(request, token, media_id, "media_upload")
    set_tenant(session, UUID(payload["org"]), None, intake_ticket_id=UUID(payload["tid"]), access_mode="intake")
    row = _media(session, UUID(payload["org"]), media_id)
    limit = min(row["size_bytes"] or 0, 200 * 1024 * 1024)
    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > limit:
            problem(413, "MEDIA_LIMIT", "The upload exceeds its declared size.")
        chunks.extend(chunk)
    stored = save_quarantine(session, request.app.state.settings, UUID(payload["org"]), media_id, bytes(chunks))
    stored["request_id"] = request_id_of(request)
    return stored


@router.post("/media/{media_id}/complete", response_model=ScanOut)
def post_complete(media_id: UUID, request: Request, session: Session = Depends(get_session, scope="function")):
    actor, organization_id = _any_actor(request, session)
    row = _media(session, organization_id, media_id)
    if actor is None:
        payload = _bearer_payload(request)
        if payload.get("sub") != str(row["ticket_id"]):
            problem(404, "NOT_FOUND", "Media not found.")
    elif can_view_ticket(session, organization_id, row["ticket_id"], actor.user_id, actor.roles) is None:
        problem(404, "NOT_FOUND", "Media not found.")
    result = store_and_scan(session, request.app.state.settings, organization_id, media_id, None)
    result["request_id"] = request_id_of(request)
    result["video_understanding"] = False
    return result


@router.get("/media/{media_id}/download", response_model=DownloadOut)
def get_download(media_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    row = _media(session, principal.organization_id, media_id)
    if can_view_ticket(session, principal.organization_id, row["ticket_id"], principal.user_id, principal.roles) is None:
        problem(404, "NOT_FOUND", "Media not found.")
    if row["status"] != "READY" or not row["derivative_key"]:
        problem(404, "MEDIA_NOT_READY", "This file is not available.")
    token = _scoped_token(request, principal.organization_id, str(media_id), "media_download", row["ticket_id"])
    return {
        "download_url": f"/v1/media/{media_id}/content?token={token}",
        "expires_in_seconds": 300,
        "scanner_name": row["scanner_name"],
        "video_understanding": False,
        "request_id": request_id_of(request),
    }


@router.get(
    "/media/{media_id}/content",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
            "description": "Scanned derivative file.",
        }
    },
)
def get_content(media_id: UUID, request: Request, token: str, session: Session = Depends(get_session, scope="function")):
    payload = _media_payload(request, token, media_id, "media_download")
    organization_id = UUID(payload["org"])
    set_tenant(session, organization_id, None, intake_ticket_id=UUID(payload["tid"]), access_mode="intake")
    row = _media(session, organization_id, media_id)
    if row["status"] != "READY" or not row["derivative_key"]:
        problem(404, "MEDIA_NOT_READY", "This file is not available.")
    target = safe_media_file(Path(request.app.state.settings.media_root), row["derivative_key"])
    return FileResponse(target)


@router.post("/maintenance-tickets/{ticket_id}/escalations", response_model=EscalationOut)
def post_escalation(ticket_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    if not (principal.allows("maintenance.report") or principal.allows("maintenance.manage")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    if can_view_ticket(session, principal.organization_id, ticket_id, principal.user_id, principal.roles) is None:
        problem(404, "NOT_FOUND", "Ticket not found.")
    result = request_escalation(session, principal.organization_id, ticket_id, principal.user_id, request.app.state.clock.now())
    result["request_id"] = request_id_of(request)
    return result


@router.post("/escalations/{escalation_id}/acknowledge", response_model=AckOut)
def post_ack(escalation_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.acknowledge")
    result = acknowledge(session, principal.organization_id, escalation_id, principal.user_id, request.app.state.clock)
    result["request_id"] = request_id_of(request)
    return result


@router.post("/maintenance-escalations/advance", response_model=AdvanceOut)
def post_advance(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    result = advance_escalations(session, principal.organization_id, request.app.state.clock, principal.user_id)
    result["request_id"] = request_id_of(request)
    result["delivered_at"] = None
    return result


@router.post("/maintenance-tickets/{ticket_id}/deescalations", response_model=DeescalateOut)
def post_deescalate(ticket_id: UUID, body: ReasonBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    return deescalate(session, principal.organization_id, ticket_id, principal.user_id, body.reason)


@router.post("/contractor-profiles", response_model=ProfileOut, status_code=201)
def post_profile(body: ProfileBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    return JSONResponse(status_code=201, content=create_contractor_profile(session, principal.organization_id, body.party_id, body.user_id, body.approved, body.trades))


@router.post("/maintenance-tickets/{ticket_id}/assignments", response_model=AssignmentOut, status_code=201)
def post_assignment(ticket_id: UUID, body: AssignmentBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.assign")
    return JSONResponse(status_code=201, content=assign_contractor(session, principal.organization_id, ticket_id, body.contractor_profile_id, body.scope, principal.user_id))


@router.post("/assignments/{assignment_id}/respond", response_model=RespondOut)
def post_respond(assignment_id: UUID, body: RespondBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.respond")
    return respond_assignment(session, principal.organization_id, assignment_id, principal.user_id, body.accept)


@router.post("/work-orders/{work_order_id}/completion", response_model=CompletionOut)
def post_completion(work_order_id: UUID, body: CompletionBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    _require_work_access(session, principal, work_order_id)
    result = complete_work(session, principal.organization_id, work_order_id, body.notes)
    result["request_id"] = "maintenance"
    return result


@router.post("/work-orders/{work_order_id}/invoices", response_model=InvoiceOut, status_code=201)
def post_work_invoice(work_order_id: UUID, body: InvoiceBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    _require_work_access(session, principal, work_order_id)
    if body.currency != "USD":
        problem(422, "UNSUPPORTED_CURRENCY", "Only USD cents are supported.")
    result = submit_work_invoice(session, principal.organization_id, work_order_id, body.model_dump())
    return JSONResponse(status_code=201, content=result)


@router.post("/work-orders/{work_order_id}/estimates", response_model=EstimateOut)
def post_estimate(work_order_id: UUID, body: EstimateBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    _require_work_access(session, principal, work_order_id)
    return record_estimate(session, principal.organization_id, work_order_id, body.estimate_cents)


@router.post("/maintenance-tickets/{ticket_id}/transitions", response_model=TransitionOut)
def post_transition(ticket_id: UUID, body: TransitionBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    return transition_ticket(session, principal.organization_id, ticket_id, body.action, body.reason, body.duplicate_of_id, body.status, principal.user_id)


@router.post("/maintenance-tickets/{ticket_id}/entry-secrets", response_model=StoredOut)
def post_secret(ticket_id: UUID, body: SecretBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    stored = store_entry_code(session, principal.organization_id, ticket_id, body.code, request.app.state.settings.contact_key_bytes)
    stored["request_id"] = request_id_of(request)
    return stored


@router.post("/maintenance-tickets/{ticket_id}/accommodations", response_model=StoredOut)
def post_note(ticket_id: UUID, body: NoteBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    stored = store_accommodation(session, principal.organization_id, ticket_id, body.note, request.app.state.settings.contact_key_bytes)
    stored["request_id"] = request_id_of(request)
    return stored


@router.post("/maintenance-tickets/{ticket_id}/appointments", response_model=MaintenanceAppointmentOut, status_code=201)
def post_appointment(ticket_id: UUID, body: AppointmentBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    viewer = can_view_ticket(session, principal.organization_id, ticket_id, principal.user_id, principal.roles)
    if viewer not in {"manager", "tenant"}:
        problem(404, "NOT_FOUND", "Ticket not found.")
    return JSONResponse(status_code=201, content=create_appointment(session, principal.organization_id, ticket_id, body.starts_at, body.ends_at, body.timezone))


@router.post("/maintenance-appointments/{appointment_id}/confirm", response_model=MaintenanceConfirmOut)
def post_confirm(appointment_id: UUID, body: ConfirmBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    return confirm_appointment(session, principal.organization_id, appointment_id, body.entry_permission, body.notice_evidence, body.contractor_accepted)


@router.post("/escalation-destinations", response_model=EscalationDestinationOut, status_code=201)
def post_destination(body: DestinationBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    return JSONResponse(status_code=201, content=add_destination(session, principal.organization_id, body.role, body.label, body.fail_next))


@router.post("/leases/{lease_id}/parties", response_model=LeasePartyOut, status_code=201)
def post_lease_party(lease_id: UUID, body: LeasePartyBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    if not (principal.allows("maintenance.manage") or principal.allows("leases.write")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    return JSONResponse(status_code=201, content=link_lease_party(session, principal.organization_id, lease_id, body.user_id))


def _require_work_access(session: Session, principal: Principal, work_order_id: UUID) -> None:
    row = session.execute(
        text(
            """
            SELECT w.ticket_id, a.contractor_profile_id
            FROM work_orders AS w
            JOIN assignments AS a ON a.id = w.assignment_id AND a.organization_id = w.organization_id
            WHERE w.organization_id = :organization_id AND w.id = :id
            """
        ),
        {"organization_id": principal.organization_id, "id": work_order_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Work order not found.")
    if principal.allows("maintenance.manage") or principal.allows("invoices.submit"):
        return
    if principal.allows("maintenance.respond") and can_view_ticket(session, principal.organization_id, row["ticket_id"], principal.user_id, principal.roles) == "contractor":
        return
    problem(403, "FORBIDDEN", "You do not have access to this action.")


def _media(session: Session, organization_id: UUID, media_id: UUID):
    row = session.execute(
        text("SELECT * FROM media_objects WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": media_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Media not found.")
    return row


def _ticket_actor(request: Request, session: Session, ticket_id: UUID):
    payload = _bearer_payload(request)
    if payload.get("amr") == "intake_link" and payload.get("env") == "ticket" and payload.get("sub") == str(ticket_id):
        organization_id = UUID(payload["org"])
        set_tenant(session, organization_id, None, intake_ticket_id=ticket_id, access_mode="intake")
        return None, organization_id
    principal = principal_from_request(request, session)
    if can_view_ticket(session, principal.organization_id, ticket_id, principal.user_id, principal.roles) is None:
        problem(404, "NOT_FOUND", "Ticket not found.")
    return principal, principal.organization_id


def _any_actor(request: Request, session: Session):
    payload = _bearer_payload(request)
    if payload.get("amr") == "intake_link" and payload.get("env") == "ticket":
        if payload.get("sub") is None:
            problem(401, "UNAUTHENTICATED", "Sign-in is required.")
        organization_id = UUID(payload["org"])
        set_tenant(session, organization_id, None, intake_ticket_id=UUID(payload["sub"]), access_mode="intake")
        return None, organization_id
    principal = principal_from_request(request, session)
    return principal, principal.organization_id


def _bearer_payload(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    try:
        return verify_token(header.split(" ", 1)[1].strip(), request.app.state.settings.session_secret)
    except TokenError:
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")


def _media_payload(request: Request, token: str, media_id: UUID, amr: str) -> dict:
    try:
        payload = verify_token(token, request.app.state.settings.session_secret)
    except TokenError:
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    if payload.get("amr") != amr or payload.get("env") != "ticket" or payload.get("sub") != str(media_id) or not payload.get("tid"):
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    return payload


def _scoped_token(request: Request, organization_id: UUID, subject: str, amr: str, ticket_id: UUID) -> str:
    return _sign(
        {
            "amr": amr,
            "env": "ticket",
            "exp": int(time.time()) + 300,
            "org": str(organization_id),
            "sub": subject,
            "tid": str(ticket_id),
            "v": 1,
        },
        request.app.state.settings.session_secret,
    )
