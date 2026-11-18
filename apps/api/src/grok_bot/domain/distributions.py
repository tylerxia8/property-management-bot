import hashlib
import json
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import text

from grok_bot.domain.accounting import _account_balance, _line, _lock_invoice, _lock_property, _owner_balance, _owner_line, _post, property_balances
from grok_bot.domain.records import write_audit
from grok_bot.errors import problem


def create_destination(session, organization_id, party_id, masked_label: str, channel: str = "ZELLE") -> dict:
    if not masked_label.strip():
        problem(422, "VALIDATION_ERROR", "A destination label is required.")
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": f"payee-destination:{organization_id}:{party_id}"},
    )
    party = session.execute(
        text("SELECT id FROM parties WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": party_id},
    ).scalar()
    if party is None:
        problem(404, "NOT_FOUND", "Payee not found.")
    version = session.execute(
        text(
            """
            SELECT COALESCE(MAX(version), 0) + 1
            FROM payee_destinations
            WHERE organization_id = :organization_id AND party_id = :party_id
            """
        ),
        {"organization_id": organization_id, "party_id": party_id},
    ).scalar()
    destination_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO payee_destinations (
              id, organization_id, party_id, version, masked_label, active, channel
            ) VALUES (
              :id, :organization_id, :party_id, :version, :masked_label, true, :channel
            )
            """
        ),
        {
            "id": destination_id,
            "organization_id": organization_id,
            "party_id": party_id,
            "version": version,
            "masked_label": masked_label,
            "channel": channel,
        },
    )
    return {"id": str(destination_id), "party_id": str(party_id), "version": version, "masked_label": masked_label}


def record_step_up(session, organization_id, user_id, when, method="LOCAL_DEV_PASSWORD") -> dict:
    event_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO step_up_events (id, organization_id, user_id, occurred_at, method)
            VALUES (:id, :organization_id, :user_id, :occurred_at, :method)
            """
        ),
        {"id": event_id, "organization_id": organization_id, "user_id": user_id, "occurred_at": when, "method": method},
    )
    return {"id": str(event_id), "method": method, "production_oidc": False}


def draft_batch(session, organization_id, property_id, as_of, management_party_id, liability_ids=None) -> dict:
    _lock_property(session, organization_id, property_id)
    balances = property_balances(session, organization_id, property_id)
    committed = session.execute(
        text(
            """
            SELECT i.kind, i.recipient_party_id, i.liability_id, sum(i.amount_cents) AS amount_cents
            FROM distribution_items AS i
            JOIN distribution_batches AS b ON b.organization_id = i.organization_id AND b.id = i.batch_id
            WHERE i.organization_id = :organization_id AND b.property_id = :property_id
              AND EXISTS (SELECT 1 FROM fund_reservations AS r
                WHERE r.organization_id = i.organization_id AND r.item_id = i.id AND r.status = 'ACTIVE')
            GROUP BY i.kind, i.recipient_party_id, i.liability_id
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).mappings().all()
    accounts = {item["code"]: item["amount_cents"] for item in balances["accounts"]}
    batch_id = uuid4()
    items = []
    for owner in balances["owners"]:
        amount = owner["unrestricted_cents"] - sum(row["amount_cents"] for row in committed if row["kind"] == "OWNER" and str(row["recipient_party_id"]) == owner["owner_party_id"])
        if amount > 0:
            items.append(("OWNER", UUID(owner["owner_party_id"]), amount, None))
    fee = accounts.get("2050", 0) - sum(row["amount_cents"] for row in committed if row["kind"] == "MANAGEMENT")
    if fee > 0:
        if management_party_id is None:
            problem(409, "CONFIGURATION_REQUIRED", "A management payee is required when a fee payable is outstanding.")
        items.append(("MANAGEMENT", management_party_id, fee, None))
    invoices = session.execute(
        text(
            """
            SELECT id, contractor_party_id, total_cents - credited_cents - settled_cents AS remaining
            FROM invoices
            WHERE organization_id = :organization_id AND property_id = :property_id
              AND payable_journal_id IS NOT NULL
              AND total_cents - credited_cents - settled_cents > 0
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).mappings().all()
    for invoice in invoices:
        if liability_ids is not None and invoice["id"] not in liability_ids:
            continue
        remaining = int(invoice["remaining"]) - sum(row["amount_cents"] for row in committed if row["liability_id"] == invoice["id"])
        if remaining > 0:
            items.append(("CONTRACTOR", invoice["contractor_party_id"], remaining, invoice["id"]))
    session.execute(
        text(
            """
            INSERT INTO distribution_batches (
              id, organization_id, property_id, as_of, status, total_cents, retained_reserves_cents
            ) VALUES (
              :id, :organization_id, :property_id, :as_of, 'DRAFT', :total_cents, :retained_reserves_cents
            )
            """
        ),
        {
            "id": batch_id,
            "organization_id": organization_id,
            "property_id": property_id,
            "as_of": as_of,
            "total_cents": sum(item[2] for item in items),
            "retained_reserves_cents": accounts.get("2030", 0),
        },
    )
    stored = []
    for kind, recipient, amount, liability in items:
        destination = _active_destination(session, organization_id, recipient)
        item_id = uuid4()
        session.execute(
            text(
                """
                INSERT INTO distribution_items (
                  id, organization_id, batch_id, kind, recipient_party_id, amount_cents,
                  destination_id, destination_version, liability_id, status, provider_key
                ) VALUES (
                  :id, :organization_id, :batch_id, :kind, :recipient_party_id, :amount_cents,
                  :destination_id, :destination_version, :liability_id, 'DRAFT', :provider_key
                )
                """
            ),
            {
                "id": item_id,
                "organization_id": organization_id,
                "batch_id": batch_id,
                "kind": kind,
                "recipient_party_id": recipient,
                "amount_cents": amount,
                "destination_id": None if destination is None else destination["id"],
                "destination_version": None if destination is None else destination["version"],
                "liability_id": liability,
                "provider_key": f"sim-{item_id}",
            },
        )
        stored.append(item_id)
    return get_batch(session, organization_id, batch_id)


def validate_batch(session, organization_id, batch_id) -> dict:
    batch = _lock_batch(session, organization_id, batch_id)
    if batch["status"] not in {"DRAFT", "VALIDATED"}:
        problem(409, "BATCH_NOT_DRAFT", "Only a draft batch can be validated.")
    fee_due = session.execute(text("SELECT coalesce(sum(fee_due_cents), 0) FROM stripe_rents WHERE organization_id = :org AND property_id = :property"), {"org": organization_id, "property": batch["property_id"]}).scalar()
    if fee_due:
        problem(409, "MANAGEMENT_FEE_FUNDING_REQUIRED", "Management must reimburse Stripe processing fees before this property's payouts can be reserved.")
    items = _items(session, organization_id, batch_id)
    if not items:
        problem(409, "EMPTY_BATCH", "There are no payments to validate.")
    if _lock_property(session, organization_id, batch["property_id"]):
        problem(409, "DISBURSEMENTS_FROZEN", "Disbursements for this property are frozen.")
    if any(item["destination_id"] is None for item in items):
        problem(409, "DESTINATION_UNCONFIGURED", "Every item needs an active payee destination.")
    _release_reservations(session, organization_id, batch_id)
    for item in items:
        _reserve(session, organization_id, batch["property_id"], item["id"], item["amount_cents"])
        session.execute(
            text("UPDATE distribution_items SET status = 'RESERVED' WHERE organization_id = :organization_id AND id = :id"),
            {"organization_id": organization_id, "id": item["id"]},
        )
    _assert_snapshot_inputs(session, organization_id, batch_id)
    hashed = _hash(session, organization_id, batch_id)
    session.execute(
        text(
            """
            UPDATE distribution_batches
            SET status = 'VALIDATED', snapshot_hash = :snapshot_hash
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"snapshot_hash": hashed, "organization_id": organization_id, "id": batch_id},
    )
    return get_batch(session, organization_id, batch_id)


def approve_batch(session, organization_id, batch_id, actor_id, snapshot_hash: str, reason: str, settings, now) -> dict:
    if settings.approval_ttl_hours <= 0:
        problem(409, "CONFIGURATION_REQUIRED", "Approval lifetime is not configured.")
    if settings.step_up_max_age_seconds <= 0:
        problem(409, "CONFIGURATION_REQUIRED", "Step-up freshness is not configured.")
    if not reason.strip():
        problem(422, "VALIDATION_ERROR", "Approval requires a reason.")
    batch = _lock_batch(session, organization_id, batch_id)
    if batch["status"] not in {"VALIDATED", "APPROVED", "UNKNOWN", "PARTIALLY_SETTLED", "FAILED"}:
        problem(409, "APPROVAL_INVALID", "Only a validated or previously approved unpaid batch can be approved.")
    if _lock_property(session, organization_id, batch["property_id"]):
        problem(409, "DISBURSEMENTS_FROZEN", "Disbursements for this property are frozen.")
    _assert_snapshot_inputs(session, organization_id, batch_id)
    current = _hash(session, organization_id, batch_id)
    if current != snapshot_hash or current != batch["snapshot_hash"]:
        problem(409, "APPROVAL_INVALID", "The snapshot does not match the current batch.")
    step_up = session.execute(
        text(
            """
            SELECT max(occurred_at) FROM step_up_events
            WHERE organization_id = :organization_id AND user_id = :user_id
            """
        ),
        {"organization_id": organization_id, "user_id": actor_id},
    ).scalar()
    if step_up is None or not 0 <= (now - step_up).total_seconds() <= settings.step_up_max_age_seconds:
        problem(409, "STEP_UP_REQUIRED", "A fresh dev/test step-up is required. Production MFA is not configured.")
    expires = now + timedelta(hours=settings.approval_ttl_hours)
    approval_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO distribution_approvals (
              id, organization_id, batch_id, actor_id, snapshot_hash, step_up_at, expires_at, reason
            ) VALUES (
              :id, :organization_id, :batch_id, :actor_id, :snapshot_hash, :step_up_at, :expires_at, :reason
            )
            """
        ),
        {
            "id": approval_id,
            "organization_id": organization_id,
            "batch_id": batch_id,
            "actor_id": actor_id,
            "snapshot_hash": current,
            "step_up_at": step_up,
            "expires_at": expires,
            "reason": reason,
        },
    )
    session.execute(
        text(
            """
            UPDATE distribution_batches
            SET status = 'APPROVED', approved_at = :now, expires_at = :expires_at, approval_ttl_hours = :ttl_hours
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
            {
                "now": now,
                "expires_at": expires,
                "ttl_hours": settings.approval_ttl_hours,
                "organization_id": organization_id,
                "id": batch_id,
            },
    )
    session.execute(
        text("UPDATE distribution_items SET status = 'APPROVED' WHERE organization_id = :organization_id AND batch_id = :batch_id AND status = 'RESERVED'"),
        {"organization_id": organization_id, "batch_id": batch_id},
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="distribution.approved",
        target_type="distribution_batch",
        target_id=batch_id,
        target_version=None,
        request_id="distribution",
        before_state={"status": batch["status"]},
        after_state={"status": "APPROVED", "snapshot_hash": current, "submitted": False},
    )
    body = get_batch(session, organization_id, batch_id)
    body["approval_id"] = str(approval_id)
    return body


def export_batch(session, organization_id, batch_id, actor_id, now) -> dict:
    batch = _require_current_approval(session, organization_id, batch_id, now)
    if session.execute(text("SELECT 1 FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": organization_id, "property": batch["property_id"]}).scalar():
        problem(409, "STRIPE_QUEUE_REQUIRED", "Approved Stripe payments use the durable payout queue, not manual exports.")
    prior = session.execute(
        text("SELECT count(*) FROM distribution_exports WHERE organization_id = :organization_id AND batch_id = :batch_id"),
        {"organization_id": organization_id, "batch_id": batch_id},
    ).scalar()
    artifact = {
        "batch_id": str(batch_id),
        "snapshot_hash": batch["snapshot_hash"],
        "items": [
            {
                "id": str(item["id"]),
                "kind": item["kind"],
                "amount_cents": item["amount_cents"],
                "destination_version": item["destination_version"],
                "provider_key": item["provider_key"],
            }
            for item in _items(session, organization_id, batch_id)
        ],
        "submitted": False,
        "settled": False,
    }
    digest = hashlib.sha256(json.dumps(artifact, sort_keys=True).encode()).hexdigest()
    export_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO distribution_exports (
              id, organization_id, batch_id, artifact_hash, duplicate_download
            ) VALUES (
              :id, :organization_id, :batch_id, :artifact_hash, :duplicate_download
            )
            """
        ),
        {
            "id": export_id,
            "organization_id": organization_id,
            "batch_id": batch_id,
            "artifact_hash": digest,
            "duplicate_download": prior > 0,
        },
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="distribution.exported",
        target_type="distribution_batch",
        target_id=batch_id,
        target_version=None,
        request_id="distribution",
        before_state=None,
        after_state={"export_id": str(export_id), "duplicate_download": prior > 0, "settled": False},
    )
    return {
        "id": str(export_id),
        "batch_id": str(batch_id),
        "artifact": artifact,
        "artifact_hash": digest,
        "duplicate_download": prior > 0,
        "status": batch["status"],
        "settled": False,
    }


def submit_batch(session, organization_id, batch_id, scripts: dict, settings, posting_date, now) -> dict:
    from grok_bot.domain.controls import outbound_flags
    from grok_bot.domain.simulated_bank import send_approved

    if not outbound_flags(session, organization_id)["payment_enabled"]:
        problem(409, "KILL_SWITCH", "Automatic payment submission is switched off.")
    stripe = session.execute(text("SELECT 1 FROM stripe_properties AS p JOIN distribution_batches AS b ON b.organization_id = p.organization_id AND b.property_id = p.property_id WHERE b.organization_id = :org AND b.id = :batch"), {"org": organization_id, "batch": batch_id}).scalar()
    if stripe:
        problem(409, "STRIPE_QUEUE_REQUIRED", "Stripe payouts are queued by approval and processed by the Stripe worker.")
    simulated = session.execute(
        text("SELECT 1 FROM simulated_bank_accounts AS a JOIN distribution_batches AS b ON b.organization_id = a.organization_id AND b.property_id = a.property_id WHERE b.organization_id = :organization_id AND b.id = :id"),
        {"organization_id": organization_id, "id": batch_id},
    ).scalar()
    if simulated:
        if not settings.allows_local_auth:
            problem(409, "PROVIDER_SUBMISSION_DISABLED", "Simulated banking is unavailable in production.")
        if scripts:
            problem(422, "VALIDATION_ERROR", "Configure simulated outcomes on the bank account before approval.")
        return send_approved(session, organization_id, batch_id, posting_date, now)
    if not settings.payment_simulator_enabled:
        problem(409, "PROVIDER_SUBMISSION_DISABLED", "No payment provider is configured. Nothing was submitted to a bank.")
    batch = _require_current_approval(session, organization_id, batch_id, now)
    items = _items(session, organization_id, batch_id)
    if set(scripts) - {str(item["id"]) for item in items} or any(value not in {"settle", "timeout", "fail"} for value in scripts.values()):
        problem(422, "VALIDATION_ERROR", "Simulator scripts must name batch items and use settle, timeout, or fail.")
    submitted = session.execute(
        text("SELECT 1 FROM payment_events AS e JOIN distribution_items AS i ON i.organization_id = e.organization_id AND i.id = e.item_id WHERE i.organization_id = :organization_id AND i.batch_id = :batch_id AND e.kind = 'MANUAL_SUBMISSION' LIMIT 1"),
        {"organization_id": organization_id, "batch_id": batch_id},
    ).scalar()
    if submitted:
        problem(409, "EVIDENCE_STATE", "Manually submitted payments must be reconciled with settlement evidence.")
    for item in items:
        if item["status"] == "SETTLED":
            continue
        script = scripts.get(str(item["id"]), "settle")
        if item["status"] == "UNKNOWN" and script == "fail":
            problem(409, "BATCH_UNCERTAIN", "An uncertain payment must be reconciled before it can fail.")
        if script == "timeout" and item["status"] != "UNKNOWN":
            _event(session, organization_id, item, "SIMULATOR_TIMEOUT", "Simulator timed out after an uncertain accept.")
            session.execute(
                text("UPDATE distribution_items SET status = 'UNKNOWN' WHERE organization_id = :organization_id AND id = :id"),
                {"organization_id": organization_id, "id": item["id"]},
            )
            continue
        if script == "fail":
            _event(session, organization_id, item, "SIMULATOR_FAILED", "Simulator declined this item.")
            session.execute(
                text("UPDATE distribution_items SET status = 'FAILED' WHERE organization_id = :organization_id AND id = :id"),
                {"organization_id": organization_id, "id": item["id"]},
            )
            continue
        _settle_item(session, organization_id, batch["property_id"], item, posting_date)
    return _refresh_status(session, organization_id, batch_id)


def cancel_batch(session, organization_id, batch_id) -> dict:
    batch = _lock_batch(session, organization_id, batch_id)
    _lock_property(session, organization_id, batch["property_id"])
    submitted = session.execute(
        text("SELECT 1 FROM payment_events AS e JOIN distribution_items AS i ON i.organization_id = e.organization_id AND i.id = e.item_id WHERE i.organization_id = :organization_id AND i.batch_id = :batch_id AND e.kind = 'MANUAL_SUBMISSION' LIMIT 1"),
        {"organization_id": organization_id, "batch_id": batch_id},
    ).scalar()
    if submitted:
        problem(409, "BATCH_UNCERTAIN", "Manually submitted payments must be reconciled before cancellation.")
    items = _items(session, organization_id, batch_id)
    if any(item["status"] in {"UNKNOWN", "RETURNED"} for item in items) or (items and all(item["status"] == "SETTLED" for item in items)):
        problem(409, "BATCH_UNCERTAIN", "Completed or uncertain payments cannot be canceled.")
    _release_reservations(session, organization_id, batch_id)
    session.execute(
        text("UPDATE distribution_items SET status = 'CANCELED' WHERE organization_id = :organization_id AND batch_id = :batch_id AND status != 'SETTLED'"),
        {"organization_id": organization_id, "batch_id": batch_id},
    )
    session.execute(
        text("UPDATE distribution_batches SET status = :status WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": batch_id, "status": "PARTIALLY_SETTLED" if any(item["status"] == "SETTLED" for item in items) else "CANCELED"},
    )
    del batch
    return get_batch(session, organization_id, batch_id)


def record_return(session, organization_id, item_id, posting_date) -> dict:
    item, batch = _item_with_batch(session, organization_id, item_id)
    if item["status"] != "SETTLED":
        problem(409, "NOT_SETTLED", "A return requires a settled simulator item.")
    simulated = session.execute(
        text("SELECT 1 FROM payment_events WHERE organization_id = :organization_id AND item_id = :item_id AND kind = 'SIMULATOR_SETTLED'"),
        {"organization_id": organization_id, "item_id": item_id},
    ).scalar()
    if not simulated:
        problem(409, "EVIDENCE_STATE", "Simulator returns require a simulator settlement.")
    _lock_property(session, organization_id, batch["property_id"])
    banks = session.execute(
        text(
            """
            SELECT l.bank_account_id, sum(r.amount_cents) AS amount_cents
            FROM fund_reservations AS r
            JOIN funding_lots AS l ON l.organization_id = r.organization_id AND l.id = r.funding_lot_id
            WHERE r.organization_id = :organization_id AND r.item_id = :item_id AND r.status = 'CONSUMED'
            GROUP BY l.bank_account_id
            """
        ),
        {"organization_id": organization_id, "item_id": item_id},
    ).mappings().all()
    if sum(row["amount_cents"] for row in banks) != item["amount_cents"]:
        problem(409, "APPROVAL_INVALID", "Consumed cash does not match the returned amount.")
    _post(
        session,
        organization_id,
        "DISTRIBUTION_RETURN",
        item_id,
        posting_date,
        [
            _line("1040", "DEBIT", item["amount_cents"], {"property_id": batch["property_id"], "lease_id": None}, "RENT"),
        ] + [
            _line("1030", "CREDIT", int(row["amount_cents"]), {"property_id": batch["property_id"], "lease_id": None}, "RENT", bank_account_id=row["bank_account_id"])
            for row in banks
        ],
    )
    session.execute(
        text("UPDATE distribution_items SET status = 'RETURNED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": item_id},
    )
    session.execute(
        text("UPDATE properties SET disbursements_frozen = true WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": batch["property_id"]},
    )
    _event(session, organization_id, item, "SIMULATOR_RETURN", "Simulator recorded a bank return. This is not a live bank debit.")
    return {"id": str(item_id), "status": "RETURNED", "recovery_account": "1040", "disbursements_frozen": True, "simulator": True}


def issue_statement(session, organization_id, property_id, owner_party_id, period_start, period_end, reason: str) -> dict:
    balances = property_balances(session, organization_id, property_id)
    owner = next((item for item in balances["owners"] if item["owner_party_id"] == str(owner_party_id)), None)
    version = session.execute(
        text(
            """
            SELECT COALESCE(MAX(version), 0) + 1
            FROM owner_statements
            WHERE organization_id = :organization_id AND property_id = :property_id
              AND owner_party_id = :owner_party_id AND period_start = :period_start AND period_end = :period_end
            """
        ),
        {
            "organization_id": organization_id,
            "property_id": property_id,
            "owner_party_id": owner_party_id,
            "period_start": period_start,
            "period_end": period_end,
        },
    ).scalar()
    snapshot = {
        "property_id": str(property_id),
        "owner_party_id": str(owner_party_id),
        "period_start": str(period_start),
        "period_end": str(period_end),
        "unrestricted_cents": 0 if owner is None else owner["unrestricted_cents"],
        "reserve_cents": 0 if owner is None else owner["reserve_cents"],
        "accounts": balances["accounts"],
        "fixture": False,
    }
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    statement_id = uuid4()
    prior = session.execute(
        text(
            """
            SELECT id FROM owner_statements
            WHERE organization_id = :organization_id AND property_id = :property_id
              AND owner_party_id = :owner_party_id AND period_start = :period_start
              AND period_end = :period_end AND version = :version
            """
        ),
        {
            "organization_id": organization_id,
            "property_id": property_id,
            "owner_party_id": owner_party_id,
            "period_start": period_start,
            "period_end": period_end,
            "version": version - 1,
        },
    ).scalar()
    session.execute(
        text(
            """
            INSERT INTO owner_statements (
              id, organization_id, property_id, owner_party_id, period_start, period_end,
              version, snapshot_hash, snapshot, reason
            ) VALUES (
              :id, :organization_id, :property_id, :owner_party_id, :period_start, :period_end,
              :version, :snapshot_hash, CAST(:snapshot AS jsonb), :reason
            )
            """
        ),
        {
            "id": statement_id,
            "organization_id": organization_id,
            "property_id": property_id,
            "owner_party_id": owner_party_id,
            "period_start": period_start,
            "period_end": period_end,
            "version": version,
            "snapshot_hash": digest,
            "snapshot": json.dumps(snapshot),
            "reason": reason,
        },
    )
    return {
        "id": str(statement_id),
        "version": version,
        "snapshot_hash": digest,
        "snapshot": snapshot,
        "supersedes": None if prior is None else str(prior),
    }


def get_batch(session, organization_id, batch_id) -> dict:
    batch = session.execute(
        text("SELECT * FROM distribution_batches WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": batch_id},
    ).mappings().first()
    if batch is None:
        problem(404, "NOT_FOUND", "Distribution batch not found.")
    items = _items(session, organization_id, batch_id)
    return {
        "id": str(batch["id"]),
        "property_id": str(batch["property_id"]),
        "status": batch["status"],
        "snapshot_hash": batch["snapshot_hash"],
        "total_cents": batch["total_cents"],
        "retained_reserves_cents": batch["retained_reserves_cents"],
        "expires_at": None if batch["expires_at"] is None else batch["expires_at"].isoformat(),
        "items": [
            {
                "id": str(item["id"]),
                "kind": item["kind"],
                "recipient_id": str(item["recipient_party_id"]),
                "amount_cents": item["amount_cents"],
                "destination_version": item["destination_version"],
                "liability_id": None if item["liability_id"] is None else str(item["liability_id"]),
                "status": item["status"],
                "provider_key": item["provider_key"],
                "channel": item["channel"],
                "destination_label": item["destination_label"],
            }
            for item in items
        ],
        "currency": "USD",
        "submitted": False,
    }


def record_submission_evidence(session, organization_id, item_id, reference: str, now, actor_id, request_id: str) -> dict:
    if not reference.strip():
        problem(422, "VALIDATION_ERROR", "Submission evidence needs a reference.")
    item, batch = _item_with_batch(session, organization_id, item_id)
    from grok_bot.domain.simulated_bank import account_for_property

    stripe = session.execute(text("SELECT 1 FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": organization_id, "property": batch["property_id"]}).scalar()
    if stripe or account_for_property(session, organization_id, batch["property_id"]) is not None:
        problem(409, "EVIDENCE_STATE", "Use simulated bank approval and reconciliation for this property.")
    if item["status"] != "APPROVED":
        problem(409, "EVIDENCE_STATE", "Submission evidence requires an approved unpaid item.")
    _require_current_approval(session, organization_id, batch["id"], now)
    _reject_duplicate_evidence(session, organization_id, item["id"], "MANUAL_SUBMISSION")
    _event(session, organization_id, item, "MANUAL_SUBMISSION", reference, simulator=False)
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="distribution.submission_evidence",
        target_type="distribution_item",
        target_id=item["id"],
        target_version=None,
        request_id=request_id,
        before_state={"status": item["status"]},
        after_state={"kind": "MANUAL_SUBMISSION", "simulator": False, "bank_contacted": False, "amount_cents": item["amount_cents"]},
    )
    return _evidence_body(item, "MANUAL_SUBMISSION", reference, settled=False)


def record_settlement_evidence(session, organization_id, item_id, reference: str, posting_date, now, actor_id, request_id: str) -> dict:
    if not reference.strip():
        problem(422, "VALIDATION_ERROR", "Settlement evidence needs a reference.")
    item, batch = _item_with_batch(session, organization_id, item_id)
    from grok_bot.domain.simulated_bank import account_for_property

    stripe = session.execute(text("SELECT 1 FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": organization_id, "property": batch["property_id"]}).scalar()
    if stripe or account_for_property(session, organization_id, batch["property_id"]) is not None:
        problem(409, "EVIDENCE_STATE", "Use simulated bank reconciliation for this property.")
    if item["status"] not in {"APPROVED", "UNKNOWN"}:
        problem(409, "EVIDENCE_STATE", "Settlement evidence requires an approved or unknown item that is not already settled.")
    submitted = session.execute(
        text("SELECT 1 FROM payment_events WHERE organization_id = :organization_id AND item_id = :item_id AND kind = 'MANUAL_SUBMISSION'"),
        {"organization_id": organization_id, "item_id": item_id},
    ).scalar()
    if not submitted:
        _require_current_approval(session, organization_id, batch["id"], now)
    _reject_duplicate_evidence(session, organization_id, item["id"], "MANUAL_SETTLEMENT")
    _reject_duplicate_evidence(session, organization_id, item["id"], "SIMULATOR_SETTLED")
    _settle_item(
        session,
        organization_id,
        batch["property_id"],
        item,
        posting_date,
        event_kind="MANUAL_SETTLEMENT",
        simulator=False,
        evidence=reference,
    )
    _refresh_status(session, organization_id, batch["id"])
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="distribution.settlement_evidence",
        target_type="distribution_item",
        target_id=item["id"],
        target_version=None,
        request_id=request_id,
        before_state={"status": item["status"]},
        after_state={
            "kind": "MANUAL_SETTLEMENT",
            "simulator": False,
            "bank_contacted": False,
            "amount_cents": item["amount_cents"],
            "currency": "USD",
        },
    )
    return _evidence_body(item, "MANUAL_SETTLEMENT", reference, settled=True)


def _evidence_body(item, kind: str, reference: str, settled: bool) -> dict:
    return {
        "id": str(item["id"]),
        "kind": kind,
        "simulator": False,
        "settled": settled,
        "reference": reference,
        "bank_contacted": False,
        "amount_cents": item["amount_cents"],
        "currency": "USD",
    }


def _reject_duplicate_evidence(session, organization_id, item_id, kind: str) -> None:
    existing = session.execute(
        text(
            """
            SELECT id FROM payment_events
            WHERE organization_id = :organization_id AND item_id = :item_id AND kind = :kind
            """
        ),
        {"organization_id": organization_id, "item_id": item_id, "kind": kind},
    ).scalar()
    if existing is not None:
        problem(409, "DUPLICATE_EVIDENCE", "That evidence is already recorded for this item.")


def _item_with_batch(session, organization_id, item_id):
    row = session.execute(
        text(
            """
            SELECT i.*, b.property_id AS batch_property_id, b.id AS batch_row_id
            FROM distribution_items AS i
            JOIN distribution_batches AS b ON b.organization_id = i.organization_id AND b.id = i.batch_id
            WHERE i.organization_id = :organization_id AND i.id = :id
            """
        ),
        {"organization_id": organization_id, "id": item_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Payment item not found.")
    batch = _lock_batch(session, organization_id, row["batch_id"])
    item = session.execute(
        text("SELECT * FROM distribution_items WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": item_id},
    ).mappings().one()
    return item, batch


def _settle_item(session, organization_id, property_id, item, posting_date, event_kind="SIMULATOR_SETTLED", simulator=True, evidence=None) -> None:
    if not simulator and not (evidence or "").strip():
        problem(422, "VALIDATION_ERROR", "Settlement evidence needs a reference before cash can clear.")
    existing = session.execute(
        text(
            """
            SELECT id FROM payment_events
            WHERE organization_id = :organization_id AND item_id = :item_id AND kind = 'SIMULATOR_SETTLED'
            """
        ),
        {"organization_id": organization_id, "item_id": item["id"]},
    ).scalar()
    if existing or item["status"] == "SETTLED":
        return
    frozen = _lock_property(session, organization_id, property_id)
    if frozen and simulator and event_kind == "SIMULATOR_SETTLED":
        problem(409, "DISBURSEMENTS_FROZEN", "Disbursements for this property are frozen.")
    if item["kind"] == "OWNER":
        payable = _owner_balance(session, organization_id, property_id, item["recipient_party_id"], "2020")
    elif item["kind"] == "MANAGEMENT":
        payable = _account_balance(session, organization_id, "2050", property_id=property_id)
    else:
        invoice = _lock_invoice(session, organization_id, item["liability_id"])
        if invoice["property_id"] != property_id or invoice["contractor_party_id"] != item["recipient_party_id"] or invoice["payable_journal_id"] is None:
            problem(409, "APPROVAL_INVALID", "The invoice no longer matches the approved payment.")
        payable = invoice["total_cents"] - invoice["credited_cents"] - invoice["settled_cents"]
    if payable < item["amount_cents"]:
        problem(409, "SETTLEMENT_EXCEEDS_PAYABLE", "The payment exceeds the remaining payable.")
    banks = session.execute(
        text(
            """
            SELECT l.bank_account_id, sum(r.amount_cents) AS amount_cents
            FROM fund_reservations AS r
            JOIN funding_lots AS l ON l.organization_id = r.organization_id AND l.id = r.funding_lot_id
            WHERE r.organization_id = :organization_id AND r.item_id = :item_id AND r.status = 'ACTIVE'
            GROUP BY l.bank_account_id
            """
        ),
        {"organization_id": organization_id, "item_id": item["id"]},
    ).mappings().all()
    if sum(row["amount_cents"] for row in banks) != item["amount_cents"]:
        problem(409, "APPROVAL_INVALID", "Active reserved cash does not match the payment amount.")
    if item["kind"] == "OWNER":
        lines = [
            _owner_line("2020", "DEBIT", item["amount_cents"], {"property_id": property_id, "lease_id": None}, item["recipient_party_id"]),
        ]
        source = "DISTRIBUTION_SETTLEMENT"
    elif item["kind"] == "MANAGEMENT":
        lines = [
            _line("2050", "DEBIT", item["amount_cents"], {"property_id": property_id, "lease_id": None}, "RENT"),
        ]
        source = "FEE_SETTLEMENT"
    else:
        lines = [
            _line("2040", "DEBIT", item["amount_cents"], {"property_id": property_id, "lease_id": None}, "RENT"),
        ]
        source = "INVOICE_SETTLEMENT"
        session.execute(
            text(
                """
                UPDATE invoices
                SET settled_cents = settled_cents + :amount, status = 'SETTLED'
                WHERE organization_id = :organization_id AND id = :id
                """
            ),
            {"amount": item["amount_cents"], "organization_id": organization_id, "id": item["liability_id"]},
        )
    lines.extend(
        _line("1030", "CREDIT", int(row["amount_cents"]), {"property_id": property_id, "lease_id": None}, "RENT", bank_account_id=row["bank_account_id"])
        for row in banks
    )
    _consume_reserved(session, organization_id, item["id"])
    _post(session, organization_id, source, item["id"], posting_date, lines)
    session.execute(
        text("UPDATE distribution_items SET status = 'SETTLED' WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": item["id"]},
    )
    _event(
        session,
        organization_id,
        item,
        event_kind,
        evidence or "Simulator settlement journal. No bank was contacted.",
        simulator=simulator,
    )


def _consume_reserved(session, organization_id, item_id) -> None:
    rows = session.execute(
        text(
            """
            SELECT id, funding_lot_id, amount_cents
            FROM fund_reservations
            WHERE organization_id = :organization_id AND item_id = :item_id AND status = 'ACTIVE'
            FOR UPDATE
            """
        ),
        {"organization_id": organization_id, "item_id": item_id},
    ).mappings().all()
    for row in rows:
        session.execute(
            text(
                """
                UPDATE funding_lots
                SET reserved_cents = reserved_cents - :amount, consumed_cents = consumed_cents + :amount
                WHERE organization_id = :organization_id AND id = :id
                """
            ),
            {"amount": row["amount_cents"], "organization_id": organization_id, "id": row["funding_lot_id"]},
        )
        session.execute(
            text("UPDATE fund_reservations SET status = 'CONSUMED' WHERE id = :id"),
            {"id": row["id"]},
        )


def _reserve(session, organization_id, property_id, item_id, amount: int) -> None:
    rows = session.execute(
        text(
            """
            SELECT id, amount_cents - consumed_cents - reserved_cents AS available
            FROM funding_lots
            WHERE organization_id = :organization_id AND property_id = :property_id
              AND purpose = 'RENT' AND amount_cents - consumed_cents - reserved_cents > 0
            ORDER BY id
            FOR UPDATE
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).mappings().all()
    unapplied = session.execute(
        text(
            """
            SELECT coalesce(sum(available_cents - allocated_cents), 0)
            FROM receipts
            WHERE organization_id = :organization_id AND property_id = :property_id
              AND method IN ('CHECK', 'CASH', 'ZELLE', 'VENMO', 'STRIPE_ACH')
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).scalar()
    if sum(row["available"] for row in rows) - unapplied < amount:
        problem(409, "INSUFFICIENT_FUNDS", "This property does not have enough unreserved eligible cash.")
    left = amount
    for row in rows:
        take = min(left, row["available"])
        if take <= 0:
            continue
        session.execute(
            text("UPDATE funding_lots SET reserved_cents = reserved_cents + :take WHERE id = :id"),
            {"take": take, "id": row["id"]},
        )
        session.execute(
            text(
                """
                INSERT INTO fund_reservations (
                  id, organization_id, item_id, funding_lot_id, property_id, amount_cents, status
                ) VALUES (
                  :id, :organization_id, :item_id, :funding_lot_id, :property_id, :amount_cents, 'ACTIVE'
                )
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "item_id": item_id,
                "funding_lot_id": row["id"],
                "property_id": property_id,
                "amount_cents": take,
            },
        )
        left -= take
        if left == 0:
            return


def _release_reservations(session, organization_id, batch_id) -> None:
    rows = session.execute(
        text(
            """
            SELECT r.id, r.funding_lot_id, r.amount_cents
            FROM fund_reservations AS r
            JOIN distribution_items AS i ON i.id = r.item_id AND i.organization_id = r.organization_id
            WHERE r.organization_id = :organization_id AND i.batch_id = :batch_id AND r.status = 'ACTIVE'
            """
        ),
        {"organization_id": organization_id, "batch_id": batch_id},
    ).mappings().all()
    for row in rows:
        session.execute(
            text("UPDATE funding_lots SET reserved_cents = reserved_cents - :amount WHERE id = :id"),
            {"amount": row["amount_cents"], "id": row["funding_lot_id"]},
        )
        session.execute(text("UPDATE fund_reservations SET status = 'RELEASED' WHERE id = :id"), {"id": row["id"]})


def _hash(session, organization_id, batch_id) -> str:
    batch = _lock_batch(session, organization_id, batch_id)
    items = _items(session, organization_id, batch_id)
    reservations = session.execute(
        text(
            """
            SELECT r.funding_lot_id, r.amount_cents, r.item_id
            FROM fund_reservations AS r
            JOIN distribution_items AS i ON i.id = r.item_id AND i.organization_id = r.organization_id
            WHERE r.organization_id = :organization_id AND i.batch_id = :batch_id
              AND r.status IN ('ACTIVE', 'CONSUMED')
            """
        ),
        {"organization_id": organization_id, "batch_id": batch_id},
    ).mappings().all()
    payload = {
        "as_of": str(batch["as_of"]),
        "property_id": str(batch["property_id"]),
        "items": [
            {
                "amount_cents": item["amount_cents"],
                "destination_version": item["destination_version"],
                "kind": item["kind"],
                "liability_id": None if item["liability_id"] is None else str(item["liability_id"]),
                "recipient_id": str(item["recipient_party_id"]),
            }
            for item in sorted(items, key=lambda row: str(row["id"]))
        ],
        "reservations": [
            {"amount_cents": row["amount_cents"], "funding_lot_id": str(row["funding_lot_id"]), "item_id": str(row["item_id"])}
            for row in sorted(reservations, key=lambda row: (str(row["item_id"]), str(row["funding_lot_id"])))
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _assert_snapshot_inputs(session, organization_id, batch_id) -> None:
    batch = _lock_batch(session, organization_id, batch_id)
    items = sorted(_items(session, organization_id, batch_id), key=lambda item: str(item["recipient_party_id"]))
    for item in items:
        if item["status"] == "CANCELED":
            continue
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": f"payee-destination:{organization_id}:{item['recipient_party_id']}"},
        )
        destination = session.execute(
            text(
                """
                SELECT party_id, version FROM payee_destinations
                WHERE organization_id = :organization_id AND id = :id
                  AND active = true
                """
            ),
            {"organization_id": organization_id, "id": item["destination_id"]},
        ).mappings().first()
        if (
            destination is None
            or destination["party_id"] != item["recipient_party_id"]
            or destination["version"] != item["destination_version"]
        ):
            problem(409, "APPROVAL_INVALID", "The payee destination does not match the approved recipient.")
        reserved = session.execute(
            text(
                """
                SELECT coalesce(sum(amount_cents), 0)
                FROM fund_reservations
                WHERE organization_id = :organization_id AND item_id = :item_id
                  AND status IN ('ACTIVE', 'CONSUMED')
                """
            ),
            {"organization_id": organization_id, "item_id": item["id"]},
        ).scalar()
        if int(reserved) != item["amount_cents"]:
            problem(409, "APPROVAL_INVALID", "Reserved funds no longer match the approved amount.")
        if item["status"] in {"SETTLED", "RETURNED"}:
            continue
        if item["kind"] == "OWNER":
            payable = _owner_balance(session, organization_id, batch["property_id"], item["recipient_party_id"], "2020")
        elif item["kind"] == "MANAGEMENT":
            payable = _account_balance(session, organization_id, "2050", property_id=batch["property_id"])
        else:
            invoice = _lock_invoice(session, organization_id, item["liability_id"])
            if invoice["property_id"] != batch["property_id"] or invoice["contractor_party_id"] != item["recipient_party_id"] or invoice["payable_journal_id"] is None:
                problem(409, "APPROVAL_INVALID", "The invoice no longer matches the payment.")
            payable = invoice["total_cents"] - invoice["credited_cents"] - invoice["settled_cents"]
        committed = session.execute(
            text(
                """
                SELECT coalesce(sum(r.amount_cents), 0)
                FROM fund_reservations AS r
                JOIN distribution_items AS i ON i.organization_id = r.organization_id AND i.id = r.item_id
                WHERE r.organization_id = :organization_id AND r.property_id = :property_id AND r.status = 'ACTIVE'
                  AND ((:kind = 'OWNER' AND i.kind = 'OWNER' AND i.recipient_party_id = :recipient_id)
                    OR (:kind = 'MANAGEMENT' AND i.kind = 'MANAGEMENT')
                    OR (:kind = 'CONTRACTOR' AND i.kind = 'CONTRACTOR' AND i.liability_id = :liability_id))
                """
            ),
            {"organization_id": organization_id, "property_id": batch["property_id"], "kind": item["kind"],
             "recipient_id": item["recipient_party_id"], "liability_id": item["liability_id"]},
        ).scalar()
        if int(committed) > payable:
            problem(409, "SETTLEMENT_EXCEEDS_PAYABLE", "Reserved payments exceed the remaining payable; cancel and recalculate the affected proposals.")


def _require_current_approval(session, organization_id, batch_id, now=None):
    batch = _lock_batch(session, organization_id, batch_id)
    if _lock_property(session, organization_id, batch["property_id"]):
        problem(409, "DISBURSEMENTS_FROZEN", "Disbursements for this property are frozen.")
    if now is not None and batch["expires_at"] is not None and batch["expires_at"] <= now:
        session.execute(
            text("UPDATE distribution_batches SET status = 'EXPIRED' WHERE organization_id = :organization_id AND id = :id"),
            {"organization_id": organization_id, "id": batch_id},
        )
        problem(409, "APPROVAL_EXPIRED", "The approval has expired.")
    if batch["status"] not in {"APPROVED", "PARTIALLY_SETTLED", "UNKNOWN", "SETTLED"}:
        problem(409, "APPROVAL_INVALID", "The batch is not approved.")
    _assert_snapshot_inputs(session, organization_id, batch_id)
    for item in _items(session, organization_id, batch_id):
        if _current_destination_version(session, organization_id, item) != item["destination_version"]:
            problem(409, "APPROVAL_INVALID", "The payee destination version changed after approval.")
    current = _hash(session, organization_id, batch_id)
    if current != batch["snapshot_hash"]:
        problem(409, "APPROVAL_INVALID", "Amount, destination, or reservation inputs changed after approval.")
    return batch


def _refresh_status(session, organization_id, batch_id) -> dict:
    items = _items(session, organization_id, batch_id)
    statuses = {item["status"] for item in items}
    if statuses == {"SETTLED"}:
        status = "SETTLED"
    elif "UNKNOWN" in statuses:
        status = "UNKNOWN"
    elif "SETTLED" in statuses:
        status = "PARTIALLY_SETTLED"
    elif statuses == {"FAILED"}:
        status = "FAILED"
    else:
        status = "APPROVED"
    session.execute(
        text("UPDATE distribution_batches SET status = :status WHERE organization_id = :organization_id AND id = :id"),
        {"status": status, "organization_id": organization_id, "id": batch_id},
    )
    body = get_batch(session, organization_id, batch_id)
    body["simulator"] = True
    body["bank_contacted"] = False
    return body


def _event(session, organization_id, item, kind: str, evidence: str, simulator: bool = True) -> None:
    session.execute(
        text(
            """
            INSERT INTO payment_events (
              id, organization_id, item_id, provider_key, kind, simulator, evidence
            ) VALUES (
              :id, :organization_id, :item_id, :provider_key, :kind, :simulator, :evidence
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "item_id": item["id"],
            "provider_key": item["provider_key"],
            "kind": kind,
            "simulator": simulator,
            "evidence": evidence,
        },
    )


def _current_destination_version(session, organization_id, item) -> int | None:
    active = _active_destination(session, organization_id, item["recipient_party_id"])
    if active is None:
        return None
    return active["version"]


def _active_destination(session, organization_id, party_id):
    return session.execute(
        text(
            """
            SELECT id, version FROM payee_destinations
            WHERE organization_id = :organization_id AND party_id = :party_id AND active = true
            ORDER BY version DESC LIMIT 1
            """
        ),
        {"organization_id": organization_id, "party_id": party_id},
    ).mappings().first()


def _items(session, organization_id, batch_id):
    return session.execute(
        text(
            """
            SELECT i.*, d.channel, d.masked_label AS destination_label
            FROM distribution_items AS i
            LEFT JOIN payee_destinations AS d ON d.organization_id = i.organization_id AND d.id = i.destination_id
            WHERE i.organization_id = :organization_id AND i.batch_id = :batch_id
            ORDER BY i.created_at, i.id
            """
        ),
        {"organization_id": organization_id, "batch_id": batch_id},
    ).mappings().all()


def _lock_batch(session, organization_id, batch_id):
    row = session.execute(
        text("SELECT * FROM distribution_batches WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": batch_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Distribution batch not found.")
    return row
