from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from grok_bot.api.success import MaintenanceIssueOut, MaintenanceIssueRecordOut


class WorkflowHome(BaseModel):
    property_name: str
    unit_label: str


class WorkflowTicket(BaseModel):
    id: UUID
    ticket_number: int
    description: str
    status: str
    verification: str
    priority: str
    home: WorkflowHome | None


class WorkflowAssignment(BaseModel):
    id: UUID
    contractor_profile_id: UUID
    status: Literal["PENDING", "ACCEPTED", "DECLINED"]
    scope: str
    created_at: datetime
    updated_at: datetime


class WorkflowWorkOrder(BaseModel):
    id: UUID
    assignment_id: UUID
    workflow_managed: bool
    estimate_cents: int | None
    estimate_version: int
    estimate_scope: str | None
    authorization_state: str
    approved_version: int | None
    spending_limit_cents: int | None
    approved_by: UUID | None
    approved_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    confirmed_at: datetime | None
    completion_notes: str | None
    completion_media_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class WorkflowAppointment(BaseModel):
    id: UUID
    starts_at: datetime
    ends_at: datetime
    timezone: str
    status: str
    entry_permission: str
    contractor_accepted: bool
    assignment_id: UUID | None
    entry_granted_by: UUID | None


class WorkflowAvailability(BaseModel):
    windows: list[str]


class WorkflowMessage(BaseModel):
    id: UUID
    body: str
    author_role: Literal["tenant", "manager", "contractor", "system"]
    sender_label: str
    created_at: datetime
    media_ids: list[UUID]


class WorkflowMedia(BaseModel):
    id: UUID
    content_type: str
    status: str


class WorkflowContractor(BaseModel):
    id: UUID
    name: str
    trades: str


class WorkflowEscalation(BaseModel):
    id: UUID
    state: str
    created_at: datetime
    acknowledged_at: datetime | None


class WorkflowDetailOut(BaseModel):
    issue_records: list[MaintenanceIssueRecordOut] = []
    escalation: WorkflowEscalation | None = None
    issues: list[MaintenanceIssueOut] = []
    role: Literal["tenant", "manager", "contractor"]
    available_actions: list[str]
    ticket: WorkflowTicket
    assignment: WorkflowAssignment | None
    work_order: WorkflowWorkOrder | None
    appointments: list[WorkflowAppointment]
    availability: WorkflowAvailability
    messages: list[WorkflowMessage]
    media: list[WorkflowMedia]
    completion_media: list[WorkflowMedia]
    follow_up_flags: list[str]
    contractors: list[WorkflowContractor]


class WorkflowBoardItem(WorkflowTicket):
    job_status: str
    next_step: str
    due_flags: list[str]


class WorkflowBoardOut(BaseModel):
    next_cursor: str | None = None
    role: Literal["tenant", "manager", "contractor"]
    items: list[WorkflowBoardItem]
    contractors: list[WorkflowContractor]
