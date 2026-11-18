from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import text

from grok_bot.db import set_tenant
from grok_bot.domain.accounting import _line, _lock_property, _post, allocate_receipt, apply_reserve_top_up, create_bank_account, create_deposit, create_receipt, make_available, verify_receipt
from grok_bot.domain.distributions import create_destination
from grok_bot.domain.portfolio import run_idempotent_create
from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.records import write_audit
from grok_bot.domain.stripe_client import StripeClient
from grok_bot.errors import problem


def snapshot(session, organization_id, settings) -> dict:
    properties = session.execute(text("SELECT s.*, p.name AS property_name FROM stripe_properties AS s JOIN properties AS p ON p.organization_id = s.organization_id AND p.id = s.property_id WHERE s.organization_id = :org ORDER BY p.name"), {"org": organization_id}).mappings().all()
    recipients = session.execute(text("SELECT s.*, p.display_name FROM stripe_recipients AS s JOIN parties AS p ON p.organization_id = s.organization_id AND p.id = s.party_id WHERE s.organization_id = :org ORDER BY p.display_name"), {"org": organization_id}).mappings().all()
    rents = session.execute(text("SELECT * FROM stripe_rents WHERE organization_id = :org ORDER BY created_at DESC, id DESC LIMIT 100"), {"org": organization_id}).mappings().all()
    jobs = session.execute(text("SELECT * FROM stripe_payout_jobs WHERE organization_id = :org ORDER BY created_at DESC, id DESC LIMIT 100"), {"org": organization_id}).mappings().all()
    return {
        "configured": settings.stripe_configured, "sandbox": True,
        "webhook_configured": settings.stripe_webhook_secret.get_secret_value().startswith("whsec_"),
        "worker_enabled": settings.stripe_worker_enabled and settings.stripe_configured, "fee_payer": "MANAGEMENT",
        "properties": [{"property_id": str(row["property_id"]), "property_name": row["property_name"], "bank_account_id": str(row["bank_account_id"])} for row in properties],
        "recipients": [{"party_id": str(row["party_id"]), "display_name": row["display_name"], "account_id": row["account_id"], "status": row["status"], "destination_id": str(row["destination_id"]) if row["destination_id"] else None} for row in recipients],
        "rents": [{key: str(row[key]) if isinstance(row[key], UUID) else row[key] for key in ("id", "property_id", "lease_id", "amount_cents", "status", "checkout_url", "fee_cents", "fee_due_cents")} for row in rents],
        "payouts": [{key: str(row[key]) if isinstance(row[key], UUID) else row[key] for key in ("id", "batch_id", "item_id", "amount_cents", "status", "transfer_id", "payout_id", "last_error")} for row in jobs],
    }


def register_property(session, principal, property_id, request_id) -> None:
    _lock_property(session, principal.organization_id, property_id)
    params = {"org": principal.organization_id, "property": property_id}
    if session.execute(text("SELECT 1 FROM simulated_bank_accounts WHERE organization_id = :org AND property_id = :property"), params).scalar():
        problem(409, "BANKING_MODE_CONFLICT", "Use a separate property for Stripe; simulated and Stripe funds cannot be mixed.")
    if session.execute(text("SELECT 1 FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), params).scalar():
        return
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"), {"scope": f"stripe-bank:{principal.organization_id}"})
    bank = session.execute(text("SELECT bank_account_id FROM stripe_properties WHERE organization_id = :org LIMIT 1"), params).scalar()
    if bank is None:
        bank = UUID(create_bank_account(session, principal.organization_id, "Stripe sandbox balance", "STRIPE TEST")["id"])
    session.execute(text("INSERT INTO stripe_properties (organization_id, property_id, bank_account_id) VALUES (:org, :property, :bank)"), {**params, "bank": bank})
    write_audit(session, organization_id=principal.organization_id, actor_id=principal.user_id, action="stripe.property_registered", target_type="property", target_id=property_id, target_version=None, request_id=request_id, before_state=None, after_state={"sandbox": True, "bank_account_id": str(bank)})


def onboard(session, principal, party_id, key, settings) -> dict:
    def create():
        party = session.execute(text("SELECT id FROM parties WHERE organization_id = :org AND id = :id"), {"org": principal.organization_id, "id": party_id}).scalar()
        if party is None:
            problem(404, "NOT_FOUND", "Payee not found.")
        recipient_id = session.execute(text("INSERT INTO stripe_recipients (id, organization_id, party_id, actor_id) VALUES (:id, :org, :party, :actor) ON CONFLICT (organization_id, party_id) DO UPDATE SET party_id = EXCLUDED.party_id RETURNING id"), {"id": uuid4(), "org": principal.organization_id, "party": party_id, "actor": principal.user_id}).scalar_one()
        return {"recipient_id": str(recipient_id), "operation_id": str(uuid4())}

    reserved, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/stripe/recipients", {"party_id": str(party_id)}), create=create)
    session.commit()
    set_tenant(session, principal.organization_id, principal.user_id)
    params = {"org": principal.organization_id, "id": UUID(reserved["recipient_id"])}
    row = session.execute(text("SELECT * FROM stripe_recipients WHERE organization_id = :org AND id = :id FOR UPDATE"), params).mappings().one()
    client = StripeClient(settings)
    account_id = row["account_id"]
    if account_id is None:
        if row["first_attempt_at"] and datetime.now(timezone.utc) - row["first_attempt_at"] >= timedelta(hours=23):
            problem(409, "STRIPE_RECONCILIATION_REQUIRED", "The account-creation attempt is too old to retry safely; reconcile it in Stripe first.")
        session.execute(text("UPDATE stripe_recipients SET first_attempt_at = coalesce(first_attempt_at, clock_timestamp()) WHERE organization_id = :org AND id = :id"), params)
        session.commit()
        set_tenant(session, principal.organization_id, principal.user_id)
        account = client.request("POST", "/accounts", idempotency_key=f"recipient:{row['id']}", data={
            "type": "express", "country": "US", "capabilities[transfers][requested]": "true",
            "settings[payouts][schedule][interval]": "manual", "metadata[organization_id]": str(principal.organization_id),
            "metadata[actor_id]": str(row["actor_id"]), "metadata[party_id]": str(party_id),
        })
        account_id = account["id"]
        session.execute(text("UPDATE stripe_recipients SET account_id = :account WHERE organization_id = :org AND id = :id"), {**params, "account": account_id})
        session.commit()
        set_tenant(session, principal.organization_id, principal.user_id)
    link = client.request("POST", "/account_links", idempotency_key=f"onboarding:{reserved['operation_id']}", data={"account": account_id, "type": "account_onboarding", "return_url": settings.stripe_public_url + "/stripe?onboarding=return", "refresh_url": settings.stripe_public_url + "/stripe?onboarding=refresh"})
    return {"onboarding_url": link["url"], "recipient_id": reserved["recipient_id"]}


def refresh_recipient(session, principal, party_id, settings) -> None:
    params = {"org": principal.organization_id, "party": party_id}
    row = session.execute(text("SELECT * FROM stripe_recipients WHERE organization_id = :org AND party_id = :party"), params).mappings().first()
    if row is None or row["account_id"] is None:
        problem(409, "STRIPE_ONBOARDING_REQUIRED", "Create the Stripe recipient first.")
    account = StripeClient(settings).request("GET", f"/accounts/{row['account_id']}")
    metadata = account.get("metadata", {})
    if metadata.get("organization_id") != str(principal.organization_id) or metadata.get("party_id") != str(party_id):
        problem(409, "STRIPE_ACCOUNT_MISMATCH", "The Stripe account does not match this payee.")
    banks = StripeClient(settings).request("GET", f"/accounts/{row['account_id']}/external_accounts", data={"object": "bank_account", "limit": 100})
    usable = [bank for bank in banks.get("data", []) if bank.get("currency") == "usd" and bank.get("default_for_currency")]
    ready = account.get("details_submitted") and account.get("payouts_enabled") and account.get("capabilities", {}).get("transfers") == "active" and len(usable) == 1 and account.get("settings", {}).get("payouts", {}).get("schedule", {}).get("interval") == "manual"
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"), {"scope": f"payee-destination:{principal.organization_id}:{party_id}"})
    row = session.execute(text("SELECT * FROM stripe_recipients WHERE organization_id = :org AND party_id = :party FOR UPDATE"), params).mappings().one()
    if not ready:
        session.execute(text("UPDATE stripe_recipients SET status = 'PENDING' WHERE organization_id = :org AND party_id = :party"), params)
        if row["destination_id"]:
            session.execute(text("UPDATE payee_destinations SET active = false WHERE organization_id = :org AND id = :id"), {"org": principal.organization_id, "id": row["destination_id"]})
        return
    destination_id = row["destination_id"]
    active = session.execute(text("SELECT active FROM payee_destinations WHERE organization_id = :org AND id = :id"), {"org": principal.organization_id, "id": destination_id}).scalar() if destination_id else False
    if usable[0]["id"] != row["external_bank_id"] or not active:
        destination_id = UUID(create_destination(session, principal.organization_id, party_id, f"Stripe ACH ····{usable[0]['last4']}", "STRIPE_ACH")["id"])
    session.execute(text("UPDATE stripe_recipients SET external_bank_id = :bank, destination_id = :destination, status = 'READY' WHERE organization_id = :org AND party_id = :party"), {**params, "bank": usable[0]["id"], "destination": destination_id})


def checkout(session, principal, body, key, settings) -> dict:
    def create():
        registered = session.execute(text("SELECT 1 FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": principal.organization_id, "property": body.property_id}).scalar()
        lease = session.execute(text("SELECT 1 FROM leases AS l JOIN units AS u ON u.organization_id = l.organization_id AND u.id = l.unit_id WHERE l.organization_id = :org AND l.id = :lease AND u.property_id = :property"), {"org": principal.organization_id, "lease": body.lease_id, "property": body.property_id}).scalar()
        if not registered or not lease:
            problem(409, "STRIPE_PROPERTY_REQUIRED", "Register the property and select one of its leases first.")
        rent_id = uuid4()
        session.execute(text("INSERT INTO stripe_rents (id, organization_id, property_id, lease_id, payer_party_id, actor_id, amount_cents, posting_date, reference) VALUES (:id, :org, :property, :lease, :payer, :actor, :amount, :date, :reference)"), {"id": rent_id, "org": principal.organization_id, "property": body.property_id, "lease": body.lease_id, "payer": body.payer_party_id, "actor": principal.user_id, "amount": body.amount_cents, "date": body.posting_date, "reference": body.reference})
        return {"rent_id": str(rent_id)}

    reserved, _status = run_idempotent_create(session, principal, key=key, hashed=request_hash("POST", "/v1/stripe/rents", body.model_dump(mode="json")), create=create)
    session.commit()
    set_tenant(session, principal.organization_id, principal.user_id)
    params = {"org": principal.organization_id, "id": UUID(reserved["rent_id"])}
    row = session.execute(text("SELECT * FROM stripe_rents WHERE organization_id = :org AND id = :id FOR UPDATE"), params).mappings().one()
    if row["checkout_url"]:
        return {"checkout_url": row["checkout_url"], "rent_id": reserved["rent_id"]}
    if row["first_attempt_at"] and datetime.now(timezone.utc) - row["first_attempt_at"] >= timedelta(hours=23):
        problem(409, "STRIPE_RECONCILIATION_REQUIRED", "The checkout attempt is too old to retry safely; reconcile it in Stripe first.")
    session.execute(text("UPDATE stripe_rents SET first_attempt_at = coalesce(first_attempt_at, clock_timestamp()) WHERE organization_id = :org AND id = :id"), params)
    session.commit()
    set_tenant(session, principal.organization_id, principal.user_id)
    session_data = {"mode": "payment", "payment_method_types[0]": "us_bank_account", "line_items[0][price_data][currency]": "usd", "line_items[0][price_data][unit_amount]": row["amount_cents"], "line_items[0][price_data][product_data][name]": "Rent payment", "line_items[0][quantity]": 1, "success_url": settings.stripe_public_url + "/stripe?checkout=complete", "cancel_url": settings.stripe_public_url + "/stripe?checkout=canceled"}
    for name, value in {"rent_id": row["id"], "organization_id": principal.organization_id, "actor_id": row["actor_id"]}.items():
        session_data[f"metadata[{name}]"] = str(value)
        session_data[f"payment_intent_data[metadata][{name}]"] = str(value)
    hosted = StripeClient(settings).request("POST", "/checkout/sessions", data=session_data, idempotency_key=f"rent:{row['id']}")
    session.execute(text("UPDATE stripe_rents SET checkout_id = :checkout, checkout_url = :url, status = 'CHECKOUT' WHERE organization_id = :org AND id = :id"), {**params, "checkout": hosted["id"], "url": hosted["url"]})
    return {"checkout_url": hosted["url"], "rent_id": reserved["rent_id"]}


def refresh_rent(session, principal, rent_id, posting_date, settings) -> None:
    params = {"org": principal.organization_id, "id": rent_id}
    row = session.execute(text("SELECT * FROM stripe_rents WHERE organization_id = :org AND id = :id"), params).mappings().first()
    if row is None or not row["checkout_id"]:
        problem(404, "NOT_FOUND", "Stripe rent checkout not found.")
    client = StripeClient(settings)
    hosted = client.request("GET", f"/checkout/sessions/{row['checkout_id']}")
    session.execute(text("UPDATE stripe_rents SET available_at = clock_timestamp() + interval '5 minutes' WHERE organization_id = :org AND id = :id"), params)
    if hosted.get("status") == "expired" and hosted.get("payment_status") != "paid":
        session.execute(text("UPDATE stripe_rents SET status = 'FAILED' WHERE organization_id = :org AND id = :id"), params)
        return
    intent_id = hosted.get("payment_intent")
    if not intent_id:
        return
    intent = client.request("GET", f"/payment_intents/{intent_id}", data={"expand[]": "latest_charge.balance_transaction"})
    metadata = intent.get("metadata", {})
    if metadata.get("rent_id") != str(rent_id) or metadata.get("organization_id") != str(principal.organization_id) or intent.get("currency") != "usd" or intent.get("amount") != row["amount_cents"]:
        problem(409, "STRIPE_PAYMENT_MISMATCH", "The Stripe payment does not match the saved rent instruction.")
    _lock_property(session, principal.organization_id, row["property_id"])
    row = session.execute(text("SELECT * FROM stripe_rents WHERE organization_id = :org AND id = :id FOR UPDATE"), params).mappings().one()
    charge = intent.get("latest_charge") or {}
    if charge.get("refunded") or charge.get("amount_refunded", 0) or charge.get("disputed"):
        session.execute(text("UPDATE properties SET disbursements_frozen = true WHERE organization_id = :org AND id IN (SELECT property_id FROM stripe_properties WHERE organization_id = :org)"), params)
        session.execute(text("UPDATE stripe_rents SET status = 'REVIEW' WHERE organization_id = :org AND id = :id"), params)
        return
    if row["receipt_id"]:
        return
    balance = charge.get("balance_transaction") or {}
    if intent.get("status") != "succeeded" or hosted.get("payment_status") != "paid" or balance.get("status") != "available" or balance.get("available_on", float("inf")) > datetime.now(timezone.utc).timestamp():
        session.execute(text("UPDATE stripe_rents SET status = 'PROCESSING', payment_intent_id = :intent WHERE organization_id = :org AND id = :id"), {**params, "intent": intent_id})
        return
    gross, fee, net = balance.get("amount"), balance.get("fee"), balance.get("net")
    if not all(type(value) is int for value in (gross, fee, net)) or gross != row["amount_cents"] or fee < 0 or net != gross - fee or net <= 0 or balance.get("currency") != "usd" or intent.get("amount_received") != gross:
        problem(409, "STRIPE_BALANCE_MISMATCH", "The settled Stripe balance and processing fees do not match this rent.")
    bank = session.execute(text("SELECT bank_account_id FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": principal.organization_id, "property": row["property_id"]}).scalar_one()
    unit = session.execute(text("SELECT unit_id FROM leases WHERE organization_id = :org AND id = :lease"), {"org": principal.organization_id, "lease": row["lease_id"]}).scalar_one()
    receipt = create_receipt(session, principal.organization_id, principal.user_id, {"property_id": row["property_id"], "unit_id": unit, "lease_id": row["lease_id"], "payer_party_id": row["payer_party_id"], "method": "STRIPE_ACH", "amount_cents": gross, "received_at": datetime.fromtimestamp(intent["created"], timezone.utc), "posting_date": posting_date, "reference": str(rent_id)}, f"stripe:{rent_id}")
    receipt_id = UUID(receipt["id"])
    create_deposit(session, principal.organization_id, {"property_id": row["property_id"], "bank_account_id": bank, "slip_reference": intent_id, "deposited_on": posting_date, "items": [{"receipt_id": receipt_id, "amount_cents": gross}]})
    verify_receipt(session, principal.organization_id, receipt_id, gross)
    make_available(session, principal.organization_id, receipt_id, gross, posting_date)
    allocate_receipt(session, principal.organization_id, principal.user_id, receipt_id, None, posting_date, f"stripe:{rent_id}")
    if fee:
        session.execute(text("SELECT app_ensure_stripe_chart(:org)"), {"org": principal.organization_id})
        consumed = session.execute(text("UPDATE funding_lots SET consumed_cents = consumed_cents + :fee WHERE organization_id = :org AND receipt_id = :receipt AND bank_account_id = :bank AND purpose = 'RENT' AND consumed_cents + reserved_cents + :fee <= amount_cents RETURNING id"), {"org": principal.organization_id, "receipt": receipt_id, "bank": bank, "fee": fee}).all()
        if len(consumed) != 1:
            problem(409, "STRIPE_FUNDING_MISMATCH", "The Stripe fee does not match exactly one receipt funding lot.")
        source = {"property_id": row["property_id"], "lease_id": row["lease_id"]}
        _post(session, principal.organization_id, "STRIPE_MANAGEMENT_FEE", rent_id, posting_date, [_line("1050", "DEBIT", fee, source, "RENT"), _line("1030", "CREDIT", fee, source, "RENT", bank_account_id=bank)])
    session.execute(text("UPDATE stripe_rents SET receipt_id = :receipt, payment_intent_id = :intent, fee_cents = :fee, fee_due_cents = :fee, status = 'AVAILABLE' WHERE organization_id = :org AND id = :id"), {**params, "receipt": receipt_id, "intent": intent_id, "fee": fee})
    due = session.execute(text("SELECT sum(fee_due_cents) FROM stripe_rents WHERE organization_id = :org AND property_id = :property"), {"org": principal.organization_id, "property": row["property_id"]}).scalar()
    if not due:
        apply_reserve_top_up(session, principal.organization_id, row["property_id"], posting_date)


def reimburse_fee(session, principal, rent_id, topup_id, posting_date, settings) -> None:
    params = {"org": principal.organization_id, "id": rent_id}
    row = session.execute(text("SELECT * FROM stripe_rents WHERE organization_id = :org AND id = :id"), params).mappings().first()
    if row is None or not row["fee_due_cents"]:
        problem(409, "NO_FEE_DUE", "This rent has no processing-fee reimbursement due.")
    client = StripeClient(settings)
    topup = client.request("GET", f"/topups/{topup_id}", data={"expand[]": "balance_transaction"})
    metadata = topup.get("metadata", {})
    if metadata.get("organization_id") != str(principal.organization_id) or metadata.get("rent_id") != str(rent_id) or metadata.get("purpose") != "management_processing_fee":
        problem(409, "STRIPE_TOPUP_OWNERSHIP_REQUIRED", "The management top-up must identify this organization, rent, and management_processing_fee purpose in Stripe metadata.")
    balance = topup.get("balance_transaction") or {}
    if topup.get("status") != "succeeded" or topup.get("currency") != "usd" or topup.get("amount") != row["fee_due_cents"] or balance.get("status") != "available" or balance.get("currency") != "usd" or balance.get("available_on", float("inf")) > datetime.now(timezone.utc).timestamp() or balance.get("net") != row["fee_due_cents"]:
        problem(409, "STRIPE_TOPUP_MISMATCH", "Use a cleared management top-up whose net amount exactly equals this processing fee.")
    _lock_property(session, principal.organization_id, row["property_id"])
    row = session.execute(text("SELECT * FROM stripe_rents WHERE organization_id = :org AND id = :id FOR UPDATE"), params).mappings().one()
    if not row["fee_due_cents"]:
        return
    bank = session.execute(text("SELECT bank_account_id FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": principal.organization_id, "property": row["property_id"]}).scalar_one()
    amount = row["fee_due_cents"]
    source = {"property_id": row["property_id"], "lease_id": row["lease_id"]}
    _post(session, principal.organization_id, "STRIPE_FEE_REIMBURSEMENT", rent_id, posting_date, [_line("1030", "DEBIT", amount, source, "RENT", bank_account_id=bank), _line("1050", "CREDIT", amount, source, "RENT")])
    session.execute(text("INSERT INTO funding_lots (id, organization_id, property_id, bank_account_id, purpose, amount_cents, source_type, source_id) VALUES (:lot, :org, :property, :bank, 'RENT', :amount, 'STRIPE_FEE_REIMBURSEMENT', :id)"), {**params, "lot": uuid4(), "property": row["property_id"], "bank": bank, "amount": amount})
    session.execute(text("UPDATE stripe_rents SET topup_id = :topup, fee_due_cents = 0 WHERE organization_id = :org AND id = :id"), {**params, "topup": topup_id})
    due = session.execute(text("SELECT sum(fee_due_cents) FROM stripe_rents WHERE organization_id = :org AND property_id = :property"), {"org": principal.organization_id, "property": row["property_id"]}).scalar()
    if not due:
        apply_reserve_top_up(session, principal.organization_id, row["property_id"], posting_date)
