from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import text
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, request_id_of, require_capability, require_idempotency_key
from grok_bot.auth.permissions import Principal
from grok_bot.domain.accounting import (
    allocate_receipt,
    apply_reserve_top_up,
    approve_invoice,
    close_period,
    close_reconciliation,
    create_bank_account,
    create_deposit,
    create_lease,
    create_party,
    create_receipt,
    create_rent_charge,
    declare_distributions,
    draft_reconciliation,
    get_receipt,
    import_bank_transactions,
    make_available,
    opening_reserve_cash,
    property_balances,
    publish_agreement,
    publish_ownership,
    settle_declaration,
    settle_fee,
    settle_invoice,
    submit_invoice,
    verify_receipt,
)
from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.portfolio import run_idempotent_create
from grok_bot.errors import problem
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()


class PartyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(person|company)$")


class BankAccountBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str
    masked_label: str


class LeaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_id: UUID
    start_date: date
    end_date: date
    agreed_rent_cents: int = Field(ge=0)


class ShareBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_party_id: UUID
    weight: int = Field(gt=0)


class OwnershipBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    shares: list[ShareBody]


class AgreementBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    responsibility_mode: str = "OWNERSHIP_WEIGHTS"
    rate_numerator: int = Field(ge=0)
    rate_denominator: int = Field(gt=0)
    fixed_cents: int = Field(default=0, ge=0)
    cap_cents: int | None = Field(default=None, ge=0)
    minimum_cents: int | None = Field(default=None, ge=0)
    reserve_target_total_cents: int | None = Field(default=None, ge=0)


class ReceiptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    unit_id: UUID
    lease_id: UUID
    payer_party_id: UUID
    method: str
    amount_cents: int = Field(gt=0)
    currency: str = "USD"
    received_at: datetime
    posting_date: date
    reference: str = Field(min_length=1, max_length=80)
    service_period: str | None = None


class DepositItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: UUID
    amount_cents: int = Field(gt=0)


class DepositBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    bank_account_id: UUID
    slip_reference: str
    deposited_on: date
    items: list[DepositItem]


class AmountDateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_cents: int = Field(gt=0)
    posting_date: date | None = None


class AllocationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_cents: int | None = Field(default=None, gt=0)
    posting_date: date


class OpeningReserveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    bank_account_id: UUID
    owner_party_id: UUID
    amount_cents: int = Field(gt=0)
    posting_date: date
    reason: str


class RentChargeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_id: UUID
    due_on: date
    amount_cents: int = Field(gt=0)
    description: str


class InvoiceLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    quantity: int = Field(gt=0)
    unit_price_cents: int = Field(ge=0)
    line_total_cents: int = Field(ge=0)


class InvoiceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    contractor_party_id: UUID
    invoice_number: str
    currency: str = "USD"
    tax_cents: int = Field(ge=0)
    total_cents: int = Field(gt=0)
    lines: list[InvoiceLineBody]


class PostingDateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_date: date


class FeeSettlementBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    amount_cents: int = Field(gt=0)
    posting_date: date


class BankTransactionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank_account_id: UUID
    external_id: str
    amount_cents: int
    posted_on: date


class BankImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str | None = None
    csv_text: str | None = None
    transactions: list[BankTransactionBody] = Field(default_factory=list)


class ReconciliationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank_account_id: UUID
    period_start: date
    period_end: date
    statement_opening_cents: int
    statement_closing_cents: int
    timing_item_cents: int = 0


class PeriodCloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_start: date
    period_end: date
    reason: str


def _idempotent(session, principal, key, method, path, payload, create):
    hashed = request_hash(method, path, payload)
    body, replay = run_idempotent_create(session, principal, key=key, hashed=hashed, create=create)
    body = dict(body)
    body["request_id"] = payload.get("request_id", body.get("request_id"))
    return body, replay


@router.post("/parties")
def post_party(body: PartyBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "parties.write")
    key = require_idempotency_key(idempotency_key)
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/parties", body.model_dump(mode="json")),
        create=lambda: {**create_party(session, principal.organization_id, body.display_name, body.kind), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/bank-accounts")
def post_bank(body: BankAccountBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "bank_accounts.write")
    key = require_idempotency_key(idempotency_key)
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/bank-accounts", body.model_dump(mode="json")),
        create=lambda: {**create_bank_account(session, principal.organization_id, body.display_name, body.masked_label), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/leases")
def post_lease(body: LeaseBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "leases.write")
    key = require_idempotency_key(idempotency_key)
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/leases", body.model_dump(mode="json")),
        create=lambda: {**create_lease(session, principal.organization_id, body.unit_id, body.start_date, body.end_date, body.agreed_rent_cents), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/properties/{property_id}/ownership-periods")
def post_ownership(property_id: UUID, body: OwnershipBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "ownership.write")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", f"/v1/properties/{property_id}/ownership-periods", payload),
        create=lambda: {**publish_ownership(session, principal.organization_id, property_id, body.start_date, body.end_date, payload["shares"]), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/properties/{property_id}/agreements")
def post_agreement(property_id: UUID, body: AgreementBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "agreements.write")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", f"/v1/properties/{property_id}/agreements", payload),
        create=lambda: {**publish_agreement(session, principal.organization_id, property_id, payload), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/receipts")
def post_receipt(body: ReceiptBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "receipts.write")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/receipts", payload),
        create=lambda: create_receipt(session, principal.organization_id, principal.user_id, _with_ids(payload), request_id_of(request)),
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/receipts/{receipt_id}")
def get_receipt_route(receipt_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "receipts.read")
    return get_receipt(session, principal.organization_id, receipt_id)


@router.post("/deposit-batches")
def post_deposit(body: DepositBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "deposits.write")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/deposit-batches", payload),
        create=lambda: {**create_deposit(session, principal.organization_id, _with_ids(payload)), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/receipts/{receipt_id}/bank-verification")
def post_verification(receipt_id: UUID, body: AmountDateBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "availability.write")
    return verify_receipt(session, principal.organization_id, receipt_id, body.amount_cents)


@router.post("/receipts/{receipt_id}/availability")
def post_availability(receipt_id: UUID, body: AmountDateBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "availability.write")
    if body.posting_date is None:
        problem(422, "VALIDATION_ERROR", "posting_date is required.")
    return make_available(session, principal.organization_id, receipt_id, body.amount_cents, body.posting_date)


@router.post("/receipts/{receipt_id}/allocations")
def post_allocation(receipt_id: UUID, body: AllocationBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "allocations.write")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", f"/v1/receipts/{receipt_id}/allocations", payload),
        create=lambda: allocate_receipt(session, principal.organization_id, principal.user_id, receipt_id, body.amount_cents, body.posting_date, request_id_of(request)),
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/opening-entries/reserve-cash")
def post_opening(body: OpeningReserveBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "opening_entries.write")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/opening-entries/reserve-cash", payload),
        create=lambda: {**opening_reserve_cash(session, principal.organization_id, _with_ids(payload)), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/properties/{property_id}/reserve-top-ups")
def post_top_up(property_id: UUID, body: PostingDateBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "reserves.apply")
    return apply_reserve_top_up(session, principal.organization_id, property_id, body.posting_date)


@router.post("/rent-charges")
def post_charge(body: RentChargeBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "rent_charges.write")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/rent-charges", payload),
        create=lambda: {**create_rent_charge(session, principal.organization_id, _with_ids(payload)), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/invoices")
def post_invoice(body: InvoiceBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "invoices.submit")
    if body.currency != "USD":
        problem(422, "UNSUPPORTED_CURRENCY", "Only USD cents are supported.")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/invoices", payload),
        create=lambda: {**submit_invoice(session, principal.organization_id, _with_ids(payload)), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/invoices/{invoice_id}/approve")
def post_approve(invoice_id: UUID, body: PostingDateBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "invoices.approve")
    return approve_invoice(session, principal.organization_id, invoice_id, body.posting_date)


def require_fixture_ledger_settlement(request: Request) -> None:
    del request
    problem(
        409,
        "APPROVAL_CONTRACT_REQUIRED",
        "Clearing a payable requires an approved distribution snapshot. The fixture settlement flag does not bypass that.",
    )


@router.post("/properties/{property_id}/distribution-declarations")
def post_declare(property_id: UUID, body: PostingDateBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_fixture_ledger_settlement(request)
    require_capability(principal, "distributions.declare")
    return declare_distributions(session, principal.organization_id, property_id, body.posting_date)


@router.post("/invoices/{invoice_id}/simulated-settlement")
def post_invoice_settlement(invoice_id: UUID, body: PostingDateBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_fixture_ledger_settlement(request)
    require_capability(principal, "settlements.simulate")
    return settle_invoice(session, principal.organization_id, invoice_id, body.posting_date)


@router.post("/fee-settlements/simulated")
def post_fee_settlement(body: FeeSettlementBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_fixture_ledger_settlement(request)
    require_capability(principal, "settlements.simulate")
    return settle_fee(session, principal.organization_id, body.property_id, body.amount_cents, body.posting_date)


@router.post("/distribution-declarations/{declaration_id}/simulated-settlement")
def post_distribution_settlement(declaration_id: UUID, body: PostingDateBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_fixture_ledger_settlement(request)
    require_capability(principal, "settlements.simulate")
    return settle_declaration(session, principal.organization_id, declaration_id, body.posting_date)


@router.post("/bank-imports")
def post_import(body: BankImportBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "bank_imports.write")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump(mode="json")
    result, _status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=request_hash("POST", "/v1/bank-imports", payload),
        create=lambda: {**import_bank_transactions(session, principal.organization_id, _with_ids(payload)), "request_id": request_id_of(request)},
    )
    return JSONResponse(status_code=201, content=result)


@router.post("/reconciliations")
def post_reconciliation(body: ReconciliationBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "reconciliations.write")
    return draft_reconciliation(session, principal.organization_id, body.model_dump(mode="json"))


@router.post("/reconciliations/{reconciliation_id}/close")
def post_close_reconciliation(reconciliation_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "reconciliations.write")
    return close_reconciliation(session, principal.organization_id, reconciliation_id)


@router.post("/period-closes")
def post_period_close(body: PeriodCloseBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "period_closes.write")
    return close_period(session, principal.organization_id, body.period_start, body.period_end, body.reason)


@router.get("/parties")
def list_parties(principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "receipts.read")
    rows = session.execute(
        text("SELECT id, display_name, kind FROM parties WHERE organization_id = :organization_id ORDER BY display_name"),
        {"organization_id": principal.organization_id},
    ).mappings().all()
    return {"items": [{"id": str(row["id"]), "display_name": row["display_name"], "kind": row["kind"]} for row in rows]}


@router.get("/units/{unit_id}/leases")
def list_leases(unit_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "receipts.read")
    rows = session.execute(
        text(
            """
            SELECT id, agreed_rent_cents FROM leases
            WHERE organization_id = :organization_id AND unit_id = :unit_id
            ORDER BY start_date
            """
        ),
        {"organization_id": principal.organization_id, "unit_id": unit_id},
    ).mappings().all()
    return {"items": [{"id": str(row["id"]), "agreed_rent_cents": row["agreed_rent_cents"]} for row in rows]}


@router.get("/properties/{property_id}/balances")
def get_balances(property_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "ledger.read")
    return property_balances(session, principal.organization_id, property_id)


def _with_ids(payload: dict):
    converted = {}
    for key, value in payload.items():
        if key.endswith("_id") and key != "external_id" and isinstance(value, str):
            converted[key] = UUID(value)
        elif key == "items" and isinstance(value, list):
            converted[key] = [_with_ids(item) for item in value]
        elif key == "transactions" and isinstance(value, list):
            converted[key] = [_with_ids(item) for item in value]
        elif key == "lines" and isinstance(value, list):
            converted[key] = value
        elif key in {"received_at", "posting_date", "deposited_on", "start_date", "end_date", "due_on", "posted_on", "period_start", "period_end"} and isinstance(value, str):
            converted[key] = date.fromisoformat(value[:10]) if key != "received_at" else datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            converted[key] = value
    return converted
