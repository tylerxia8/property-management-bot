import asyncio
from collections import deque
from datetime import date
from threading import Lock
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from grok_bot.api.deps import get_principal, get_session, require_capability, require_idempotency_key, request_id_of
from grok_bot.api.success import APIModel, ERROR_RESPONSES
from grok_bot.auth.permissions import Principal
from grok_bot.db import set_tenant
from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.portfolio import run_idempotent_create
from grok_bot.domain.stripe_banking import checkout, onboard, refresh_recipient, refresh_rent, register_property, reimburse_fee, snapshot
from grok_bot.domain.stripe_client import StripeClient, verify_webhook
from grok_bot.errors import problem

router = APIRouter(responses=ERROR_RESPONSES)
webhook_times = deque(maxlen=120)
webhook_lock = Lock()


class PropertyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID


class RecipientBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party_id: UUID


class RentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    lease_id: UUID
    payer_party_id: UUID
    amount_cents: int = Field(gt=0, le=10**12)
    posting_date: date
    reference: str = Field(min_length=1, max_length=80, pattern=r"\S")


class RefreshBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_date: date


class ReimbursementBody(RefreshBody):
    topup_id: str = Field(pattern=r"^tu_[A-Za-z0-9]+$")


class StripePropertyOut(APIModel):
    property_id: str
    property_name: str
    bank_account_id: str


class StripeRecipientOut(APIModel):
    party_id: str
    display_name: str
    account_id: str | None
    status: str
    destination_id: str | None


class StripeRentOut(APIModel):
    id: str
    property_id: str
    lease_id: str
    amount_cents: int
    status: str
    checkout_url: str | None
    fee_cents: int
    fee_due_cents: int


class StripePayoutOut(APIModel):
    id: str
    batch_id: str
    item_id: str
    amount_cents: int
    status: str
    transfer_id: str | None
    payout_id: str | None
    last_error: str | None


class StripeOut(APIModel):
    configured: bool
    sandbox: bool
    webhook_configured: bool
    worker_enabled: bool
    fee_payer: str
    properties: list[StripePropertyOut]
    recipients: list[StripeRecipientOut]
    rents: list[StripeRentOut]
    payouts: list[StripePayoutOut]


class OnboardingOut(APIModel):
    onboarding_url: str
    recipient_id: str


class CheckoutOut(APIModel):
    checkout_url: str
    rent_id: str


class StripeWebhookOut(APIModel):
    accepted: bool
    sandbox: bool


@router.get("/stripe", response_model=StripeOut)
def get_stripe(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    if not (principal.allows("receipts.read") or principal.allows("distributions.approve")):
        problem(403, "FORBIDDEN", "You do not have access to Stripe payments.")
    return snapshot(session, principal.organization_id, request.app.state.settings)


@router.post("/stripe/properties", response_model=StripeOut)
def post_property(body: PropertyBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    key = require_idempotency_key(idempotency_key)

    def create():
        register_property(session, principal, body.property_id, request_id_of(request))
        return snapshot(session, principal.organization_id, request.app.state.settings)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/stripe/properties", body.model_dump(mode="json")), create=create)
    return result


@router.post("/stripe/recipients", response_model=OnboardingOut)
def post_recipient(body: RecipientBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    if not request.app.state.settings.stripe_configured:
        problem(409, "STRIPE_SANDBOX_NOT_CONFIGURED", "Configure a Stripe test secret key on the server first.")
    return onboard(session, principal, body.party_id, require_idempotency_key(idempotency_key), request.app.state.settings)


@router.post("/stripe/recipients/{party_id}/refresh", response_model=StripeOut)
def post_recipient_refresh(party_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "distributions.approve")
    key = require_idempotency_key(idempotency_key)

    def create():
        refresh_recipient(session, principal, party_id, request.app.state.settings)
        return snapshot(session, principal.organization_id, request.app.state.settings)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", f"/v1/stripe/recipients/{party_id}/refresh", {}), create=create)
    return result


@router.post("/stripe/rents", response_model=CheckoutOut)
def post_rent(body: RentBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "receipts.write")
    require_capability(principal, "allocations.write")
    if not request.app.state.settings.stripe_configured:
        problem(409, "STRIPE_SANDBOX_NOT_CONFIGURED", "Configure a Stripe test secret key on the server first.")
    return checkout(session, principal, body, require_idempotency_key(idempotency_key), request.app.state.settings)


@router.post("/stripe/rents/{rent_id}/refresh", response_model=StripeOut)
def post_rent_refresh(rent_id: UUID, body: RefreshBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "allocations.write")
    key = require_idempotency_key(idempotency_key)

    def create():
        refresh_rent(session, principal, rent_id, body.posting_date, request.app.state.settings)
        return snapshot(session, principal.organization_id, request.app.state.settings)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", f"/v1/stripe/rents/{rent_id}/refresh", body.model_dump(mode="json")), create=create)
    return result


@router.post("/stripe/rents/{rent_id}/reimburse-fee", response_model=StripeOut)
def post_reimbursement(rent_id: UUID, body: ReimbursementBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function"), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    require_capability(principal, "allocations.write")
    key = require_idempotency_key(idempotency_key)

    def create():
        reimburse_fee(session, principal, rent_id, body.topup_id, body.posting_date, request.app.state.settings)
        return snapshot(session, principal.organization_id, request.app.state.settings)

    result, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", f"/v1/stripe/rents/{rent_id}/reimburse-fee", body.model_dump(mode="json")), create=create)
    return result


@router.post("/stripe/webhook", response_model=StripeWebhookOut, status_code=202)
async def stripe_webhook(request: Request, session: Session = Depends(get_session, scope="function")):
    now = monotonic()
    with webhook_lock:
        if len(webhook_times) == webhook_times.maxlen and now - webhook_times[0] < 60:
            problem(429, "RATE_LIMITED", "Retry this webhook later.", retryable=True)
        webhook_times.append(now)
    body = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 1024 * 1024:
                    problem(413, "WEBHOOK_TOO_LARGE", "The webhook exceeds the accepted size.")
    except TimeoutError:
        problem(408, "WEBHOOK_TIMEOUT", "The webhook body did not arrive in time.")
    settings = request.app.state.settings
    if not settings.stripe_configured or not settings.stripe_webhook_secret.get_secret_value():
        problem(409, "STRIPE_WEBHOOK_NOT_CONFIGURED", "The Stripe sandbox webhook is not configured.")
    event = verify_webhook(bytes(body), request.headers.get("stripe-signature"), settings.stripe_webhook_secret.get_secret_value(), request.app.state.clock.now())
    obj = event["data"]["object"]
    metadata = obj.get("metadata") or {}
    if event["type"].startswith("charge.dispute.") and obj.get("charge"):
        charge = await run_in_threadpool(StripeClient(settings).request, "GET", f"/charges/{obj['charge']}")
        metadata = charge.get("metadata") or {}
    target = metadata.get("rent_id") or metadata.get("job_id") or metadata.get("party_id")
    if target is None:
        return {"accepted": True, "sandbox": True}
    try:
        organization_id = UUID(metadata["organization_id"])
        object_id = UUID(target)
    except (ValueError, KeyError, TypeError):
        problem(422, "STRIPE_EVENT_METADATA_INVALID", "The event has no valid application mapping.")
    actor_id = session.execute(text("SELECT app_stripe_service_actor(:org)"), {"org": organization_id}).scalar()
    if actor_id is None:
        problem(409, "STRIPE_SERVICE_ACTOR_REQUIRED", "An active staff account is required to process this organization's Stripe events.")
    set_tenant(session, organization_id, actor_id)
    if not isinstance(obj.get("id"), str):
        problem(422, "STRIPE_EVENT_OBJECT_INVALID", "The event has no provider object ID.")
    session.execute(text("INSERT INTO stripe_webhook_events (id, organization_id, actor_id, object_id, provider_object_id, event_type) VALUES (:id, :org, :actor, :object, :provider_object, :type) ON CONFLICT (id) DO NOTHING"), {"id": event["id"], "org": organization_id, "actor": actor_id, "object": str(object_id), "provider_object": obj["id"], "type": event["type"]})
    return {"accepted": True, "sandbox": True}
