from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, require_idempotency_key
from grok_bot.auth.permissions import Principal
from grok_bot.domain.maintenance_workflow import board, detail, execute
from grok_bot.api.workflow_success import WorkflowBoardOut, WorkflowDetailOut
from grok_bot.api.success import ERROR_RESPONSES
from grok_bot.errors import problem

router = APIRouter(responses=ERROR_RESPONSES)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Assign(Command):
    action: Literal["assign"]
    contractor_profile_id: UUID
    scope: str = Field(min_length=1, max_length=5000)


class Simple(Command):
    action: Literal["accept", "start_work", "confirm_completion"]


class Reason(Command):
    action: Literal["decline", "reject_estimate", "reopen", "resolve_self"]
    reason: str = Field(min_length=1, max_length=5000)


class Message(Command):
    action: Literal["message"]
    body: str = Field(min_length=1, max_length=5000)
    media_ids: list[UUID] = Field(default_factory=list, max_length=10)


class Availability(Command):
    action: Literal["availability"]
    windows: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(min_length=1, max_length=10)


class Visit(Command):
    action: Literal["propose_visit"]
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_window(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None or self.ends_at <= self.starts_at or self.ends_at - self.starts_at > timedelta(hours=24):
            raise ValueError("Provide timezone-aware start and end times in order.")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Choose a valid timezone.")
        return self


class ConfirmVisit(Command):
    action: Literal["confirm_visit"]
    appointment_id: UUID
    entry_permission: Literal["GRANTED", "DENIED"]


class Estimate(Command):
    action: Literal["estimate"]
    estimate_cents: int = Field(strict=True, ge=0, le=100000000)
    scope: str = Field(min_length=1, max_length=5000)


class ArrangeRepair(Visit):
    action: Literal["arrange_repair"]
    estimate_cents: int | None = Field(default=None, strict=True, ge=0, le=100000000)
    scope: str = Field(min_length=1, max_length=5000)


class Approve(Command):
    action: Literal["approve_estimate"]
    estimate_version: int = Field(strict=True, ge=1)
    spending_limit_cents: int = Field(strict=True, ge=0, le=100000000)


class Complete(Command):
    action: Literal["complete"]
    notes: str = Field(min_length=1, max_length=5000)
    media_ids: list[UUID] = Field(min_length=1, max_length=10)


WorkflowCommand = Annotated[Assign | Simple | Reason | Message | Availability | Visit | ConfirmVisit | Estimate | ArrangeRepair | Approve | Complete, Field(discriminator="action")]


@router.get("/maintenance-workflow", response_model=WorkflowBoardOut)
def get_board(request: Request, view: Literal["active", "past"] | None = None, before: str | None = Query(default=None, pattern=r"^[0-3]:[1-9][0-9]{0,18}$"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    if before and int(before.split(":")[1]) > 9223372036854775807:
        problem(422, "VALIDATION_ERROR", "The repair page cursor is invalid.")
    return board(session, principal, request.app.state.clock.now(), view, before)


@router.get("/maintenance-tickets/{ticket_id}/workflow", response_model=WorkflowDetailOut)
def get_workflow(ticket_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return detail(session, principal, ticket_id, request.app.state.clock.now())


@router.post("/maintenance-tickets/{ticket_id}/workflow", response_model=WorkflowDetailOut)
def post_workflow(ticket_id: UUID, body: WorkflowCommand, request: Request, idempotency_key: str = Header(alias="Idempotency-Key"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return execute(session, principal, ticket_id, body.model_dump(mode="json"), require_idempotency_key(idempotency_key), request.app.state.clock.now())
