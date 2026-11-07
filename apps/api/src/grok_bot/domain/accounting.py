import hashlib
import json
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.domain.money import allocate_by_weights, round_half_up_ratio
from grok_bot.domain.records import write_audit, write_outbox
from grok_bot.errors import problem

RENT_METHODS = {"CHECK", "CASH"}
DEPOSIT_METHODS = {"SECURITY_DEPOSIT_CHECK", "SECURITY_DEPOSIT_CASH"}


def create_party(session: Session, organization_id: UUID, display_name: str, kind: str) -> dict:
    party_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO parties (id, organization_id, display_name, kind)
            VALUES (:id, :organization_id, :display_name, :kind)
            """
        ),
        {
            "id": party_id,
            "organization_id": organization_id,
            "display_name": display_name,
            "kind": kind,
        },
    )
    return {"id": str(party_id), "display_name": display_name, "kind": kind}


def create_bank_account(session: Session, organization_id: UUID, display_name: str, masked_label: str) -> dict:
    account_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO bank_accounts (id, organization_id, display_name, masked_label)
            VALUES (:id, :organization_id, :display_name, :masked_label)
            """
        ),
        {
            "id": account_id,
            "organization_id": organization_id,
            "display_name": display_name,
            "masked_label": masked_label,
        },
    )
    return {"id": str(account_id), "display_name": display_name, "masked_label": masked_label, "currency": "USD"}


def create_lease(session: Session, organization_id: UUID, unit_id: UUID, start_date: date, end_date: date, agreed_rent_cents: int) -> dict:
    lease_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO leases (
              id, organization_id, unit_id, start_date, end_date, agreed_rent_cents
            ) VALUES (
              :id, :organization_id, :unit_id, :start_date, :end_date, :agreed_rent_cents
            )
            """
        ),
        {
            "id": lease_id,
            "organization_id": organization_id,
            "unit_id": unit_id,
            "start_date": start_date,
            "end_date": end_date,
            "agreed_rent_cents": agreed_rent_cents,
        },
    )
    return {"id": str(lease_id), "unit_id": str(unit_id), "agreed_rent_cents": agreed_rent_cents}


def publish_ownership(session: Session, organization_id: UUID, property_id: UUID, start_date: date, end_date: date, shares: list[dict]) -> dict:
    weights = [(UUID(item["owner_party_id"]), int(item["weight"])) for item in shares]
    if sum(weight for _, weight in weights) != 1_000_000:
        problem(422, "OWNERSHIP_WEIGHTS_INVALID", "Ownership weights must total 1000000.")
    _lock_property(session, organization_id, property_id)
    period_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO ownership_periods (
              id, organization_id, property_id, start_date, end_date
            ) VALUES (
              :id, :organization_id, :property_id, :start_date, :end_date
            )
            """
        ),
        {
            "id": period_id,
            "organization_id": organization_id,
            "property_id": property_id,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    for owner_id, weight in weights:
        session.execute(
            text(
                """
                INSERT INTO ownership_shares (
                  id, organization_id, period_id, owner_party_id, weight
                ) VALUES (
                  :id, :organization_id, :period_id, :owner_party_id, :weight
                )
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "period_id": period_id,
                "owner_party_id": owner_id,
                "weight": weight,
            },
        )
    return {"id": str(period_id), "property_id": str(property_id), "shares": shares}


def publish_agreement(session: Session, organization_id: UUID, property_id: UUID, body: dict) -> dict:
    if body.get("responsibility_mode", "OWNERSHIP_WEIGHTS") != "OWNERSHIP_WEIGHTS":
        problem(
            409,
            "CONFIGURATION_REQUIRED",
            "Only ownership-weight responsibility is configured. Other responsibility rules are not defined.",
        )
    _lock_property(session, organization_id, property_id)
    agreement_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO agreements (
              id, organization_id, property_id, start_date, end_date, responsibility_mode
            ) VALUES (
              :id, :organization_id, :property_id, :start_date, :end_date, 'OWNERSHIP_WEIGHTS'
            )
            """
        ),
        {
            "id": agreement_id,
            "organization_id": organization_id,
            "property_id": property_id,
            "start_date": body["start_date"],
            "end_date": body["end_date"],
        },
    )
    session.execute(
        text(
            """
            INSERT INTO fee_rules (
              id, organization_id, agreement_id, fee_base, rate_numerator, rate_denominator,
              fixed_cents, cap_cents, minimum_cents
            ) VALUES (
              :id, :organization_id, :agreement_id, 'ALLOCATED_RENT', :rate_numerator,
              :rate_denominator, :fixed_cents, :cap_cents, :minimum_cents
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "agreement_id": agreement_id,
            "rate_numerator": body["rate_numerator"],
            "rate_denominator": body["rate_denominator"],
            "fixed_cents": body.get("fixed_cents", 0),
            "cap_cents": body.get("cap_cents"),
            "minimum_cents": body.get("minimum_cents"),
        },
    )
    if body.get("reserve_target_total_cents") is not None:
        session.execute(
            text(
                """
                INSERT INTO reserve_rules (id, organization_id, agreement_id, target_total_cents)
                VALUES (:id, :organization_id, :agreement_id, :target_total_cents)
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "agreement_id": agreement_id,
                "target_total_cents": body["reserve_target_total_cents"],
            },
        )
    return {"id": str(agreement_id), "property_id": str(property_id)}


def create_receipt(session: Session, organization_id: UUID, actor_id: UUID, body: dict, request_id: str) -> dict:
    method = body["method"]
    if method == "DIRECT_BANK":
        problem(
            409,
            "DIRECT_BANK_TEMPLATE_UNCONFIGURED",
            "Direct-bank receipt journal legs are not configured.",
        )
    if method not in RENT_METHODS | DEPOSIT_METHODS:
        problem(422, "VALIDATION_ERROR", "Receipt method is not supported.")
    if body.get("currency", "USD") != "USD":
        problem(422, "UNSUPPORTED_CURRENCY", "Only USD cents are supported.")
    receipt_id = uuid4()
    number = session.execute(
        text(
            """
            INSERT INTO receipt_counters (organization_id, last_number)
            VALUES (:organization_id, 1)
            ON CONFLICT (organization_id) DO UPDATE
            SET last_number = receipt_counters.last_number + 1,
                updated_at = clock_timestamp()
            RETURNING last_number
            """
        ),
        {"organization_id": organization_id},
    ).scalar()
    purpose = "SECURITY_DEPOSIT" if method in DEPOSIT_METHODS else "RENT"
    credit_account = "2070" if purpose == "SECURITY_DEPOSIT" else "2010"
    session.execute(
        text(
            """
            INSERT INTO receipts (
              id, organization_id, property_id, unit_id, lease_id, payer_party_id, method,
              amount_cents, received_at, posting_date, reference_masked, receipt_number,
              service_period, status
            ) VALUES (
              :id, :organization_id, :property_id, :unit_id, :lease_id, :payer_party_id, :method,
              :amount_cents, :received_at, :posting_date, :reference_masked, :receipt_number,
              :service_period, 'RECORDED'
            )
            """
        ),
        {
            "id": receipt_id,
            "organization_id": organization_id,
            "property_id": body["property_id"],
            "unit_id": body["unit_id"],
            "lease_id": body["lease_id"],
            "payer_party_id": body["payer_party_id"],
            "method": method,
            "amount_cents": body["amount_cents"],
            "received_at": body["received_at"],
            "posting_date": body["posting_date"],
            "reference_masked": body["reference"],
            "receipt_number": number,
            "service_period": body.get("service_period"),
        },
    )
    _post(
        session,
        organization_id,
        "RECEIPT_CUSTODY",
        receipt_id,
        body["posting_date"],
        [
            _line("1010", "DEBIT", body["amount_cents"], body, purpose),
            _line(credit_account, "CREDIT", body["amount_cents"], body, purpose),
        ],
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="receipt.recorded",
        target_type="receipt",
        target_id=receipt_id,
        target_version=1,
        request_id=request_id,
        before_state=None,
        after_state={"amount_cents": body["amount_cents"], "method": method, "status": "RECORDED"},
    )
    write_outbox(
        session,
        organization_id=organization_id,
        event_type="receipt.recorded",
        dedup_key=f"receipt.recorded:{receipt_id}",
        property_id=body["property_id"],
        payload={"receipt_id": str(receipt_id), "amount_cents": body["amount_cents"]},
    )
    return get_receipt(session, organization_id, receipt_id)


def create_deposit(session: Session, organization_id: UUID, body: dict) -> dict:
    _lock_property(session, organization_id, body["property_id"])
    total = 0
    locked = []
    for item in body["items"]:
        receipt_id = item["receipt_id"] if isinstance(item["receipt_id"], UUID) else UUID(str(item["receipt_id"]))
        receipt = _lock_receipt(session, organization_id, receipt_id)
        amount = int(item["amount_cents"])
        remaining = receipt["amount_cents"] - receipt["deposited_cents"] - receipt["returned_cents"]
        if amount > remaining or receipt["property_id"] != body["property_id"]:
            problem(409, "DEPOSIT_EXCEEDS_RECEIPT", "The deposit slice exceeds the receipt that is still in custody.")
        total += amount
        locked.append((receipt, amount))
    batch_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO deposit_batches (
              id, organization_id, bank_account_id, slip_reference, deposited_on, total_cents
            ) VALUES (
              :id, :organization_id, :bank_account_id, :slip_reference, :deposited_on, :total_cents
            )
            """
        ),
        {
            "id": batch_id,
            "organization_id": organization_id,
            "bank_account_id": body["bank_account_id"],
            "slip_reference": body["slip_reference"],
            "deposited_on": body["deposited_on"],
            "total_cents": total,
        },
    )
    for receipt, amount in locked:
        session.execute(
            text(
                """
                INSERT INTO deposit_items (id, organization_id, batch_id, receipt_id, amount_cents)
                VALUES (:id, :organization_id, :batch_id, :receipt_id, :amount_cents)
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "batch_id": batch_id,
                "receipt_id": receipt["id"],
                "amount_cents": amount,
            },
        )
        purpose = _purpose(receipt["method"])
        _post(
            session,
            organization_id,
            "RECEIPT_DEPOSIT",
            uuid4(),
            body["deposited_on"],
            [
                _line("1020", "DEBIT", amount, receipt, purpose, bank_account_id=body["bank_account_id"]),
                _line("1010", "CREDIT", amount, receipt, purpose),
            ],
        )
        deposited = receipt["deposited_cents"] + amount
        _update_receipt_counters(session, organization_id, receipt["id"], deposited_cents=deposited, bank_account_id=body["bank_account_id"])
    return {"id": str(batch_id), "total_cents": total, "currency": "USD"}


def verify_receipt(session: Session, organization_id: UUID, receipt_id: UUID, amount_cents: int) -> dict:
    receipt = _lock_receipt(session, organization_id, receipt_id)
    if amount_cents > receipt["deposited_cents"] - receipt["verified_cents"]:
        problem(409, "VERIFICATION_EXCEEDS_DEPOSIT", "Verification cannot exceed the deposited amount still unverified.")
    _update_receipt_counters(session, organization_id, receipt_id, verified_cents=receipt["verified_cents"] + amount_cents)
    return get_receipt(session, organization_id, receipt_id)


def make_available(session: Session, organization_id: UUID, receipt_id: UUID, amount_cents: int, posting_date: date) -> dict:
    receipt = _lock_receipt(session, organization_id, receipt_id)
    if receipt["bank_account_id"] is None:
        problem(409, "DEPOSIT_REQUIRED", "Availability requires a deposit to a bank account.")
    if amount_cents > receipt["verified_cents"] - receipt["available_cents"]:
        problem(409, "AVAILABILITY_EXCEEDS_VERIFIED", "Availability cannot exceed the verified amount still held.")
    purpose = _purpose(receipt["method"])
    source_id = uuid4()
    _post(
        session,
        organization_id,
        "RECEIPT_AVAILABLE",
        source_id,
        posting_date,
        [
            _line("1030", "DEBIT", amount_cents, receipt, purpose, bank_account_id=receipt["bank_account_id"]),
            _line("1020", "CREDIT", amount_cents, receipt, purpose, bank_account_id=receipt["bank_account_id"]),
        ],
    )
    session.execute(
        text(
            """
            INSERT INTO funding_lots (
              id, organization_id, property_id, bank_account_id, purpose, amount_cents,
              source_type, source_id
            ) VALUES (
              :id, :organization_id, :property_id, :bank_account_id, :purpose, :amount_cents,
              'RECEIPT_AVAILABLE', :source_id
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "property_id": receipt["property_id"],
            "bank_account_id": receipt["bank_account_id"],
            "purpose": purpose,
            "amount_cents": amount_cents,
            "source_id": source_id,
        },
    )
    available = receipt["available_cents"] + amount_cents
    available_at = datetime.now().astimezone() if available == receipt["amount_cents"] else None
    _update_receipt_counters(
        session,
        organization_id,
        receipt_id,
        available_cents=available,
        available_at=available_at,
        keep_available_at=available != receipt["amount_cents"],
    )
    return get_receipt(session, organization_id, receipt_id)


def allocate_receipt(session: Session, organization_id: UUID, actor_id: UUID, receipt_id: UUID, amount_cents: int | None, posting_date: date, request_id: str) -> dict:
    receipt = _lock_receipt(session, organization_id, receipt_id)
    _lock_property(session, organization_id, receipt["property_id"])
    if receipt["method"] in DEPOSIT_METHODS:
        problem(409, "SECURITY_DEPOSIT_RESTRICTED", "Security deposits cannot be allocated as rent or owner funds.")
    remaining = receipt["available_cents"] - receipt["allocated_cents"]
    amount = remaining if amount_cents is None else amount_cents
    if amount <= 0 or amount > remaining:
        problem(409, "ALLOCATION_EXCEEDS_AVAILABLE", "Allocation cannot exceed available unallocated cents.")
    weights = _weights_on(session, organization_id, receipt["property_id"], posting_date)
    fee_rule = _fee_rule_on(session, organization_id, receipt["property_id"], posting_date)
    first_slice = receipt["allocated_cents"] == 0
    fee = round_half_up_ratio(amount, fee_rule["rate_numerator"], fee_rule["rate_denominator"])
    if first_slice:
        fee += fee_rule["fixed_cents"]
    if fee_rule["cap_cents"] is not None:
        fee = min(fee, fee_rule["cap_cents"])
    if first_slice and fee_rule["minimum_cents"] is not None:
        fee = max(fee, fee_rule["minimum_cents"])
    owner_amounts = allocate_by_weights(amount, weights)
    fee_amounts = allocate_by_weights(fee, weights) if fee else {owner_id: 0 for owner_id, _ in weights}
    lines = [_line("2010", "DEBIT", amount, receipt, "RENT")]
    for owner_id, owner_amount in owner_amounts.items():
        if owner_amount:
            lines.append(_owner_line("2020", "CREDIT", owner_amount, receipt, owner_id))
    for owner_id, fee_amount in fee_amounts.items():
        if fee_amount:
            lines.append(_owner_line("2020", "DEBIT", fee_amount, receipt, owner_id))
    if fee:
        lines.append(_line("2050", "CREDIT", fee, receipt, "RENT"))
    _post(session, organization_id, "RECEIPT_ALLOCATION", uuid4(), posting_date, lines)
    _update_receipt_counters(
        session,
        organization_id,
        receipt_id,
        allocated_cents=receipt["allocated_cents"] + amount,
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="receipt.allocated",
        target_type="receipt",
        target_id=receipt_id,
        target_version=None,
        request_id=request_id,
        before_state={"allocated_cents": receipt["allocated_cents"]},
        after_state={"allocated_cents": receipt["allocated_cents"] + amount, "fee_cents": fee},
    )
    return get_receipt(session, organization_id, receipt_id)


def apply_reserve_top_up(session: Session, organization_id: UUID, property_id: UUID, posting_date: date) -> dict:
    _lock_property(session, organization_id, property_id)
    weights = _weights_on(session, organization_id, property_id, posting_date)
    rule = session.execute(
        text(
            """
            SELECT r.target_total_cents
            FROM reserve_rules AS r
            JOIN agreements AS a ON a.id = r.agreement_id AND a.organization_id = r.organization_id
            WHERE a.organization_id = :organization_id AND a.property_id = :property_id
              AND a.start_date <= :posting_date AND a.end_date > :posting_date
            """
        ),
        {"organization_id": organization_id, "property_id": property_id, "posting_date": posting_date},
    ).mappings().first()
    if rule is None:
        problem(409, "CONFIGURATION_REQUIRED", "A reserve target agreement is required.")
    targets = allocate_by_weights(rule["target_total_cents"], weights)
    lines = []
    total = 0
    applied = {}
    for owner_id, _weight in weights:
        unrestricted = _owner_balance(session, organization_id, property_id, owner_id, "2020")
        reserve = _owner_balance(session, organization_id, property_id, owner_id, "2030")
        top_up = min(max(0, targets[owner_id] - reserve), max(0, unrestricted))
        applied[str(owner_id)] = top_up
        total += top_up
        if top_up:
            lines.append(_owner_line("2020", "DEBIT", top_up, {"property_id": property_id, "lease_id": None}, owner_id))
            lines.append(_owner_line("2030", "CREDIT", top_up, {"property_id": property_id, "lease_id": None}, owner_id))
    if total:
        _consume_rent_lots(session, organization_id, property_id, total)
        source_id = uuid4()
        _post(session, organization_id, "RESERVE_TOP_UP", source_id, posting_date, lines)
        bank_account_id = _property_bank_account(session, organization_id, property_id)
        session.execute(
            text(
                """
                INSERT INTO funding_lots (
                  id, organization_id, property_id, bank_account_id, purpose, amount_cents,
                  source_type, source_id
                ) VALUES (
                  :id, :organization_id, :property_id, :bank_account_id, 'RESERVE', :amount_cents,
                  'RESERVE_TOP_UP', :source_id
                )
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "property_id": property_id,
                "bank_account_id": bank_account_id,
                "amount_cents": total,
                "source_id": source_id,
            },
        )
    return {"property_id": str(property_id), "top_up_cents": total, "owners": applied, "currency": "USD"}


def opening_reserve_cash(session: Session, organization_id: UUID, body: dict) -> dict:
    _lock_property(session, organization_id, body["property_id"])
    source_id = uuid4()
    _post(
        session,
        organization_id,
        "OPENING_RESERVE_CASH",
        source_id,
        body["posting_date"],
        [
            _line(
                "1030",
                "DEBIT",
                body["amount_cents"],
                body,
                "RESERVE",
                bank_account_id=body["bank_account_id"],
            ),
            _owner_line("2030", "CREDIT", body["amount_cents"], body, UUID(str(body["owner_party_id"]))),
        ],
    )
    session.execute(
        text(
            """
            INSERT INTO funding_lots (
              id, organization_id, property_id, bank_account_id, purpose, amount_cents,
              source_type, source_id
            ) VALUES (
              :id, :organization_id, :property_id, :bank_account_id, 'RESERVE', :amount_cents,
              'OPENING_RESERVE_CASH', :source_id
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "property_id": body["property_id"],
            "bank_account_id": body["bank_account_id"],
            "amount_cents": body["amount_cents"],
            "source_id": source_id,
        },
    )
    return {"id": str(source_id), "amount_cents": body["amount_cents"], "currency": "USD"}


def create_rent_charge(session: Session, organization_id: UUID, body: dict) -> dict:
    charge_id = uuid4()
    before = _journal_count(session, organization_id)
    session.execute(
        text(
            """
            INSERT INTO rent_charges (
              id, organization_id, lease_id, due_on, amount_cents, description
            ) VALUES (
              :id, :organization_id, :lease_id, :due_on, :amount_cents, :description
            )
            """
        ),
        {"id": charge_id, "organization_id": organization_id, **body},
    )
    if _journal_count(session, organization_id) != before:
        problem(500, "LEDGER_COUPLING", "A rent charge must not post custodial cash.")
    return {"id": str(charge_id), "amount_cents": body["amount_cents"], "journal_posted": False, "currency": "USD"}


def submit_invoice(session: Session, organization_id: UUID, body: dict) -> dict:
    total = sum(line["line_total_cents"] for line in body["lines"]) + body["tax_cents"]
    if total != body["total_cents"]:
        problem(422, "INVOICE_TOTAL_MISMATCH", "Invoice total does not match the recalculated lines and tax.")
    for line in body["lines"]:
        if line["quantity"] * line["unit_price_cents"] != line["line_total_cents"]:
            problem(422, "INVOICE_TOTAL_MISMATCH", "A line total does not match quantity times unit price.")
    invoice_id = uuid4()
    normalized = " ".join(body["invoice_number"].split()).upper()
    session.execute(
        text(
            """
            INSERT INTO invoices (
              id, organization_id, property_id, contractor_party_id, invoice_number,
              normalized_invoice_number, status, tax_cents, total_cents
            ) VALUES (
              :id, :organization_id, :property_id, :contractor_party_id, :invoice_number,
              :normalized_invoice_number, 'SUBMITTED', :tax_cents, :total_cents
            )
            """
        ),
        {
            "id": invoice_id,
            "organization_id": organization_id,
            "property_id": body["property_id"],
            "contractor_party_id": body["contractor_party_id"],
            "invoice_number": body["invoice_number"],
            "normalized_invoice_number": normalized,
            "tax_cents": body["tax_cents"],
            "total_cents": body["total_cents"],
        },
    )
    for line in body["lines"]:
        session.execute(
            text(
                """
                INSERT INTO invoice_lines (
                  id, organization_id, invoice_id, description, quantity, unit_price_cents, line_total_cents
                ) VALUES (
                  :id, :organization_id, :invoice_id, :description, :quantity, :unit_price_cents, :line_total_cents
                )
                """
            ),
            {"id": uuid4(), "organization_id": organization_id, "invoice_id": invoice_id, **line},
        )
    stored = get_invoice(session, organization_id, invoice_id)
    if stored["payable_journal_id"] is not None:
        problem(500, "LEDGER_COUPLING", "Submitting an invoice must not post a payable.")
    return stored


def approve_invoice(session: Session, organization_id: UUID, invoice_id: UUID, posting_date: date) -> dict:
    invoice = _lock_invoice(session, organization_id, invoice_id)
    if invoice["payable_journal_id"] is not None:
        return get_invoice(session, organization_id, invoice_id)
    weights = _weights_on(session, organization_id, invoice["property_id"], posting_date)
    period_id = _period_id_on(session, organization_id, invoice["property_id"], posting_date)
    shares = allocate_by_weights(invoice["total_cents"], weights)
    lines = []
    for owner_id, amount in shares.items():
        if amount:
            lines.append(
                _owner_line(
                    "2020",
                    "DEBIT",
                    amount,
                    {"property_id": invoice["property_id"], "lease_id": None},
                    owner_id,
                )
            )
    lines.append(_line("2040", "CREDIT", invoice["total_cents"], {"property_id": invoice["property_id"], "lease_id": None}, "RENT"))
    journal_id = _post(session, organization_id, "INVOICE_APPROVAL", invoice_id, posting_date, lines)
    session.execute(
        text(
            """
            UPDATE invoices
            SET status = 'APPROVED', ownership_period_id = :period_id, payable_journal_id = :journal_id,
                version = version + 1
            WHERE organization_id = :organization_id AND id = :id AND payable_journal_id IS NULL
            """
        ),
        {
            "period_id": period_id,
            "journal_id": journal_id,
            "organization_id": organization_id,
            "id": invoice_id,
        },
    )
    return get_invoice(session, organization_id, invoice_id)


def declare_distributions(session: Session, organization_id: UUID, property_id: UUID, posting_date: date) -> dict:
    frozen = _lock_property(session, organization_id, property_id)
    if frozen:
        problem(409, "DISBURSEMENTS_FROZEN", "Disbursements for this property are frozen.")
    weights = _weights_on(session, organization_id, property_id, posting_date)
    lines = []
    declared = []
    for owner_id, _weight in weights:
        balance = _owner_balance(session, organization_id, property_id, owner_id, "2020")
        if balance <= 0:
            continue
        declaration_id = uuid4()
        lines.append(_owner_line("2020", "DEBIT", balance, {"property_id": property_id, "lease_id": None}, owner_id))
        lines.append(_owner_line("2060", "CREDIT", balance, {"property_id": property_id, "lease_id": None}, owner_id))
        declared.append((declaration_id, owner_id, balance))
    if not lines:
        return {"property_id": str(property_id), "declarations": [], "currency": "USD"}
    journal_id = _post(session, organization_id, "OWNER_DISTRIBUTION_DECLARED", uuid4(), posting_date, lines)
    results = []
    for declaration_id, owner_id, amount in declared:
        session.execute(
            text(
                """
                INSERT INTO owner_declarations (
                  id, organization_id, property_id, owner_party_id, amount_cents, journal_id
                ) VALUES (
                  :id, :organization_id, :property_id, :owner_party_id, :amount_cents, :journal_id
                )
                """
            ),
            {
                "id": declaration_id,
                "organization_id": organization_id,
                "property_id": property_id,
                "owner_party_id": owner_id,
                "amount_cents": amount,
                "journal_id": journal_id,
            },
        )
        results.append({"id": str(declaration_id), "owner_party_id": str(owner_id), "amount_cents": amount})
    return {"property_id": str(property_id), "declarations": results, "currency": "USD"}


def settle_invoice(session: Session, organization_id: UUID, invoice_id: UUID, posting_date: date) -> dict:
    invoice = _lock_invoice(session, organization_id, invoice_id)
    frozen = _lock_property(session, organization_id, invoice["property_id"])
    if frozen:
        problem(409, "DISBURSEMENTS_FROZEN", "Disbursements for this property are frozen.")
    if invoice["payable_journal_id"] is None:
        problem(409, "INVOICE_NOT_APPROVED", "Settlement requires an approved payable.")
    remaining = invoice["total_cents"] - invoice["credited_cents"] - invoice["settled_cents"]
    if remaining <= 0:
        return get_invoice(session, organization_id, invoice_id)
    _consume_rent_lots(session, organization_id, invoice["property_id"], remaining)
    bank_account_id = _property_bank_account(session, organization_id, invoice["property_id"])
    _post(
        session,
        organization_id,
        "INVOICE_SETTLEMENT",
        uuid4(),
        posting_date,
        [
            _line("2040", "DEBIT", remaining, {"property_id": invoice["property_id"], "lease_id": None}, "RENT"),
            _line(
                "1030",
                "CREDIT",
                remaining,
                {"property_id": invoice["property_id"], "lease_id": None},
                "RENT",
                bank_account_id=bank_account_id,
            ),
        ],
    )
    session.execute(
        text(
            """
            UPDATE invoices
            SET settled_cents = settled_cents + :amount, status = 'SETTLED'
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"amount": remaining, "organization_id": organization_id, "id": invoice_id},
    )
    return get_invoice(session, organization_id, invoice_id)


def settle_fee(session: Session, organization_id: UUID, property_id: UUID, amount_cents: int, posting_date: date) -> dict:
    frozen = _lock_property(session, organization_id, property_id)
    if frozen:
        problem(409, "DISBURSEMENTS_FROZEN", "Disbursements for this property are frozen.")
    balance = _account_balance(session, organization_id, "2050", property_id=property_id)
    if amount_cents > balance:
        problem(409, "SETTLEMENT_EXCEEDS_PAYABLE", "The fee settlement exceeds the unpaid management payable.")
    _consume_rent_lots(session, organization_id, property_id, amount_cents)
    bank_account_id = _property_bank_account(session, organization_id, property_id)
    journal_id = _post(
        session,
        organization_id,
        "FEE_SETTLEMENT",
        uuid4(),
        posting_date,
        [
            _line("2050", "DEBIT", amount_cents, {"property_id": property_id, "lease_id": None}, "RENT"),
            _line(
                "1030",
                "CREDIT",
                amount_cents,
                {"property_id": property_id, "lease_id": None},
                "RENT",
                bank_account_id=bank_account_id,
            ),
        ],
    )
    return {"journal_id": str(journal_id), "amount_cents": amount_cents, "currency": "USD"}


def settle_declaration(session: Session, organization_id: UUID, declaration_id: UUID, posting_date: date) -> dict:
    row = session.execute(
        text(
            """
            SELECT id, property_id, owner_party_id, amount_cents, settled_cents
            FROM owner_declarations
            WHERE organization_id = :organization_id AND id = :id
            FOR UPDATE
            """
        ),
        {"organization_id": organization_id, "id": declaration_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Distribution declaration not found.")
    frozen = _lock_property(session, organization_id, row["property_id"])
    if frozen:
        problem(409, "DISBURSEMENTS_FROZEN", "Disbursements for this property are frozen.")
    remaining = row["amount_cents"] - row["settled_cents"]
    if remaining <= 0:
        return {"id": str(declaration_id), "settled_cents": row["settled_cents"], "currency": "USD"}
    _consume_rent_lots(session, organization_id, row["property_id"], remaining)
    bank_account_id = _property_bank_account(session, organization_id, row["property_id"])
    _post(
        session,
        organization_id,
        "DISTRIBUTION_SETTLEMENT",
        uuid4(),
        posting_date,
        [
            _owner_line("2060", "DEBIT", remaining, {"property_id": row["property_id"], "lease_id": None}, row["owner_party_id"]),
            _line(
                "1030",
                "CREDIT",
                remaining,
                {"property_id": row["property_id"], "lease_id": None},
                "RENT",
                bank_account_id=bank_account_id,
            ),
        ],
    )
    session.execute(
        text(
            """
            UPDATE owner_declarations
            SET settled_cents = settled_cents + :amount
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"amount": remaining, "organization_id": organization_id, "id": declaration_id},
    )
    return {"id": str(declaration_id), "settled_cents": row["amount_cents"], "currency": "USD"}


def import_bank_transactions(session: Session, organization_id: UUID, body: dict) -> dict:
    from grok_bot.domain.bank_imports import bank_import_transactions

    transactions = bank_import_transactions(body)
    created = 0
    existing = 0
    for item in transactions:
        inserted = session.execute(
            text(
                """
                INSERT INTO bank_transactions (
                  id, organization_id, bank_account_id, external_id, amount_cents, posted_on, import_hash
                ) VALUES (
                  :id, :organization_id, :bank_account_id, :external_id, :amount_cents, :posted_on, :import_hash
                )
                ON CONFLICT (organization_id, bank_account_id, external_id) DO NOTHING
                RETURNING id
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "bank_account_id": item["bank_account_id"],
                "external_id": item["external_id"],
                "amount_cents": item["amount_cents"],
                "posted_on": item["posted_on"],
                "import_hash": hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest(),
            },
        ).first()
        if inserted:
            created += 1
        else:
            # The external ID identifies an immutable bank event, not permission
            # to ignore a different amount or date. The unique insert above also
            # waits for concurrent importers before we compare their saved row.
            saved = session.execute(
                text(
                    """
                    SELECT amount_cents, posted_on FROM bank_transactions
                    WHERE organization_id = :organization_id
                      AND bank_account_id = :bank_account_id
                      AND external_id = :external_id
                    """
                ),
                {
                    "organization_id": organization_id,
                    "bank_account_id": item["bank_account_id"],
                    "external_id": item["external_id"],
                },
            ).mappings().one()
            if saved["amount_cents"] != item["amount_cents"] or str(saved["posted_on"]) != str(item["posted_on"]):
                problem(
                    409,
                    "BANK_TRANSACTION_CONFLICT",
                    "A bank transaction with this external ID has a different amount or date. Review the source before importing again.",
                )
            existing += 1
    return {"created": created, "existing": existing}


def close_period(session: Session, organization_id: UUID, start_date: date, end_date: date, reason: str) -> dict:
    period_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO period_closes (id, organization_id, period_start, period_end, status, reason)
            VALUES (:id, :organization_id, :period_start, :period_end, 'CLOSED', :reason)
            """
        ),
        {
            "id": period_id,
            "organization_id": organization_id,
            "period_start": start_date,
            "period_end": end_date,
            "reason": reason,
        },
    )
    return {"id": str(period_id), "status": "CLOSED"}


def draft_reconciliation(session: Session, organization_id: UUID, body: dict) -> dict:
    ledger_cash = _bank_ledger_cash(session, organization_id, body["bank_account_id"])
    obligations = _custodial_obligations(session, organization_id)
    timing = body.get("timing_item_cents", 0)
    difference = body["statement_closing_cents"] - ledger_cash - timing
    reconciliation_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO reconciliations (
              id, organization_id, bank_account_id, period_start, period_end,
              statement_opening_cents, statement_closing_cents, ledger_cash_cents,
              obligation_cents, timing_item_cents, difference_cents, status
            ) VALUES (
              :id, :organization_id, :bank_account_id, :period_start, :period_end,
              :statement_opening_cents, :statement_closing_cents, :ledger_cash_cents,
              :obligation_cents, :timing_item_cents, :difference_cents, 'DRAFT'
            )
            """
        ),
        {
            "id": reconciliation_id,
            "organization_id": organization_id,
            "bank_account_id": body["bank_account_id"],
            "period_start": body["period_start"],
            "period_end": body["period_end"],
            "statement_opening_cents": body["statement_opening_cents"],
            "statement_closing_cents": body["statement_closing_cents"],
            "ledger_cash_cents": ledger_cash,
            "obligation_cents": obligations,
            "timing_item_cents": timing,
            "difference_cents": difference,
        },
    )
    return get_reconciliation(session, organization_id, reconciliation_id)


def close_reconciliation(session: Session, organization_id: UUID, reconciliation_id: UUID) -> dict:
    row = get_reconciliation(session, organization_id, reconciliation_id)
    if row["difference_cents"] != 0:
        problem(409, "RECONCILIATION_DIFFERENCE", "An unexplained difference cannot be forced to balance.")
    session.execute(
        text(
            """
            UPDATE reconciliations
            SET status = 'CLOSED', evidence_hash = :evidence_hash
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {
            "organization_id": organization_id,
            "id": reconciliation_id,
            "evidence_hash": hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest(),
        },
    )
    return get_reconciliation(session, organization_id, reconciliation_id)


def property_balances(session: Session, organization_id: UUID, property_id: UUID) -> dict:
    codes = ["1010", "1020", "1030", "1040", "2010", "2020", "2030", "2040", "2050", "2060", "2070"]
    balances = []
    for code in codes:
        balances.append(
            {
                "code": code,
                "amount_cents": _account_balance(session, organization_id, code, property_id=property_id),
            }
        )
    owners = session.execute(
        text(
            """
            SELECT DISTINCT owner_party_id
            FROM journal_lines
            WHERE organization_id = :organization_id AND property_id = :property_id AND owner_party_id IS NOT NULL
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).scalars().all()
    return {
        "property_id": str(property_id),
        "accounts": balances,
        "owners": [
            {
                "owner_party_id": str(owner_id),
                "unrestricted_cents": _owner_balance(session, organization_id, property_id, owner_id, "2020"),
                "reserve_cents": _owner_balance(session, organization_id, property_id, owner_id, "2030"),
            }
            for owner_id in owners
        ],
        "currency": "USD",
    }


def get_receipt(session: Session, organization_id: UUID, receipt_id: UUID) -> dict:
    row = session.execute(
        text("SELECT * FROM receipts WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": receipt_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Receipt not found.")
    status = _derive_status(row)
    if status != row["status"] or (status != "AVAILABLE" and row["available_at"] is not None and row["available_cents"] != row["amount_cents"]):
        session.execute(
            text("UPDATE receipts SET status = :status WHERE organization_id = :organization_id AND id = :id"),
            {"status": status, "organization_id": organization_id, "id": receipt_id},
        )
    return {
        "id": str(row["id"]),
        "property_id": str(row["property_id"]),
        "amount_cents": row["amount_cents"],
        "available_cents": row["available_cents"],
        "allocated_cents": row["allocated_cents"],
        "deposited_cents": row["deposited_cents"],
        "verified_cents": row["verified_cents"],
        "returned_cents": row["returned_cents"],
        "status": status,
        "available_at": row["available_at"].isoformat() if row["available_at"] and status == "AVAILABLE" else None,
        "receipt_number": row["receipt_number"],
        "currency": "USD",
        "method": row["method"],
    }


def list_property_ledger(session: Session, organization_id: UUID, property_id: UUID, limit: int, cursor: str | None) -> dict:
    found = session.execute(
        text("SELECT id FROM properties WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": property_id},
    ).first()
    if found is None:
        problem(404, "NOT_FOUND", "Property not found.")
    balances = property_balances(session, organization_id, property_id)
    cursor_id = None if cursor is None else UUID(cursor)
    rows = session.execute(
        text(
            """
            SELECT DISTINCT e.id, e.posting_date, e.source_type, e.source_id, e.reversal_of_id, e.created_at
            FROM journal_entries AS e
            JOIN journal_lines AS l ON l.organization_id = e.organization_id AND l.journal_id = e.id
            WHERE e.organization_id = :organization_id
              AND l.property_id = :property_id
              AND e.status = 'POSTED'
              AND (CAST(:cursor_id AS uuid) IS NULL OR e.id > CAST(:cursor_id AS uuid))
            ORDER BY e.id
            LIMIT :limit
            """
        ),
        {"organization_id": organization_id, "property_id": property_id, "cursor_id": cursor_id, "limit": limit + 1},
    ).mappings().all()
    page = rows[:limit]
    return {
        "property_id": str(property_id),
        "accounts": balances["accounts"],
        "owners": balances["owners"],
        "items": [
            {
                "id": str(row["id"]),
                "posting_date": row["posting_date"].isoformat(),
                "source_type": row["source_type"],
                "source_id": str(row["source_id"]),
                "reversal_of_id": None if row["reversal_of_id"] is None else str(row["reversal_of_id"]),
            }
            for row in page
        ],
        "next_cursor": None if len(rows) <= limit or not page else str(page[-1]["id"]),
        "currency": "USD",
    }


def reverse_journal(session: Session, organization_id: UUID, journal_id: UUID, posting_date: date, reason: str) -> dict:
    if not reason.strip():
        problem(422, "VALIDATION_ERROR", "A reversal requires a reason.")
    original = session.execute(
        text(
            """
            SELECT id, status FROM journal_entries
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "id": journal_id},
    ).mappings().first()
    if original is None or original["status"] != "POSTED":
        problem(404, "NOT_FOUND", "Posted journal not found.")
    lines = session.execute(
        text(
            """
            SELECT a.code AS account_code, l.side, l.amount_cents, l.property_id, l.owner_party_id,
                   l.lease_id, l.bank_account_id, l.purpose
            FROM journal_lines AS l
            JOIN ledger_accounts AS a ON a.organization_id = l.organization_id AND a.id = l.account_id
            WHERE l.organization_id = :organization_id AND l.journal_id = :journal_id
            ORDER BY l.id
            """
        ),
        {"organization_id": organization_id, "journal_id": journal_id},
    ).mappings().all()
    if not lines:
        problem(409, "UNBALANCED_JOURNAL", "The journal has no lines to reverse.")
    swapped = []
    for line in lines:
        swapped.append(
            {
                "account_code": line["account_code"],
                "side": "CREDIT" if line["side"] == "DEBIT" else "DEBIT",
                "amount_cents": int(line["amount_cents"]),
                "property_id": "" if line["property_id"] is None else str(line["property_id"]),
                "owner_party_id": "" if line["owner_party_id"] is None else str(line["owner_party_id"]),
                "lease_id": "" if line["lease_id"] is None else str(line["lease_id"]),
                "bank_account_id": "" if line["bank_account_id"] is None else str(line["bank_account_id"]),
                "purpose": "" if line["purpose"] is None else line["purpose"],
            }
        )
    reversal_id = _post(
        session,
        organization_id,
        "JOURNAL_REVERSAL",
        journal_id,
        posting_date,
        swapped,
        reversal_of=journal_id,
    )
    return {
        "id": str(reversal_id),
        "reversal_of_id": str(journal_id),
        "reason": reason,
        "currency": "USD",
        "posted": True,
    }


def list_bank_transactions(session: Session, organization_id: UUID, limit: int, cursor: str | None) -> dict:
    cursor_id = None if cursor is None else UUID(cursor)
    rows = session.execute(
        text(
            """
            SELECT t.id, t.bank_account_id, t.external_id, t.amount_cents, t.posted_on,
                   COALESCE(SUM(m.amount_cents), 0) AS matched_cents
            FROM bank_transactions AS t
            LEFT JOIN bank_matches AS m
              ON m.organization_id = t.organization_id AND m.bank_transaction_id = t.id
            WHERE t.organization_id = :organization_id
              AND (CAST(:cursor_id AS uuid) IS NULL OR t.id > CAST(:cursor_id AS uuid))
            GROUP BY t.id
            ORDER BY t.id
            LIMIT :limit
            """
        ),
        {"organization_id": organization_id, "cursor_id": cursor_id, "limit": limit + 1},
    ).mappings().all()
    page = rows[:limit]
    return {
        "items": [
            {
                "id": str(row["id"]),
                "bank_account_id": str(row["bank_account_id"]),
                "external_id": row["external_id"],
                "amount_cents": int(row["amount_cents"]),
                "matched_cents": int(row["matched_cents"]),
                "posted_on": row["posted_on"].isoformat(),
                "currency": "USD",
            }
            for row in page
        ],
        "next_cursor": None if len(rows) <= limit or not page else str(page[-1]["id"]),
        "currency": "USD",
    }


def match_bank_deposit(session: Session, organization_id: UUID, bank_transaction_id: UUID, deposit_batch_id: UUID, amount_cents: int) -> dict:
    if amount_cents <= 0:
        problem(422, "VALIDATION_ERROR", "A match amount must be positive.")
    transaction = session.execute(
        text(
            """
            SELECT id, bank_account_id, amount_cents FROM bank_transactions
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "id": bank_transaction_id},
    ).mappings().first()
    batch = session.execute(
        text(
            """
            SELECT id, bank_account_id, total_cents FROM deposit_batches
            WHERE organization_id = :organization_id AND id = :id
            FOR UPDATE
            """
        ),
        {"organization_id": organization_id, "id": deposit_batch_id},
    ).mappings().first()
    if transaction is None or batch is None:
        problem(404, "NOT_FOUND", "Bank transaction or deposit batch not found.")
    if transaction["bank_account_id"] != batch["bank_account_id"]:
        problem(409, "BANK_MISMATCH", "The deposit batch is not on this bank account.")
    matched_txn = int(
        session.execute(
            text(
                """
                SELECT COALESCE(SUM(amount_cents), 0) FROM bank_matches
                WHERE organization_id = :organization_id AND bank_transaction_id = :id
                """
            ),
            {"organization_id": organization_id, "id": bank_transaction_id},
        ).scalar()
    )
    matched_batch = int(
        session.execute(
            text(
                """
                SELECT COALESCE(SUM(amount_cents), 0) FROM bank_matches
                WHERE organization_id = :organization_id AND deposit_batch_id = :id
                """
            ),
            {"organization_id": organization_id, "id": deposit_batch_id},
        ).scalar()
    )
    if matched_txn + amount_cents > abs(int(transaction["amount_cents"])):
        problem(409, "BANK_MISMATCH", "The match exceeds the bank transaction.")
    if matched_batch + amount_cents > int(batch["total_cents"]):
        problem(409, "BANK_MISMATCH", "The match exceeds the deposit batch.")
    match_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO bank_matches (
              id, organization_id, bank_transaction_id, deposit_batch_id, amount_cents
            ) VALUES (
              :id, :organization_id, :bank_transaction_id, :deposit_batch_id, :amount_cents
            )
            """
        ),
        {
            "id": match_id,
            "organization_id": organization_id,
            "bank_transaction_id": bank_transaction_id,
            "deposit_batch_id": deposit_batch_id,
            "amount_cents": amount_cents,
        },
    )
    return {
        "id": str(match_id),
        "bank_transaction_id": str(bank_transaction_id),
        "deposit_batch_id": str(deposit_batch_id),
        "amount_cents": amount_cents,
        "currency": "USD",
        "posted_journal": False,
    }


def return_unallocated_receipt(session: Session, organization_id: UUID, receipt_id: UUID, amount_cents: int, posting_date: date) -> dict:
    row = _lock_receipt(session, organization_id, receipt_id)
    if amount_cents <= 0 or row["returned_cents"] + amount_cents > row["amount_cents"]:
        problem(422, "VALIDATION_ERROR", "The return amount is outside the receipt.")
    if row["allocated_cents"] > 0:
        problem(
            409,
            "CONFIGURATION_REQUIRED",
            "PRD §4.6 says a return after allocation and before payout reverses source allocations and fee accruals according to the agreement. The agreement does not specify those legs, so no reversal is posted.",
        )
    purpose = "SECURITY_DEPOSIT" if row["method"] in DEPOSIT_METHODS else "RENT"
    debit_account = "2070" if purpose == "SECURITY_DEPOSIT" else "2010"
    source = {"property_id": row["property_id"], "lease_id": row["lease_id"]}
    journal_id = _post(
        session,
        organization_id,
        "RECEIPT_RETURN",
        uuid4(),
        posting_date,
        [
            _line(debit_account, "DEBIT", amount_cents, source, purpose),
            _line("1010", "CREDIT", amount_cents, source, purpose),
        ],
    )
    session.execute(
        text(
            """
            UPDATE receipts
            SET returned_cents = returned_cents + :amount
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"amount": amount_cents, "organization_id": organization_id, "id": receipt_id},
    )
    body = get_receipt(session, organization_id, receipt_id)
    body["return_journal_id"] = str(journal_id)
    return body


def credit_invoice(session: Session, organization_id: UUID, invoice_id: UUID, amount_cents: int, posting_date: date, reason: str) -> dict:
    if amount_cents <= 0 or not reason.strip():
        problem(422, "VALIDATION_ERROR", "A credit note needs a positive amount and a reason.")
    invoice = _lock_invoice(session, organization_id, invoice_id)
    if invoice["payable_journal_id"] is None:
        problem(409, "NOT_APPROVED", "A credit note requires the original payable journal.")
    remaining = int(invoice["total_cents"]) - int(invoice["credited_cents"]) - int(invoice["settled_cents"])
    if amount_cents > remaining:
        problem(409, "INSUFFICIENT_FUNDS", "The credit exceeds the unsettled invoice remainder.")
    owner_lines = session.execute(
        text(
            """
            SELECT l.owner_party_id, l.amount_cents
            FROM journal_lines AS l
            JOIN ledger_accounts AS a ON a.organization_id = l.organization_id AND a.id = l.account_id
            WHERE l.organization_id = :organization_id AND l.journal_id = :journal_id
              AND a.code = '2020' AND l.side = 'DEBIT' AND l.owner_party_id IS NOT NULL
            """
        ),
        {"organization_id": organization_id, "journal_id": invoice["payable_journal_id"]},
    ).mappings().all()
    weights = [(row["owner_party_id"], int(row["amount_cents"])) for row in owner_lines]
    total_weight = sum(weight for _, weight in weights)
    if total_weight <= 0:
        problem(409, "CONFIGURATION_REQUIRED", "The payable journal has no owner lines to reverse.")
    shares = {owner_id: (amount_cents * weight) // total_weight for owner_id, weight in weights}
    leftover = amount_cents - sum(shares.values())
    ranked = sorted(weights, key=lambda item: (-((amount_cents * item[1]) % total_weight), str(item[0])))
    for index in range(leftover):
        shares[ranked[index][0]] += 1
    source = {"property_id": invoice["property_id"], "lease_id": None}
    lines = [_line("2040", "DEBIT", amount_cents, source, "RENT")]
    for owner_id, share in shares.items():
        if share:
            lines.append(_owner_line("2020", "CREDIT", share, source, owner_id))
    note_id = uuid4()
    journal_id = _post(session, organization_id, "CREDIT_NOTE", note_id, posting_date, lines)
    session.execute(
        text(
            """
            INSERT INTO credit_notes (id, organization_id, invoice_id, amount_cents, journal_id, reason)
            VALUES (:id, :organization_id, :invoice_id, :amount_cents, :journal_id, :reason)
            """
        ),
        {
            "id": note_id,
            "organization_id": organization_id,
            "invoice_id": invoice_id,
            "amount_cents": amount_cents,
            "journal_id": journal_id,
            "reason": reason,
        },
    )
    session.execute(
        text(
            """
            UPDATE invoices
            SET credited_cents = credited_cents + :amount, version = version + 1
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"amount": amount_cents, "organization_id": organization_id, "id": invoice_id},
    )
    body = get_invoice(session, organization_id, invoice_id)
    body["credit_note_id"] = str(note_id)
    body["journal_id"] = str(journal_id)
    body["original_payable_journal_id"] = str(invoice["payable_journal_id"])
    return body


def get_invoice(session: Session, organization_id: UUID, invoice_id: UUID) -> dict:
    row = session.execute(
        text(
            """
            SELECT id, status, total_cents, tax_cents, payable_journal_id, settled_cents, credited_cents, property_id
            FROM invoices WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "id": invoice_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Invoice not found.")
    return {
        "id": str(row["id"]),
        "property_id": str(row["property_id"]),
        "status": row["status"],
        "total_cents": row["total_cents"],
        "tax_cents": row["tax_cents"],
        "settled_cents": row["settled_cents"],
        "credited_cents": row["credited_cents"],
        "payable_journal_id": None if row["payable_journal_id"] is None else str(row["payable_journal_id"]),
        "currency": "USD",
    }


def get_reconciliation(session: Session, organization_id: UUID, reconciliation_id: UUID) -> dict:
    row = session.execute(
        text("SELECT * FROM reconciliations WHERE organization_id = :organization_id AND id = :id"),
        {"organization_id": organization_id, "id": reconciliation_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Reconciliation not found.")
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "statement_closing_cents": row["statement_closing_cents"],
        "ledger_cash_cents": row["ledger_cash_cents"],
        "obligation_cents": row["obligation_cents"],
        "difference_cents": row["difference_cents"],
        "currency": "USD",
    }


def _post(
    session: Session,
    organization_id: UUID,
    source_type: str,
    source_id: UUID,
    posting_date: date,
    lines: list[dict],
    reversal_of: UUID | None = None,
) -> UUID:
    encoded = json.dumps(lines, sort_keys=True, separators=(",", ":"), default=str)
    journal_id = session.execute(
        text(
            """
            SELECT app_post_journal(
              :organization_id, :source_type, :source_id, :posting_date,
              CAST(:lines AS jsonb), :lines_hash, :reversal_of
            )
            """
        ),
        {
            "organization_id": organization_id,
            "source_type": source_type,
            "source_id": source_id,
            "posting_date": posting_date,
            "lines": encoded,
            "lines_hash": hashlib.sha256(encoded.encode()).hexdigest(),
            "reversal_of": reversal_of,
        },
    ).scalar()
    return journal_id


def _line(account: str, side: str, amount: int, source: dict, purpose: str, bank_account_id: UUID | None = None) -> dict:
    return {
        "account_code": account,
        "side": side,
        "amount_cents": amount,
        "property_id": str(source["property_id"]),
        "owner_party_id": "",
        "lease_id": "" if source.get("lease_id") is None else str(source["lease_id"]),
        "bank_account_id": "" if bank_account_id is None else str(bank_account_id),
        "purpose": purpose,
    }


def _owner_line(account: str, side: str, amount: int, source: dict, owner_id: UUID) -> dict:
    line = _line(account, side, amount, source, "RENT" if account != "2030" else "RESERVE")
    line["owner_party_id"] = str(owner_id)
    return line


def _purpose(method: str) -> str:
    return "SECURITY_DEPOSIT" if method in DEPOSIT_METHODS else "RENT"


def _derive_status(row) -> str:
    amount = row["amount_cents"]
    if row["returned_cents"] == amount:
        return "RETURNED"
    if row["allocated_cents"] == amount:
        return "ALLOCATED"
    if row["available_cents"] == amount and row["allocated_cents"] < amount:
        return "AVAILABLE"
    if row["verified_cents"] > 0 and row["available_cents"] < amount:
        return "BANK_VERIFIED"
    if row["deposited_cents"] == amount and row["verified_cents"] == 0:
        return "DEPOSITED"
    return "RECORDED"


def _lock_property(session: Session, organization_id: UUID, property_id: UUID) -> bool:
    row = session.execute(
        text(
            """
            SELECT disbursements_frozen FROM properties
            WHERE organization_id = :organization_id AND id = :id
            FOR UPDATE
            """
        ),
        {"organization_id": organization_id, "id": property_id},
    ).first()
    if row is None:
        problem(404, "NOT_FOUND", "Property not found.")
    return bool(row.disbursements_frozen)


def _lock_receipt(session: Session, organization_id: UUID, receipt_id: UUID) -> dict:
    row = session.execute(
        text(
            """
            SELECT * FROM receipts
            WHERE organization_id = :organization_id AND id = :id
            FOR UPDATE
            """
        ),
        {"organization_id": organization_id, "id": receipt_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Receipt not found.")
    return row


def _lock_invoice(session: Session, organization_id: UUID, invoice_id: UUID) -> dict:
    row = session.execute(
        text(
            """
            SELECT * FROM invoices
            WHERE organization_id = :organization_id AND id = :id
            FOR UPDATE
            """
        ),
        {"organization_id": organization_id, "id": invoice_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Invoice not found.")
    return row


def _update_receipt_counters(session: Session, organization_id: UUID, receipt_id: UUID, **changes) -> None:
    current = _lock_receipt(session, organization_id, receipt_id)
    values = {
        "deposited_cents": current["deposited_cents"],
        "verified_cents": current["verified_cents"],
        "available_cents": current["available_cents"],
        "allocated_cents": current["allocated_cents"],
        "returned_cents": current["returned_cents"],
        "bank_account_id": current["bank_account_id"],
        "available_at": current["available_at"],
    }
    values.update(changes)
    if changes.get("keep_available_at"):
        values["available_at"] = None
    values.pop("keep_available_at", None)
    status_row = {
        "amount_cents": current["amount_cents"],
        "returned_cents": values["returned_cents"],
        "allocated_cents": values["allocated_cents"],
        "available_cents": values["available_cents"],
        "verified_cents": values["verified_cents"],
        "deposited_cents": values["deposited_cents"],
    }
    session.execute(
        text(
            """
            UPDATE receipts
            SET deposited_cents = :deposited_cents,
                verified_cents = :verified_cents,
                available_cents = :available_cents,
                allocated_cents = :allocated_cents,
                returned_cents = :returned_cents,
                bank_account_id = :bank_account_id,
                available_at = :available_at,
                status = :status,
                version = version + 1
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "id": receipt_id, "status": _derive_status(status_row), **values},
    )


def _weights_on(session: Session, organization_id: UUID, property_id: UUID, posting_date: date) -> list[tuple[UUID, int]]:
    rows = session.execute(
        text(
            """
            SELECT s.owner_party_id, s.weight
            FROM ownership_shares AS s
            JOIN ownership_periods AS p
              ON p.id = s.period_id AND p.organization_id = s.organization_id
            WHERE p.organization_id = :organization_id
              AND p.property_id = :property_id
              AND p.start_date <= :posting_date
              AND p.end_date > :posting_date
            ORDER BY s.owner_party_id
            """
        ),
        {"organization_id": organization_id, "property_id": property_id, "posting_date": posting_date},
    ).all()
    if not rows:
        problem(409, "CONFIGURATION_REQUIRED", "An effective ownership period is required.")
    return [(row.owner_party_id, row.weight) for row in rows]


def _period_id_on(session: Session, organization_id: UUID, property_id: UUID, posting_date: date) -> UUID:
    period_id = session.execute(
        text(
            """
            SELECT id FROM ownership_periods
            WHERE organization_id = :organization_id AND property_id = :property_id
              AND start_date <= :posting_date AND end_date > :posting_date
            """
        ),
        {"organization_id": organization_id, "property_id": property_id, "posting_date": posting_date},
    ).scalar()
    if period_id is None:
        problem(409, "CONFIGURATION_REQUIRED", "An effective ownership period is required.")
    return period_id


def _fee_rule_on(session: Session, organization_id: UUID, property_id: UUID, posting_date: date) -> dict:
    row = session.execute(
        text(
            """
            SELECT f.rate_numerator, f.rate_denominator, f.fixed_cents, f.cap_cents, f.minimum_cents
            FROM fee_rules AS f
            JOIN agreements AS a ON a.id = f.agreement_id AND a.organization_id = f.organization_id
            WHERE a.organization_id = :organization_id AND a.property_id = :property_id
              AND a.start_date <= :posting_date AND a.end_date > :posting_date
            """
        ),
        {"organization_id": organization_id, "property_id": property_id, "posting_date": posting_date},
    ).mappings().first()
    if row is None:
        problem(409, "CONFIGURATION_REQUIRED", "A fee agreement is required before rent can be allocated.")
    return row


def _owner_balance(session: Session, organization_id: UUID, property_id: UUID, owner_id: UUID, code: str) -> int:
    value = session.execute(
        text(
            """
            SELECT coalesce(sum(CASE WHEN l.side = 'CREDIT' THEN l.amount_cents ELSE -l.amount_cents END), 0)
            FROM journal_lines AS l
            JOIN ledger_accounts AS a ON a.id = l.account_id AND a.organization_id = l.organization_id
            WHERE l.organization_id = :organization_id
              AND l.property_id = :property_id
              AND l.owner_party_id = :owner_id
              AND a.code = :code
            """
        ),
        {
            "organization_id": organization_id,
            "property_id": property_id,
            "owner_id": owner_id,
            "code": code,
        },
    ).scalar()
    return int(value)


def _account_balance(session: Session, organization_id: UUID, code: str, property_id: UUID | None = None) -> int:
    normal = session.execute(
        text("SELECT normal_balance FROM ledger_accounts WHERE organization_id = :organization_id AND code = :code"),
        {"organization_id": organization_id, "code": code},
    ).scalar()
    if normal is None:
        session.execute(text("SELECT app_ensure_proposed_chart(:organization_id)"), {"organization_id": organization_id})
        normal = "CREDIT" if code.startswith("2") else "DEBIT"
    signed = "CASE WHEN l.side = 'DEBIT' THEN l.amount_cents ELSE -l.amount_cents END"
    if normal == "CREDIT":
        signed = "CASE WHEN l.side = 'CREDIT' THEN l.amount_cents ELSE -l.amount_cents END"
    value = session.execute(
        text(
            f"""
            SELECT coalesce(sum({signed}), 0)
            FROM journal_lines AS l
            JOIN ledger_accounts AS a ON a.id = l.account_id AND a.organization_id = l.organization_id
            WHERE l.organization_id = :organization_id AND a.code = :code
              AND (:property_id IS NULL OR l.property_id = :property_id)
            """
        ),
        {"organization_id": organization_id, "code": code, "property_id": property_id},
    ).scalar()
    return int(value)


def _bank_ledger_cash(session: Session, organization_id: UUID, bank_account_id: UUID) -> int:
    value = session.execute(
        text(
            """
            SELECT coalesce(sum(CASE WHEN l.side = 'DEBIT' THEN l.amount_cents ELSE -l.amount_cents END), 0)
            FROM journal_lines AS l
            JOIN ledger_accounts AS a ON a.id = l.account_id AND a.organization_id = l.organization_id
            WHERE l.organization_id = :organization_id
              AND l.bank_account_id = :bank_account_id
              AND a.code IN ('1020', '1030')
            """
        ),
        {"organization_id": organization_id, "bank_account_id": bank_account_id},
    ).scalar()
    return int(value)


def _custodial_obligations(session: Session, organization_id: UUID) -> int:
    liabilities = sum(_account_balance(session, organization_id, code) for code in ("2010", "2020", "2030", "2040", "2050", "2060", "2070"))
    receivables = _account_balance(session, organization_id, "1040")
    return liabilities - receivables


def _consume_rent_lots(session: Session, organization_id: UUID, property_id: UUID, amount: int) -> None:
    rows = session.execute(
        text(
            """
            SELECT id, amount_cents - consumed_cents AS remaining
            FROM funding_lots
            WHERE organization_id = :organization_id
              AND property_id = :property_id
              AND purpose = 'RENT'
              AND consumed_cents < amount_cents
            ORDER BY id
            FOR UPDATE
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).all()
    if sum(row.remaining for row in rows) < amount:
        problem(
            409,
            "INSUFFICIENT_FUNDS",
            "This property does not have enough eligible rent cash for this payment.",
        )
    left = amount
    for row in rows:
        take = min(left, row.remaining)
        if take == 0:
            continue
        session.execute(
            text(
                """
                UPDATE funding_lots
                SET consumed_cents = consumed_cents + :take
                WHERE id = :id AND consumed_cents + :take <= amount_cents
                """
            ),
            {"take": take, "id": row.id},
        )
        left -= take
    if left != 0:
        problem(409, "INSUFFICIENT_FUNDS", "This property does not have enough eligible rent cash for this payment.")


def _property_bank_account(session: Session, organization_id: UUID, property_id: UUID) -> UUID:
    bank_account_id = session.execute(
        text(
            """
            SELECT bank_account_id FROM funding_lots
            WHERE organization_id = :organization_id AND property_id = :property_id
            ORDER BY created_at
            LIMIT 1
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).scalar()
    if bank_account_id is None:
        problem(409, "CONFIGURATION_REQUIRED", "A bank account funding lot is required.")
    return bank_account_id


def _journal_count(session: Session, organization_id: UUID) -> int:
    return int(
        session.execute(
            text("SELECT count(*) FROM journal_entries WHERE organization_id = :organization_id"),
            {"organization_id": organization_id},
        ).scalar()
    )
