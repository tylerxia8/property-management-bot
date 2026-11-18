from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, request_id_of, require_capability, require_idempotency_key
from grok_bot.api.success import APIModel, BatchOut, ERROR_RESPONSES, StepUpOut
from grok_bot.auth.permissions import Principal
from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.portfolio import run_idempotent_create
from grok_bot.domain.simulated_bank import create_account, receive_rent, reconcile, set_outcome, setup_demo, snapshot
from grok_bot.errors import problem

router = APIRouter(responses=ERROR_RESPONSES)


class AccountBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID


class OutcomeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["settle", "timeout", "fail"]


class RentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
    lease_id: UUID
    payer_party_id: UUID
    amount_cents: int = Field(gt=0, le=10**12)
    channel: Literal["ZELLE", "VENMO"]
    posting_date: date
    reference: str = Field(min_length=1, max_length=80, pattern=r"\S")


class ReconcileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_date: date


class SimulatedAccountOut(APIModel):
    id: str
    property_id: str
    property_name: str
    balance_cents: int
    next_outcome: Literal["settle", "timeout", "fail"]


class SimulatedTransactionOut(APIModel):
    id: str
    account_id: str
    kind: Literal["RECEIPT", "PAYOUT"]
    channel: Literal["ZELLE", "VENMO"]
    amount_cents: int
    status: Literal["SETTLED", "FAILED"]
    reference: str
    created_at: str
    item_id: str | None
    receipt_id: str | None


class SimulatedBankOut(APIModel):
    simulator: Literal[True]
    bank_contacted: Literal[False]
    enabled: bool
    accounts: list[SimulatedAccountOut]
    transactions: list[SimulatedTransactionOut]
    batches: list[BatchOut]


@router.post("/simulated-bank/step-up", response_model=StepUpOut)
def simulated_step_up(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    if not request.app.state.settings.allows_demo_session:
        problem(409, "STEP_UP_REQUIRED", "Use local password verification outside the fictional demo.")
    from grok_bot.domain.distributions import record_step_up

    key = require_idempotency_key(idempotency_key)

    def create():
        proof = record_step_up(session, principal.organization_id, principal.user_id, request.app.state.clock.now(), "SIMULATED_APPROVAL")
        return {**proof, "request_id": request_id_of(request)}

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/simulated-bank/step-up", {}), create=create)
    return result


@router.get("/simulated-bank", response_model=SimulatedBankOut)
def get_bank(principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    if not (principal.allows("receipts.read") or principal.allows("distributions.approve")):
        problem(403, "FORBIDDEN", "You do not have access to the simulated bank.")
    return snapshot(session, principal.organization_id)


@router.post("/simulated-bank/accounts", response_model=SimulatedBankOut)
def post_account(body: AccountBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    key = require_idempotency_key(idempotency_key)

    def create():
        create_account(session, principal, body.property_id, request_id_of(request))
        return snapshot(session, principal.organization_id)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/simulated-bank/accounts", body.model_dump(mode="json")), create=create)
    return result


@router.post("/simulated-bank/demo-setup", response_model=SimulatedBankOut)
def demo_setup(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    if not request.app.state.settings.allows_demo_session:
        problem(404, "NOT_FOUND", "Fictional setup is unavailable outside the sample demo.")
    key = require_idempotency_key(idempotency_key)

    def create():
        setup_demo(session, principal, request_id_of(request))
        return snapshot(session, principal.organization_id)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/simulated-bank/demo-setup", {}), create=create)
    return result


@router.post("/simulated-bank/accounts/{account_id}/outcome", response_model=SimulatedBankOut)
def post_outcome(account_id: UUID, body: OutcomeBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    key = require_idempotency_key(idempotency_key)

    def create():
        set_outcome(session, principal, account_id, body.outcome, request_id_of(request))
        return snapshot(session, principal.organization_id)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", f"/v1/simulated-bank/accounts/{account_id}/outcome", body.model_dump(mode="json")), create=create)
    return result


@router.post("/simulated-bank/receipts", response_model=SimulatedBankOut)
def post_rent(body: RentBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "receipts.write")
    require_capability(principal, "allocations.write")
    key = require_idempotency_key(idempotency_key)

    def create():
        receive_rent(session, principal, body, request.app.state.clock.now(), request_id_of(request))
        return snapshot(session, principal.organization_id)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/simulated-bank/receipts", body.model_dump(mode="json")), create=create)
    return result


@router.post("/simulated-bank/batches/{batch_id}/reconcile", response_model=SimulatedBankOut)
def post_reconcile(batch_id: UUID, body: ReconcileBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    key = require_idempotency_key(idempotency_key)

    def create():
        reconcile(session, principal.organization_id, batch_id, body.posting_date)
        return snapshot(session, principal.organization_id)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", f"/v1/simulated-bank/batches/{batch_id}/reconcile", body.model_dump(mode="json")), create=create)
    return result
