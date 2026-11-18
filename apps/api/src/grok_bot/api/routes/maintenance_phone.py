from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, request_id_of, require_capability, require_idempotency_key
from grok_bot.api.success import ERROR_RESPONSES
from grok_bot.auth.permissions import Principal
from grok_bot.domain.maintenance_phone import events, reply, simulate
from grok_bot.domain.twilio_phone import callback, signed_form, twiml
from grok_bot.errors import problem

router = APIRouter(responses=ERROR_RESPONSES)


class PhoneEventOut(BaseModel):
    id: UUID
    channel: Literal["SMS", "VOICEMAIL"]
    direction: Literal["INBOUND", "OUTBOUND"]
    recipient_kind: Literal["RESIDENT", "MAINTENANCE"]
    body: str
    from_number: str
    to_number: str
    ticket_id: UUID
    ticket_number: int
    status: str
    created_at: datetime
    request_id: str | None = None


class PhoneInboxOut(BaseModel):
    mode: Literal["simulated", "twilio"]
    configured: bool
    simulation_enabled: bool
    phone_number: str | None
    maintenance_number: str | None
    events: list[PhoneEventOut]
    request_id: str


class SimulateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["SMS", "VOICEMAIL"]
    from_number: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def meaningful_body(cls, value):
        if not value.strip():
            raise ValueError("Describe the maintenance problem.")
        return value.strip()


class ReplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket_id: UUID
    body: str = Field(min_length=1, max_length=1600)

    @field_validator("body")
    @classmethod
    def meaningful_body(cls, value):
        if not value.strip():
            raise ValueError("Write a reply before sending it.")
        return value.strip()


@router.get("/maintenance-phone", response_model=PhoneInboxOut)
def inbox(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    settings = request.app.state.settings
    configured = settings.twilio_configured and settings.twilio_organization_id == principal.organization_id
    return {"mode": "twilio" if configured else "simulated", "configured": configured, "simulation_enabled": settings.allows_local_auth and not settings.twilio_configured, "phone_number": settings.twilio_phone_number if configured else None, "maintenance_number": settings.twilio_maintenance_notify_number if configured else None, "events": events(session, principal.organization_id), "request_id": request_id_of(request)}


@router.post("/maintenance-phone/simulate", response_model=PhoneEventOut, status_code=201)
def simulate_intake(body: SimulateBody, request: Request, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    settings = request.app.state.settings
    if not settings.allows_local_auth or settings.twilio_configured:
        problem(409, "SIMULATION_UNAVAILABLE", "Simulated intake is only available locally without a live phone integration.")
    result = simulate(session, settings, principal, body.model_dump(), require_idempotency_key(idempotency_key), request.app.state.clock.now(), request_id_of(request))
    return {**result, "request_id": request_id_of(request)}


@router.post("/maintenance-phone/replies", response_model=PhoneEventOut, status_code=201)
def phone_reply(body: ReplyBody, request: Request, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.manage")
    settings = request.app.state.settings
    if settings.twilio_configured and settings.twilio_organization_id != principal.organization_id or not settings.twilio_configured and not settings.allows_local_auth:
        problem(409, "PHONE_UNAVAILABLE", "The phone integration is unavailable for this organization.")
    result = reply(session, settings, principal, body.model_dump(mode="json"), require_idempotency_key(idempotency_key), request_id_of(request))
    return {**result, "request_id": request_id_of(request)}


@router.post("/maintenance-phone/twilio/{kind}", response_class=Response, responses={200: {"content": {"application/xml": {"schema": {"type": "string"}}}}})
async def twilio_callback(kind: Literal["messages", "voice", "recording", "transcription", "status"], request: Request, session: Session = Depends(get_session, scope="function")):
    form = await signed_form(request)
    callback(session, request, form, kind)
    return Response(content=twiml(request.app.state.settings, kind), media_type="application/xml")
