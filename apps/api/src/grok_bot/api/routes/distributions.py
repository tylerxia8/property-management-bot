from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, request_id_of, require_capability
from grok_bot.auth.permissions import Principal
from grok_bot.domain.distributions import (
    approve_batch,
    cancel_batch,
    create_destination,
    draft_batch,
    export_batch,
    get_batch,
    issue_statement,
    record_return,
    record_settlement_evidence,
    record_submission_evidence,
    submit_batch,
    validate_batch,
)
from grok_bot.errors import problem

router = APIRouter()


class DestinationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party_id: UUID
    masked_label: str


class DraftBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    as_of: date
    management_party_id: UUID | None = None
    liability_ids: list[UUID] | None = None


class ApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_hash: str
    reason: str


class SubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_date: date
    scripts: dict[str, str] = Field(default_factory=dict)


class EvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str
    posting_date: date | None = None


class EvidenceOut(BaseModel):
    id: str
    kind: str
    simulator: bool
    settled: bool
    reference: str
    bank_contacted: bool | None = None


class PostingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_date: date


class StatementBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    owner_party_id: UUID
    period_start: date
    period_end: date
    reason: str


class OwnerLinkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    party_id: UUID


@router.post("/payee-destinations")
def post_destination(body: DestinationBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.draft")
    return JSONResponse(status_code=201, content=create_destination(session, principal.organization_id, body.party_id, body.masked_label))


@router.post("/distribution-batches")
def post_batch(body: DraftBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.draft")
    result = draft_batch(session, principal.organization_id, body.property_id, body.as_of, body.management_party_id, body.liability_ids)
    result["request_id"] = request_id_of(request)
    return JSONResponse(status_code=201, content=result)


@router.get("/distribution-batches/{batch_id}")
def get_one(batch_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    if not (principal.allows("distributions.draft") or principal.allows("distributions.approve")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    return get_batch(session, principal.organization_id, batch_id)


@router.post("/distribution-batches/{batch_id}/validate")
def post_validate(batch_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.draft")
    return validate_batch(session, principal.organization_id, batch_id)


@router.post("/distribution-batches/{batch_id}/approve")
def post_approve(batch_id: UUID, body: ApproveBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.approve")
    return approve_batch(
        session,
        principal.organization_id,
        batch_id,
        principal.user_id,
        body.snapshot_hash,
        body.reason,
        request.app.state.settings,
        request.app.state.clock.now(),
    )


@router.post("/distribution-batches/{batch_id}/export")
def post_export(batch_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.export")
    return export_batch(session, principal.organization_id, batch_id, principal.user_id, request.app.state.clock.now())


@router.post("/distribution-batches/{batch_id}/submit")
def post_submit(batch_id: UUID, body: SubmitBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.approve")
    return submit_batch(
        session,
        principal.organization_id,
        batch_id,
        body.scripts,
        request.app.state.settings,
        body.posting_date,
        request.app.state.clock.now(),
    )


@router.post("/distribution-batches/{batch_id}/cancel")
def post_cancel(batch_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.approve")
    return cancel_batch(session, principal.organization_id, batch_id)


@router.post("/payment-items/{item_id}/submission-evidence", response_model=EvidenceOut)
def post_submission_evidence(item_id: UUID, body: EvidenceBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.approve")
    return record_submission_evidence(session, principal.organization_id, item_id, body.reference, request.app.state.clock.now())


@router.post("/payment-items/{item_id}/settlement-evidence", response_model=EvidenceOut)
def post_settlement_evidence(item_id: UUID, body: EvidenceBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.approve")
    if body.posting_date is None:
        problem(422, "VALIDATION_ERROR", "Settlement evidence needs a posting date.")
    return record_settlement_evidence(session, principal.organization_id, item_id, body.reference, body.posting_date, request.app.state.clock.now())


@router.post("/distribution-items/{item_id}/returns")
def post_return(item_id: UUID, body: PostingBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "distributions.approve")
    return record_return(session, principal.organization_id, item_id, body.posting_date)


@router.post("/statements")
def post_statement(body: StatementBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "statements.issue")
    return JSONResponse(
        status_code=201,
        content=issue_statement(
            session,
            principal.organization_id,
            body.property_id,
            body.owner_party_id,
            body.period_start,
            body.period_end,
            body.reason,
        ),
    )


@router.get("/statements")
def list_statements(principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    if not (principal.allows("statements.read") or principal.allows("statements.issue") or principal.allows("distributions.approve")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    rows = session.execute(
        text(
            """
            SELECT id, version, snapshot_hash, snapshot, owner_party_id, period_start, period_end, reason
            FROM owner_statements
            WHERE organization_id = :organization_id
            ORDER BY period_start, version
            """
        ),
        {"organization_id": principal.organization_id},
    ).mappings().all()
    return {"items": [_statement_body(row) for row in rows]}


@router.get("/statements/{statement_id}")
def get_statement(statement_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    if not (principal.allows("statements.read") or principal.allows("statements.issue") or principal.allows("distributions.approve")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    row = session.execute(
        text(
            """
            SELECT id, version, snapshot_hash, snapshot, owner_party_id, period_start, period_end, reason
            FROM owner_statements
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": principal.organization_id, "id": statement_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Statement not found.")
    return _statement_body(row)


def _statement_body(row) -> dict:
    snapshot = row["snapshot"]
    if isinstance(snapshot, str):
        snapshot = __import__("json").loads(snapshot)
    return {
        "id": str(row["id"]),
        "version": row["version"],
        "snapshot_hash": row["snapshot_hash"],
        "snapshot": snapshot,
        "owner_party_id": str(row["owner_party_id"]),
        "period_start": row["period_start"].isoformat(),
        "period_end": row["period_end"].isoformat(),
        "reason": row["reason"],
        "unrestricted_cents": snapshot.get("unrestricted_cents"),
    }


@router.post("/owner-links")
def post_owner_link(body: OwnerLinkBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "statements.issue")
    link_id = __import__("uuid").uuid4()
    session.execute(
        text(
            """
            INSERT INTO owner_links (id, organization_id, user_id, party_id)
            VALUES (:id, :organization_id, :user_id, :party_id)
            """
        ),
        {"id": link_id, "organization_id": principal.organization_id, "user_id": body.user_id, "party_id": body.party_id},
    )
    return JSONResponse(status_code=201, content={"id": str(link_id)})
