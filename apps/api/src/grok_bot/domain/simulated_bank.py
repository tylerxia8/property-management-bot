from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import text

from grok_bot.domain.accounting import _lock_property, allocate_receipt, apply_reserve_top_up, create_bank_account, create_deposit, create_receipt, make_available, publish_agreement, publish_ownership, verify_receipt
from grok_bot.domain.controls import outbound_flags
from grok_bot.domain.distributions import _event, _items, _lock_batch, _refresh_status, _require_current_approval, _settle_item, get_batch
from grok_bot.domain.records import write_audit
from grok_bot.errors import problem


def account_for_property(session, organization_id, property_id):
    return session.execute(
        text("SELECT * FROM simulated_bank_accounts WHERE organization_id = :organization_id AND property_id = :property_id"),
        {"organization_id": organization_id, "property_id": property_id},
    ).mappings().first()


def snapshot(session, organization_id) -> dict:
    accounts = session.execute(
        text(
            """
            SELECT a.id, a.property_id, p.name AS property_name, a.next_outcome,
              coalesce(sum(CASE WHEN t.status = 'FAILED' THEN 0
                WHEN t.kind = 'RECEIPT' THEN t.amount_cents ELSE -t.amount_cents END), 0) AS balance_cents
            FROM simulated_bank_accounts AS a
            JOIN properties AS p ON p.organization_id = a.organization_id AND p.id = a.property_id
            LEFT JOIN simulated_bank_transactions AS t ON t.organization_id = a.organization_id AND t.account_id = a.id
            WHERE a.organization_id = :organization_id
            GROUP BY a.id, a.property_id, p.name, a.next_outcome
            ORDER BY p.name, a.id
            """
        ),
        {"organization_id": organization_id},
    ).mappings().all()
    transactions = session.execute(
        text("SELECT * FROM simulated_bank_transactions WHERE organization_id = :organization_id ORDER BY created_at DESC, id DESC LIMIT 100"),
        {"organization_id": organization_id},
    ).mappings().all()
    batches = session.execute(
        text(
            """
            SELECT b.id FROM distribution_batches AS b
            JOIN simulated_bank_accounts AS a ON a.organization_id = b.organization_id AND a.property_id = b.property_id
            WHERE b.organization_id = :organization_id ORDER BY b.created_at DESC, b.id DESC LIMIT 20
            """
        ),
        {"organization_id": organization_id},
    ).scalars().all()
    return {
        "simulator": True,
        "bank_contacted": False,
        "enabled": True,
        "accounts": [{**dict(row), "id": str(row["id"]), "property_id": str(row["property_id"]), "balance_cents": int(row["balance_cents"])} for row in accounts],
        "transactions": [
            {key: str(row[key]) if isinstance(row[key], UUID) else row[key].isoformat() if key == "created_at" else row[key]
             for key in ("id", "account_id", "kind", "channel", "amount_cents", "status", "reference", "created_at", "item_id", "receipt_id")}
            for row in transactions
        ],
        "batches": [get_batch(session, organization_id, batch_id) for batch_id in batches],
    }


def create_account(session, principal, property_id, request_id) -> None:
    _lock_property(session, principal.organization_id, property_id)
    if session.execute(text("SELECT 1 FROM stripe_properties WHERE organization_id = :org AND property_id = :property"), {"org": principal.organization_id, "property": property_id}).scalar():
        problem(409, "BANKING_MODE_CONFLICT", "This property uses Stripe; simulated bank funds cannot be mixed with it.")
    if account_for_property(session, principal.organization_id, property_id) is not None:
        return
    account = create_bank_account(session, principal.organization_id, "Simulated Wells Fargo account", "SIMULATED")
    session.execute(
        text("INSERT INTO simulated_bank_accounts (id, organization_id, property_id) VALUES (:id, :organization_id, :property_id)"),
        {"id": UUID(account["id"]), "organization_id": principal.organization_id, "property_id": property_id},
    )
    write_audit(
        session, organization_id=principal.organization_id, actor_id=principal.user_id,
        action="simulated_bank.created", target_type="bank_account", target_id=UUID(account["id"]),
        target_version=None, request_id=request_id, before_state=None,
        after_state={"simulator": True, "bank_contacted": False, "property_id": str(property_id)},
    )


def setup_demo(session, principal, request_id) -> None:
    from grok_bot.domain.distributions import _active_destination, create_destination
    from grok_bot.seed import DEMO_ORG, DEMO_OWNER_PARTY, DEMO_PROPERTY

    if principal.organization_id != DEMO_ORG:
        problem(403, "FORBIDDEN", "Fictional setup is limited to the sample organization.")
    _lock_property(session, principal.organization_id, DEMO_PROPERTY)
    ownership = session.execute(
        text("SELECT 1 FROM ownership_periods WHERE organization_id = :organization_id AND property_id = :property_id LIMIT 1"),
        {"organization_id": principal.organization_id, "property_id": DEMO_PROPERTY},
    ).scalar()
    if not ownership:
        publish_ownership(session, principal.organization_id, DEMO_PROPERTY, date(2020, 1, 1), date(2100, 1, 1), [{"owner_party_id": str(DEMO_OWNER_PARTY), "weight": 1_000_000}])
    agreement = session.execute(
        text("SELECT 1 FROM agreements WHERE organization_id = :organization_id AND property_id = :property_id LIMIT 1"),
        {"organization_id": principal.organization_id, "property_id": DEMO_PROPERTY},
    ).scalar()
    if not agreement:
        publish_agreement(session, principal.organization_id, DEMO_PROPERTY, {
            "start_date": date(2020, 1, 1), "end_date": date(2100, 1, 1),
            "rate_numerator": 0, "rate_denominator": 1, "reserve_target_total_cents": 0,
        })
    if _active_destination(session, principal.organization_id, DEMO_OWNER_PARTY) is None:
        create_destination(session, principal.organization_id, DEMO_OWNER_PARTY, "Fictional owner · Zelle", "ZELLE")
    create_account(session, principal, DEMO_PROPERTY, request_id)
    write_audit(
        session, organization_id=principal.organization_id, actor_id=principal.user_id,
        action="simulated_bank.demo_setup", target_type="property", target_id=DEMO_PROPERTY,
        target_version=None, request_id=request_id, before_state=None,
        after_state={"simulator": True, "fixture_policy": "zero_fee_zero_reserve_when_unconfigured"},
    )


def receive_rent(session, principal, body, now, request_id) -> None:
    account = _lock_account(session, principal.organization_id, body.account_id)
    unit_id = session.execute(
        text("SELECT unit_id FROM leases WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": principal.organization_id, "id": body.lease_id},
    ).scalar()
    if unit_id is None:
        problem(404, "NOT_FOUND", "Lease not found.")
    receipt = create_receipt(session, principal.organization_id, principal.user_id, {
        "property_id": account["property_id"], "unit_id": unit_id, "lease_id": body.lease_id,
        "payer_party_id": body.payer_party_id, "method": body.channel, "amount_cents": body.amount_cents,
        "received_at": now, "posting_date": body.posting_date, "reference": body.reference,
    }, request_id)
    receipt_id = UUID(receipt["id"])
    create_deposit(session, principal.organization_id, {
        "property_id": account["property_id"], "bank_account_id": body.account_id,
        "slip_reference": f"simulated:{receipt_id}", "deposited_on": body.posting_date,
        "items": [{"receipt_id": receipt_id, "amount_cents": body.amount_cents}],
    })
    verify_receipt(session, principal.organization_id, receipt_id, body.amount_cents)
    make_available(session, principal.organization_id, receipt_id, body.amount_cents, body.posting_date)
    allocate_receipt(session, principal.organization_id, principal.user_id, receipt_id, None, body.posting_date, request_id)
    apply_reserve_top_up(session, principal.organization_id, account["property_id"], body.posting_date)
    session.execute(
        text(
            """
            INSERT INTO simulated_bank_transactions
              (id, organization_id, account_id, kind, channel, amount_cents, status, reference, receipt_id)
            VALUES (:id, :organization_id, :account_id, 'RECEIPT', :channel, :amount_cents, 'SETTLED', :reference, :receipt_id)
            """
        ),
        {"id": uuid4(), "organization_id": principal.organization_id, "account_id": body.account_id,
         "channel": body.channel, "amount_cents": body.amount_cents, "reference": body.reference, "receipt_id": receipt_id},
    )


def set_outcome(session, principal, account_id, outcome, request_id) -> None:
    account = _lock_account(session, principal.organization_id, account_id)
    session.execute(
        text("UPDATE simulated_bank_accounts SET next_outcome = :outcome WHERE organization_id = :organization_id AND id = :id"),
        {"outcome": outcome, "organization_id": principal.organization_id, "id": account_id},
    )
    write_audit(
        session, organization_id=principal.organization_id, actor_id=principal.user_id,
        action="simulated_bank.outcome_changed", target_type="bank_account", target_id=account_id,
        target_version=None, request_id=request_id, before_state={"outcome": account["next_outcome"]},
        after_state={"outcome": outcome, "simulator": True},
    )


def send_approved(session, organization_id, batch_id, posting_date, now) -> dict:
    batch = _require_current_approval(session, organization_id, batch_id, now)
    if not outbound_flags(session, organization_id)["payment_enabled"]:
        problem(409, "KILL_SWITCH", "Simulated payout sending is switched off.")
    account = account_for_property(session, organization_id, batch["property_id"])
    if account is None:
        problem(409, "CONFIGURATION_REQUIRED", "Create a simulated account for this property first.")
    account = _lock_account(session, organization_id, account["id"])
    for item in _items(session, organization_id, batch_id):
        if item["status"] in {"SETTLED", "UNKNOWN", "RETURNED", "CANCELED", "FAILED"}:
            continue
        reserved = session.execute(
            text(
                """
                SELECT coalesce(sum(r.amount_cents), 0)
                FROM fund_reservations AS r
                JOIN funding_lots AS l ON l.organization_id = r.organization_id AND l.id = r.funding_lot_id
                WHERE r.organization_id = :organization_id AND r.item_id = :item_id AND r.status = 'ACTIVE'
                  AND l.bank_account_id = :account_id
                """
            ),
            {"organization_id": organization_id, "item_id": item["id"], "account_id": account["id"]},
        ).scalar()
        if int(reserved) != item["amount_cents"]:
            problem(409, "SIMULATED_FUNDS_REQUIRED", "A simulated payout must be fully funded by its simulated account.")
        manual = session.execute(
            text("SELECT 1 FROM payment_events WHERE organization_id = :organization_id AND item_id = :item_id AND kind = 'MANUAL_SUBMISSION'"),
            {"organization_id": organization_id, "item_id": item["id"]},
        ).scalar()
        if manual:
            problem(409, "EVIDENCE_STATE", "A manually submitted payment cannot be sent by the simulated bank.")
        previous = session.execute(
            text("SELECT status FROM simulated_bank_transactions WHERE organization_id = :organization_id AND item_id = :item_id"),
            {"organization_id": organization_id, "item_id": item["id"]},
        ).scalar()
        if previous is not None:
            problem(409, "EVIDENCE_STATE", "This simulated payment already has a bank result; reconcile it instead.")
        outcome = account["next_outcome"]
        balance = session.execute(
            text("SELECT coalesce(sum(CASE WHEN status = 'FAILED' THEN 0 WHEN kind = 'RECEIPT' THEN amount_cents ELSE -amount_cents END), 0) FROM simulated_bank_transactions WHERE organization_id = :organization_id AND account_id = :account_id"),
            {"organization_id": organization_id, "account_id": account["id"]},
        ).scalar()
        declined = outcome == "fail" or balance < item["amount_cents"]
        channel = session.execute(
            text("SELECT channel FROM payee_destinations WHERE organization_id = :organization_id AND id = :id"),
            {"organization_id": organization_id, "id": item["destination_id"]},
        ).scalar_one()
        session.execute(
            text(
                """
                INSERT INTO simulated_bank_transactions
                  (id, organization_id, account_id, kind, channel, amount_cents, status, reference, item_id)
                VALUES (:id, :organization_id, :account_id, 'PAYOUT', :channel, :amount_cents, :status, :reference, :item_id)
                """
            ),
            {"id": uuid4(), "organization_id": organization_id, "account_id": account["id"], "channel": channel,
             "amount_cents": item["amount_cents"], "status": "FAILED" if declined else "SETTLED",
             "reference": item["provider_key"], "item_id": item["id"]},
        )
        session.execute(
            text("UPDATE simulated_bank_accounts SET next_outcome = 'settle' WHERE organization_id = :organization_id AND id = :id"),
            {"organization_id": organization_id, "id": account["id"]},
        )
        account = {**account, "next_outcome": "settle"}
        if declined or outcome == "timeout":
            status = "FAILED" if declined else "UNKNOWN"
            session.execute(
                text("UPDATE distribution_items SET status = :status WHERE organization_id = :organization_id AND id = :id"),
                {"status": status, "organization_id": organization_id, "id": item["id"]},
            )
            _event(session, organization_id, item, f"SIMULATED_BANK_{status}", "Simulated decline." if declined else "Simulated bank accepted payment; response was lost.")
        else:
            _settle_item(session, organization_id, batch["property_id"], item, posting_date, event_kind="SIMULATED_BANK_SETTLED")
    return _refresh_status(session, organization_id, batch_id)


def reconcile(session, organization_id, batch_id, posting_date) -> None:
    batch = _lock_batch(session, organization_id, batch_id)
    account = account_for_property(session, organization_id, batch["property_id"])
    if account is None:
        problem(409, "CONFIGURATION_REQUIRED", "This batch has no simulated account.")
    _lock_account(session, organization_id, account["id"])
    items = _items(session, organization_id, batch_id)
    if not any(item["status"] == "UNKNOWN" for item in items):
        return
    for item in items:
        if item["status"] != "UNKNOWN":
            continue
        transaction = session.execute(
            text("SELECT * FROM simulated_bank_transactions WHERE organization_id = :organization_id AND item_id = :item_id"),
            {"organization_id": organization_id, "item_id": item["id"]},
        ).mappings().first()
        if transaction is None or transaction["status"] != "SETTLED" or transaction["amount_cents"] != item["amount_cents"]:
            problem(409, "BATCH_UNCERTAIN", "No matching successful simulated bank transfer was found.")
        _settle_item(session, organization_id, batch["property_id"], item, posting_date, event_kind="SIMULATED_BANK_SETTLED")
    _refresh_status(session, organization_id, batch_id)


def _lock_account(session, organization_id, account_id):
    property_id = session.execute(
        text("SELECT property_id FROM simulated_bank_accounts WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": account_id},
    ).scalar()
    if property_id is None:
        problem(404, "NOT_FOUND", "Simulated bank account not found.")
    _lock_property(session, organization_id, property_id)
    return session.execute(
        text("SELECT * FROM simulated_bank_accounts WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": account_id},
    ).mappings().one()
