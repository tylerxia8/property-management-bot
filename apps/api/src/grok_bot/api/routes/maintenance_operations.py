from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, require_idempotency_key
from grok_bot.api.success import ERROR_RESPONSES
from grok_bot.auth.permissions import Principal
from grok_bot.domain.maintenance_operations import operations, update_worker

router = APIRouter(responses=ERROR_RESPONSES)


class WorkerOut(BaseModel):
    id: UUID
    name: str
    user_id: UUID | None
    approved: bool
    active: bool
    service_property_ids: list[UUID]
    service_categories: list[str]
    accepting_work: bool
    availability_note: str
    max_open_jobs: int
    version: int
    open_jobs: int


class RequestOut(BaseModel):
    id: UUID
    ticket_number: int
    description: str
    status: str
    priority: str
    owner_name: str | None
    next_action: str
    reason_codes: list[str]
    notification_status: str | None
    last_activity_at: datetime


class PropertyOut(BaseModel):
    id: UUID
    name: str


class WorkerHealthOut(BaseModel):
    phone_configured: bool
    history_configured: bool
    pending_notifications: int
    failed_notifications: int
    unknown_notifications: int


class BackgroundWorkerOut(BaseModel):
    status: str
    heartbeat_at: datetime | None
    last_success_at: datetime | None
    last_error_type: str | None
    failure_count: int


class OperationsOut(BaseModel):
    background_worker: BackgroundWorkerOut
    requests: list[RequestOut]
    workers: list[WorkerOut]
    properties: list[PropertyOut]
    worker_health: WorkerHealthOut


class WorkerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: int = Field(strict=True, ge=1)
    approved: bool | None = Field(default=None, strict=True)
    service_property_ids: list[UUID] | None = Field(default=None, max_length=1000)
    service_categories: list[Literal["leak", "electrical", "hvac", "appliance", "structural", "pest_mold", "lock", "general"]] | None = Field(default=None, max_length=8)
    accepting_work: bool | None = Field(default=None, strict=True)
    availability_note: str | None = Field(default=None, max_length=1000)
    max_open_jobs: int | None = Field(default=None, strict=True, ge=1, le=50)

    @model_validator(mode="after")
    def validate_changes(self):
        if self.model_fields_set == {"version"}:
            raise ValueError("Provide at least one worker setting to update.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Worker settings cannot be null.")
        if self.service_property_ids is not None and len(set(self.service_property_ids)) != len(self.service_property_ids):
            raise ValueError("Choose each property once.")
        if self.service_categories is not None and len(set(self.service_categories)) != len(self.service_categories):
            raise ValueError("Choose each category once.")
        return self


@router.get("/maintenance-operations", response_model=OperationsOut)
def get_operations(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return operations(session, principal, request.app.state.clock.now(), request.app.state.settings)


@router.patch("/maintenance-workers/{profile_id}", response_model=WorkerOut)
def patch_worker(profile_id: UUID, body: WorkerUpdate, request: Request, idempotency_key: str = Header(alias="Idempotency-Key"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return update_worker(session, principal, profile_id, body.model_dump(mode="json", exclude_unset=True), require_idempotency_key(idempotency_key), request.app.state.clock.now())
