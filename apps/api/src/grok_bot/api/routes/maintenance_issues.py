from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, require_idempotency_key
from grok_bot.api.success import ERROR_RESPONSES
from grok_bot.auth.permissions import Principal
from grok_bot.domain.maintenance_issues import detail, update

router = APIRouter(responses=ERROR_RESPONSES)


class IssueOut(BaseModel):
    id: UUID
    organization_id: UUID
    ticket_id: UUID
    key: str
    title: str
    status: str
    evidence: str
    version: int
    confirmed_by: UUID | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IssueEventOut(BaseModel):
    id: UUID
    organization_id: UUID
    ticket_id: UUID
    issue_id: UUID
    actor_id: UUID | None
    version: int
    before_status: str | None
    status: str
    source: str
    note: str
    created_at: datetime


class IssuesOut(BaseModel):
    items: list[IssueOut]
    events: list[IssueEventOut]


class IssueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(strict=True, ge=1)
    status: Literal["OPEN", "WAITING_PARTS", "RESOLUTION_REPORTED", "TENANT_CONFIRMED"]
    note: str | None = Field(default=None, min_length=1, max_length=5000)


@router.get("/maintenance-tickets/{ticket_id}/issues", response_model=IssuesOut)
def get_issues(ticket_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return detail(session, principal, ticket_id)


@router.post("/maintenance-tickets/{ticket_id}/issues/{issue_id}/updates", response_model=IssuesOut)
def post_issue_update(ticket_id: UUID, issue_id: UUID, body: IssueUpdate, request: Request, idempotency_key: str = Header(alias="Idempotency-Key"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return update(session, principal, ticket_id, issue_id, body.model_dump(mode="json"), require_idempotency_key(idempotency_key), request.app.state.clock.now())
