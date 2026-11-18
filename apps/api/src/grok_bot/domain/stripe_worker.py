import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.db import set_tenant
from grok_bot.auth.permissions import Principal
from grok_bot.domain.controls import outbound_flags
from grok_bot.domain.distributions import _items, _lock_batch, _refresh_status, _require_current_approval, _settle_item
from grok_bot.domain.accounting import _lock_property
from grok_bot.domain.stripe_client import StripeClient, StripeError
from grok_bot.domain.stripe_banking import refresh_rent, refresh_recipient
from grok_bot.errors import problem

logger = logging.getLogger(__name__)


def queue_batch(session, principal, batch_id, approval_id, posting_date, settings, now) -> None:
    if not settings.stripe_configured or not settings.stripe_worker_enabled:
        problem(409, "STRIPE_WORKER_DISABLED", "Configure the Stripe sandbox and enable its payout worker before approving Stripe payments.")
    if not settings.stripe_webhook_secret.get_secret_value().startswith("whsec_"):
        problem(409, "STRIPE_WEBHOOK_NOT_CONFIGURED", "Configure signed Stripe webhooks before enabling payout automation.")
    if not outbound_flags(session, principal.organization_id)["payment_enabled"]:
        problem(409, "KILL_SWITCH", "Automatic payout sending is switched off.")
    batch = _require_current_approval(session, principal.organization_id, batch_id, now)
    bank = session.execute(text("SELECT bank_account_id FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": principal.organization_id, "property": batch["property_id"]}).scalar_one()
    for item in _items(session, principal.organization_id, batch_id):
        if item["status"] == "SETTLED":
            continue
        recipient = session.execute(text("SELECT * FROM stripe_recipients WHERE organization_id = :org AND party_id = :party AND status = 'READY' AND destination_id = :destination"), {"org": principal.organization_id, "party": item["recipient_party_id"], "destination": item["destination_id"]}).mappings().first()
        if recipient is None or item["channel"] != "STRIPE_ACH":
            problem(409, "STRIPE_ONBOARDING_REQUIRED", "Every Stripe payout needs a fully onboarded recipient and the reviewed Stripe bank destination.")
        backed = session.execute(text("SELECT coalesce(sum(r.amount_cents), 0) FROM fund_reservations AS r JOIN funding_lots AS l ON l.organization_id = r.organization_id AND l.id = r.funding_lot_id WHERE r.organization_id = :org AND r.item_id = :item AND r.status = 'ACTIVE' AND l.bank_account_id = :bank"), {"org": principal.organization_id, "item": item["id"], "bank": bank}).scalar()
        if int(backed) != item["amount_cents"]:
            problem(409, "STRIPE_FUNDS_REQUIRED", "Stripe payouts must be fully funded by cleared Stripe rent and management reimbursements.")
        session.execute(text("INSERT INTO stripe_payout_jobs (id, organization_id, actor_id, item_id, batch_id, approval_id, account_id, external_bank_id, amount_cents, posting_date) VALUES (:id, :org, :actor, :item, :batch, :approval, :account, :bank, :amount, :date) ON CONFLICT (organization_id, item_id) DO NOTHING"), {"id": uuid4(), "org": principal.organization_id, "actor": principal.user_id, "item": item["id"], "batch": batch_id, "approval": approval_id, "account": recipient["account_id"], "bank": recipient["external_bank_id"], "amount": item["amount_cents"], "date": posting_date})
        session.execute(text("UPDATE distribution_items SET status = 'UNKNOWN' WHERE organization_id = :org AND id = :item"), {"org": principal.organization_id, "item": item["id"]})
    _refresh_status(session, principal.organization_id, batch_id)


def run_pending(engine, settings, organization_id, actor_id) -> None:
    if not settings.stripe_configured or not settings.stripe_worker_enabled:
        return
    with Session(engine) as session:
        set_tenant(session, organization_id, actor_id)
        ids = session.execute(text("SELECT id FROM stripe_payout_jobs WHERE organization_id = :org AND status NOT IN ('SETTLED', 'FAILED', 'BLOCKED') AND available_at <= clock_timestamp() ORDER BY created_at LIMIT 50"), {"org": organization_id}).scalars().all()
    for job_id in ids:
        try:
            _run_job(engine, settings, organization_id, actor_id, job_id)
        except (StripeError, HTTPException) as exc:
            code = exc.code if isinstance(exc, StripeError) else exc.detail.get("code", "STRIPE_REVIEW_REQUIRED")
            with Session(engine) as session:
                set_tenant(session, organization_id, actor_id)
                session.execute(text("UPDATE stripe_payout_jobs SET lease_until = NULL, status = CASE WHEN :blocked THEN 'BLOCKED' ELSE 'UNKNOWN' END, last_error = :error, available_at = clock_timestamp() + interval '60 seconds' WHERE organization_id = :org AND id = :id AND status != 'SETTLED'"), {"org": organization_id, "id": job_id, "error": code, "blocked": isinstance(exc, HTTPException)})
                session.commit()
            logger.warning("stripe_payout_needs_review", extra={"job_id": str(job_id), "organization_id": str(organization_id), "error_code": code})
        except Exception:
            with Session(engine) as session:
                set_tenant(session, organization_id, actor_id)
                session.execute(text("UPDATE stripe_payout_jobs SET status = 'BLOCKED', lease_until = NULL, last_error = 'STRIPE_INTERNAL_REVIEW_REQUIRED' WHERE organization_id = :org AND id = :id AND status != 'SETTLED'"), {"org": organization_id, "id": job_id})
                session.commit()
            logger.error("stripe_worker_failed", extra={"job_id": str(job_id), "organization_id": str(organization_id)})


def _run_job(engine, settings, organization_id, actor_id, job_id) -> None:
    now = datetime.now(timezone.utc)
    params = {"org": organization_id, "id": job_id}
    with Session(engine) as session:
        set_tenant(session, organization_id, actor_id)
        row = session.execute(text("SELECT * FROM stripe_payout_jobs WHERE organization_id = :org AND id = :id AND (lease_until IS NULL OR lease_until < clock_timestamp()) FOR UPDATE SKIP LOCKED"), params).mappings().first()
        if row is None or row["status"] in {"SETTLED", "FAILED", "BLOCKED"}:
            return
        job = dict(row)
        session.execute(text("UPDATE stripe_payout_jobs SET lease_until = clock_timestamp() + interval '5 minutes', attempt_count = attempt_count + 1 WHERE organization_id = :org AND id = :id"), params)
        session.commit()
    if not job["transfer_id"] and not job["transfer_attempt_at"]:
        with Session(engine) as session:
            set_tenant(session, organization_id, actor_id)
            if not outbound_flags(session, organization_id)["payment_enabled"]:
                session.execute(text("UPDATE stripe_payout_jobs SET lease_until = NULL, available_at = clock_timestamp() + interval '30 seconds', last_error = 'KILL_SWITCH' WHERE organization_id = :org AND id = :id"), params)
                session.commit()
                return
            _require_current_approval(session, organization_id, job["batch_id"], now)
            authorized = session.execute(text("SELECT 1 FROM role_grants WHERE organization_id = :org AND user_id = :actor AND role = 'property_manager' AND resource_type IS NULL AND active_from <= clock_timestamp() AND (active_until IS NULL OR active_until > clock_timestamp()) LIMIT 1"), {**params, "actor": job["actor_id"]}).scalar()
            if not authorized:
                problem(403, "STRIPE_APPROVER_REVOKED", "The original approver no longer has payout authority.")
            session.commit()
    client = StripeClient(settings)
    if not job["transfer_id"]:
        transfers = client.request("GET", "/transfers", data={"transfer_group": f"grok_{job_id}", "limit": 100})
        matching = [item for item in transfers.get("data", []) if item.get("metadata", {}).get("job_id") == str(job_id)]
        if len(matching) > 1:
            problem(409, "STRIPE_DUPLICATE_TRANSFER_REVIEW", "Multiple matching transfers require review.")
        transfer = matching[0] if matching else None
        if transfer is None:
            if job["transfer_attempt_at"] and now - job["transfer_attempt_at"] >= timedelta(hours=23):
                problem(409, "STRIPE_IDEMPOTENCY_WINDOW_EXPIRED", "Reconcile the original transfer in Stripe before any further sending.")
            account = client.request("GET", f"/accounts/{job['account_id']}")
            if not account.get("payouts_enabled") or account.get("capabilities", {}).get("transfers") != "active" or account.get("settings", {}).get("payouts", {}).get("schedule", {}).get("interval") != "manual":
                problem(409, "STRIPE_RECIPIENT_NOT_READY", "The approved recipient is not ready for a controlled bank payout.")
            balance = client.request("GET", "/balance")
            available = sum(item["amount"] for item in balance.get("available", []) if item.get("currency") == "usd")
            if available < job["amount_cents"]:
                problem(409, "STRIPE_BALANCE_INSUFFICIENT", "The Stripe sandbox balance cannot cover this payout.")
            with Session(engine) as session:
                set_tenant(session, organization_id, actor_id)
                _require_current_approval(session, organization_id, job["batch_id"], now)
                if not outbound_flags(session, organization_id)["payment_enabled"]:
                    problem(409, "KILL_SWITCH", "New Stripe transfers are paused.")
                authorized = session.execute(text("SELECT 1 FROM role_grants WHERE organization_id = :org AND user_id = :actor AND role = 'property_manager' AND resource_type IS NULL AND active_from <= clock_timestamp() AND (active_until IS NULL OR active_until > clock_timestamp()) LIMIT 1"), {"org": organization_id, "actor": job["actor_id"]}).scalar()
                if not authorized:
                    problem(403, "STRIPE_APPROVER_REVOKED", "The original approver no longer has payout authority.")
                session.execute(text("UPDATE stripe_payout_jobs SET transfer_attempt_at = coalesce(transfer_attempt_at, clock_timestamp()), status = 'TRANSFERRING' WHERE organization_id = :org AND id = :id"), params)
                session.commit()
            transfer = client.request("POST", "/transfers", idempotency_key=f"transfer:{job_id}", data={"amount": job["amount_cents"], "currency": "usd", "destination": job["account_id"], "transfer_group": f"grok_{job_id}", "metadata[job_id]": str(job_id), "metadata[organization_id]": str(organization_id), "metadata[actor_id]": str(job["actor_id"])})
        if transfer.get("amount") != job["amount_cents"] or transfer.get("currency") != "usd" or transfer.get("destination") != job["account_id"] or transfer.get("reversed") or transfer.get("amount_reversed", 0):
            problem(409, "STRIPE_TRANSFER_MISMATCH", "The Stripe transfer does not match the approved instruction.")
        with Session(engine) as session:
            set_tenant(session, organization_id, actor_id)
            session.execute(text("UPDATE stripe_payout_jobs SET transfer_id = :transfer, status = 'TRANSFERRED', lease_until = NULL, last_error = NULL WHERE organization_id = :org AND id = :id"), {**params, "transfer": transfer["id"]})
            session.commit()
        return
    transfer = client.request("GET", f"/transfers/{job['transfer_id']}")
    if transfer.get("amount") != job["amount_cents"] or transfer.get("destination") != job["account_id"] or transfer.get("currency") != "usd" or transfer.get("reversed") or transfer.get("amount_reversed", 0):
        problem(409, "STRIPE_TRANSFER_REVERSED", "The original transfer changed or was reversed; review is required.")
    with Session(engine) as session:
        set_tenant(session, organization_id, actor_id)
        batch = _lock_batch(session, organization_id, job["batch_id"])
        item = next(item for item in _items(session, organization_id, job["batch_id"]) if item["id"] == job["item_id"])
        recorded = session.execute(text("SELECT 1 FROM payment_events WHERE organization_id = :org AND item_id = :item AND kind = 'STRIPE_SANDBOX_TRANSFERRED'"), {"org": organization_id, "item": job["item_id"]}).scalar()
        if not recorded:
            _settle_item(session, organization_id, batch["property_id"], item, job["posting_date"], event_kind="STRIPE_SANDBOX_TRANSFERRED", evidence=f"Stripe sandbox transfer {job['transfer_id']}")
            if item["kind"] == "CONTRACTOR":
                session.execute(text("UPDATE invoices SET status = 'PAYMENT_PENDING' WHERE organization_id = :org AND id = :invoice"), {"org": organization_id, "invoice": item["liability_id"]})
            session.execute(text("UPDATE distribution_items SET status = 'UNKNOWN' WHERE organization_id = :org AND id = :item"), {"org": organization_id, "item": job["item_id"]})
            _refresh_status(session, organization_id, job["batch_id"])
        sending_enabled = outbound_flags(session, organization_id)["payment_enabled"]
        session.commit()
    payout = client.request("GET", f"/payouts/{job['payout_id']}", account=job["account_id"]) if job["payout_id"] else None
    if payout is None:
        pagination = {"limit": 100}
        if job["payout_attempt_at"]:
            pagination["created[gte]"] = int(job["payout_attempt_at"].timestamp()) - 60
        for _page in range(10):
            page = client.request("GET", "/payouts", data=pagination, account=job["account_id"])
            matching = [entry for entry in page.get("data", []) if entry.get("metadata", {}).get("job_id") == str(job_id)]
            if matching:
                if len(matching) != 1:
                    problem(409, "STRIPE_DUPLICATE_PAYOUT_REVIEW", "Multiple matching payouts require review.")
                payout = matching[0]
                break
            if not page.get("has_more"):
                break
            pagination["starting_after"] = page["data"][-1]["id"]
        if payout is None:
            if not sending_enabled or (job["payout_attempt_at"] and now - job["payout_attempt_at"] >= timedelta(hours=23)):
                problem(409, "STRIPE_PAYOUT_REVIEW_REQUIRED", "Payout sending is paused or the safe retry window expired.")
            balance = client.request("GET", "/balance", account=job["account_id"])
            available = sum(entry["amount"] for entry in balance.get("available", []) if entry.get("currency") == "usd")
            if available < job["amount_cents"]:
                with Session(engine) as session:
                    set_tenant(session, organization_id, actor_id)
                    session.execute(text("UPDATE stripe_payout_jobs SET status = 'TRANSFERRED', lease_until = NULL, available_at = clock_timestamp() + interval '60 seconds', last_error = 'STRIPE_RECIPIENT_FUNDS_PENDING' WHERE organization_id = :org AND id = :id"), params)
                    session.commit()
                return
            with Session(engine) as session:
                set_tenant(session, organization_id, actor_id)
                batch = _lock_batch(session, organization_id, job["batch_id"])
                if _lock_property(session, organization_id, batch["property_id"]):
                    problem(409, "DISBURSEMENTS_FROZEN", "New bank payouts are frozen for this property.")
                recipient = session.execute(text("SELECT 1 FROM stripe_recipients WHERE organization_id = :org AND account_id = :account AND external_bank_id = :bank AND status = 'READY'"), {"org": organization_id, "account": job["account_id"], "bank": job["external_bank_id"]}).scalar()
                if not recipient:
                    problem(409, "STRIPE_DESTINATION_CHANGED", "The approved bank destination changed; review is required.")
                session.execute(text("UPDATE stripe_payout_jobs SET payout_attempt_at = coalesce(payout_attempt_at, clock_timestamp()), status = 'PAYING' WHERE organization_id = :org AND id = :id"), params)
                session.commit()
            payout = client.request("POST", "/payouts", account=job["account_id"], idempotency_key=f"payout:{job_id}", data={"amount": job["amount_cents"], "currency": "usd", "destination": job["external_bank_id"], "metadata[job_id]": str(job_id), "metadata[organization_id]": str(organization_id), "metadata[actor_id]": str(job["actor_id"])})
    if payout.get("amount") != job["amount_cents"] or payout.get("currency") != "usd" or payout.get("destination") != job["external_bank_id"]:
        problem(409, "STRIPE_PAYOUT_MISMATCH", "The bank payout does not match the approved instruction.")
    status = "SETTLED" if payout.get("status") == "paid" else "BLOCKED" if payout.get("status") in {"failed", "canceled"} else "PENDING"
    with Session(engine) as session:
        set_tenant(session, organization_id, actor_id)
        _lock_batch(session, organization_id, job["batch_id"])
        session.execute(text("UPDATE stripe_payout_jobs SET payout_id = :payout, status = :status, lease_until = NULL, available_at = clock_timestamp() + interval '30 seconds', last_error = :error WHERE organization_id = :org AND id = :id"), {**params, "payout": payout["id"], "status": status, "error": "STRIPE_BANK_PAYOUT_FAILED" if status == "BLOCKED" else None})
        if status == "SETTLED":
            session.execute(text("UPDATE distribution_items SET status = 'SETTLED' WHERE organization_id = :org AND id = :item"), {"org": organization_id, "item": job["item_id"]})
            _refresh_status(session, organization_id, job["batch_id"])
            session.execute(text("UPDATE invoices SET status = 'SETTLED' WHERE organization_id = :org AND id = (SELECT liability_id FROM distribution_items WHERE organization_id = :org AND id = :item) AND settled_cents + credited_cents >= total_cents"), {"org": organization_id, "item": job["item_id"]})
        session.commit()
    logger.info("stripe_payout_progress", extra={"job_id": str(job_id), "organization_id": str(organization_id), "payment_status": status})


def worker_loop(engine, settings, stop) -> None:
    while not stop.is_set():
        try:
            with engine.connect() as connection:
                scopes = connection.execute(text("SELECT * FROM app_stripe_worker_scopes()" )).all()
            for organization_id, actor_id in scopes:
                if stop.is_set():
                    return
                if actor_id is None:
                    continue
                _drain_events(engine, settings, organization_id, actor_id)
                run_pending(engine, settings, organization_id, actor_id)
        except Exception:
            logger.error("stripe_worker_iteration_failed")
        stop.wait(10)


def _drain_events(engine, settings, organization_id, actor_id) -> None:
    principal = Principal(user_id=actor_id, organization_id=organization_id, display_name="Stripe service", roles=())
    with Session(engine) as session:
        set_tenant(session, organization_id, actor_id)
        events = session.execute(text("SELECT * FROM stripe_webhook_events WHERE organization_id = :org AND NOT processed ORDER BY created_at LIMIT 20"), {"org": organization_id}).mappings().all()
        rents = session.execute(text("SELECT id, posting_date FROM stripe_rents WHERE organization_id = :org AND status IN ('CHECKOUT', 'PROCESSING') AND available_at <= clock_timestamp() ORDER BY available_at LIMIT 5"), {"org": organization_id}).all()
    for rent_id, posting_date in rents:
        try:
            with Session(engine) as session:
                set_tenant(session, organization_id, actor_id)
                refresh_rent(session, principal, rent_id, posting_date, settings)
                session.commit()
        except Exception:
            logger.warning("stripe_rent_needs_review", extra={"rent_id": str(rent_id), "organization_id": str(organization_id)})
    for event in events:
        try:
            with Session(engine) as session:
                set_tenant(session, organization_id, actor_id)
                target = UUID(event["object_id"])
                kind = event["event_type"]
                if kind.startswith(("checkout.session.", "payment_intent.", "charge.")):
                    rent = session.execute(text("SELECT posting_date FROM stripe_rents WHERE organization_id = :org AND id = :id"), {"org": organization_id, "id": target}).first()
                    if rent:
                        refresh_rent(session, principal, target, rent.posting_date, settings)
                elif kind.startswith("account."):
                    refresh_recipient(session, principal, target, settings)
                elif kind.startswith(("payout.", "transfer.")):
                    job = session.execute(text("SELECT * FROM stripe_payout_jobs WHERE organization_id = :org AND id = :id"), {"org": organization_id, "id": target}).mappings().first()
                    if job:
                        failed = False
                        if kind.startswith("payout.") and event["provider_object_id"] == job["payout_id"]:
                            canonical = StripeClient(settings).request("GET", f"/payouts/{job['payout_id']}", account=job["account_id"])
                            failed = canonical.get("status") in {"failed", "canceled"}
                        elif kind == "transfer.reversed" and event["provider_object_id"] == job["transfer_id"]:
                            canonical = StripeClient(settings).request("GET", f"/transfers/{job['transfer_id']}")
                            failed = bool(canonical.get("reversed") or canonical.get("amount_reversed", 0))
                        _lock_batch(session, organization_id, job["batch_id"])
                        if failed:
                            session.execute(text("UPDATE stripe_payout_jobs SET status = 'BLOCKED', last_error = 'STRIPE_RETURN_REVIEW_REQUIRED' WHERE organization_id = :org AND id = :id"), {"org": organization_id, "id": target})
                            session.execute(text("UPDATE distribution_items SET status = 'UNKNOWN' WHERE organization_id = :org AND id = :item"), {"org": organization_id, "item": job["item_id"]})
                            session.execute(text("UPDATE invoices SET status = 'PAYMENT_PENDING' WHERE organization_id = :org AND id = (SELECT liability_id FROM distribution_items WHERE organization_id = :org AND id = :item)"), {"org": organization_id, "item": job["item_id"]})
                            session.execute(text("UPDATE properties SET disbursements_frozen = true WHERE organization_id = :org AND id IN (SELECT property_id FROM stripe_properties WHERE organization_id = :org)"), {"org": organization_id})
                            _refresh_status(session, organization_id, job["batch_id"])
                        else:
                            session.execute(text("UPDATE stripe_payout_jobs SET available_at = clock_timestamp() WHERE organization_id = :org AND id = :id"), {"org": organization_id, "id": target})
                session.execute(text("UPDATE stripe_webhook_events SET processed = true WHERE organization_id = :org AND id = :id"), {"org": organization_id, "id": event["id"]})
                session.commit()
        except Exception:
            logger.warning("stripe_webhook_needs_review", extra={"event_id": event["id"], "organization_id": str(organization_id)})
