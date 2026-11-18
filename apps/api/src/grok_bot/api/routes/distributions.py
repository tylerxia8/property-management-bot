from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, request_id_of, require_capability, require_idempotency_key
from grok_bot.api.success import (
    ERROR_RESPONSES,
    ApprovedBatchOut,
    BatchOut,
    DestinationOut,
    DraftBatchOut,
    EvidenceOut,
    ExportOut,
    OwnerLinkOut,
    ReturnItemOut,
    StatementIssuedOut,
    StatementOut,
    StatementPageOut,
    SubmitBatchOut,
)
from grok_bot.auth.permissions import Principal
from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.portfolio import run_idempotent_create
from grok_bot.domain.records import write_audit
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

router = APIRouter(responses=ERROR_RESPONSES)


class DestinationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party_id: UUID
    masked_label: str
    channel: Literal["ZELLE", "VENMO"] = "ZELLE"


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
    posting_date: date | None = None


class SubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_date: date
    scripts: dict[str, str] = Field(default_factory=dict)


class EvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str
    posting_date: date | None = None


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


@router.post("/payee-destinations", response_model=DestinationOut, status_code=201)
def post_destination(body: DestinationBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.draft")

    def create():
        destination = create_destination(session, principal.organization_id, body.party_id, body.masked_label, body.channel)
        write_audit(
            session, organization_id=principal.organization_id, actor_id=principal.user_id,
            action="distribution.destination_created", target_type="payee_destination", target_id=UUID(destination["id"]),
            target_version=destination["version"], request_id=request_id_of(request), before_state=None,
            after_state={"party_id": str(body.party_id), "channel": body.channel, "version": destination["version"]},
        )
        return destination

    if idempotency_key is None:
        return JSONResponse(status_code=201, content=create())
    key = require_idempotency_key(idempotency_key)
    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/payee-destinations", body.model_dump(mode="json")), create=create)
    return JSONResponse(status_code=201, content=result)


@router.post("/distribution-batches", response_model=DraftBatchOut, status_code=201)
def post_batch(body: DraftBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.draft")

    def create():
        drafted = draft_batch(session, principal.organization_id, body.property_id, body.as_of, body.management_party_id, body.liability_ids)
        return {**drafted, "request_id": request_id_of(request)}

    if idempotency_key is None:
        return JSONResponse(status_code=201, content=create())
    key = require_idempotency_key(idempotency_key)
    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/distribution-batches", body.model_dump(mode="json")), create=create)
    return JSONResponse(status_code=201, content=result)


@router.get("/distribution-batches/{batch_id}", response_model=BatchOut)
def get_one(batch_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    if not (principal.allows("distributions.draft") or principal.allows("distributions.approve")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    return get_batch(session, principal.organization_id, batch_id)


@router.post("/distribution-batches/{batch_id}/validate", response_model=BatchOut)
def post_validate(batch_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "distributions.draft")
    return validate_batch(session, principal.organization_id, batch_id)


@router.post("/distribution-batches/{batch_id}/approve", response_model=ApprovedBatchOut)
def post_approve(batch_id: UUID, body: ApproveBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    from grok_bot.domain.distributions import _lock_batch
    from grok_bot.domain.simulated_bank import account_for_property, send_approved

    settings = request.app.state.settings
    batch = _lock_batch(session, principal.organization_id, batch_id)
    simulated = settings.allows_local_auth and account_for_property(session, principal.organization_id, batch["property_id"]) is not None
    stripe = session.execute(text("SELECT 1 FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": principal.organization_id, "property": batch["property_id"]}).scalar() is not None
    if simulated or stripe:
        require_idempotency_key(idempotency_key)
        if body.posting_date is None:
            problem(422, "VALIDATION_ERROR", "Automatic payouts require a posting date.")
        settings = settings.model_copy(update={"approval_ttl_hours": settings.approval_ttl_hours or 24, "step_up_max_age_seconds": settings.step_up_max_age_seconds or 900})

    def create():
        now = request.app.state.clock.now()
        approved = approve_batch(session, principal.organization_id, batch_id, principal.user_id, body.snapshot_hash, body.reason, settings, now)
        if simulated:
            send_approved(session, principal.organization_id, batch_id, body.posting_date, now)
            approved = {**get_batch(session, principal.organization_id, batch_id), "approval_id": approved["approval_id"]}
        elif stripe:
            from grok_bot.domain.stripe_worker import queue_batch

            queue_batch(session, principal, batch_id, UUID(approved["approval_id"]), body.posting_date, settings, now)
            approved = {**get_batch(session, principal.organization_id, batch_id), "approval_id": approved["approval_id"]}
        return approved

    if idempotency_key is None:
        return create()
    key = require_idempotency_key(idempotency_key)
    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", f"/v1/distribution-batches/{batch_id}/approve", body.model_dump(mode="json")), create=create)
    return result


@router.post("/distribution-batches/{batch_id}/export", response_model=ExportOut)
def post_export(batch_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "distributions.export")
    return export_batch(session, principal.organization_id, batch_id, principal.user_id, request.app.state.clock.now())


@router.post("/distribution-batches/{batch_id}/submit", response_model=SubmitBatchOut)
def post_submit(batch_id: UUID, body: SubmitBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
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


@router.post("/distribution-batches/{batch_id}/cancel", response_model=BatchOut)
def post_cancel(batch_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "distributions.approve")
    return cancel_batch(session, principal.organization_id, batch_id)


@router.post("/payment-items/{item_id}/submission-evidence", response_model=EvidenceOut)
def post_submission_evidence(
    item_id: UUID,
    body: EvidenceBody,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session, scope="function"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    require_capability(principal, "distributions.approve")
    key = require_idempotency_key(idempotency_key)
    payload = {"reference": body.reference}
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", f"/v1/payment-items/{item_id}/submission-evidence", payload),
        create=lambda: record_submission_evidence(
            session,
            principal.organization_id,
            item_id,
            body.reference,
            request.app.state.clock.now(),
            principal.user_id,
            request_id_of(request),
        ),
    )
    return result


@router.post("/payment-items/{item_id}/settlement-evidence", response_model=EvidenceOut)
def post_settlement_evidence(
    item_id: UUID,
    body: EvidenceBody,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session, scope="function"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    require_capability(principal, "distributions.approve")
    if body.posting_date is None:
        problem(422, "VALIDATION_ERROR", "Settlement evidence needs a posting date.")
    key = require_idempotency_key(idempotency_key)
    payload = {"reference": body.reference, "posting_date": body.posting_date.isoformat()}
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", f"/v1/payment-items/{item_id}/settlement-evidence", payload),
        create=lambda: record_settlement_evidence(
            session,
            principal.organization_id,
            item_id,
            body.reference,
            body.posting_date,
            request.app.state.clock.now(),
            principal.user_id,
            request_id_of(request),
        ),
    )
    return result


@router.post("/distribution-items/{item_id}/returns", response_model=ReturnItemOut)
def post_return(item_id: UUID, body: PostingBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "distributions.approve")
    return record_return(session, principal.organization_id, item_id, body.posting_date)


@router.post("/statements", response_model=StatementIssuedOut, status_code=201)
def post_statement(body: StatementBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
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


@router.get("/statements", response_model=StatementPageOut)
def list_statements(principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
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


@router.get("/statements/{statement_id}", response_model=StatementOut)
def get_statement(statement_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
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


@router.post("/owner-links", response_model=OwnerLinkOut, status_code=201)
def post_owner_link(body: OwnerLinkBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
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
