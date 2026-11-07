import hashlib
import json
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import text

from grok_bot.crypto import encrypt_text
from grok_bot.domain.money import round_half_up_ratio
from grok_bot.domain.records import write_audit
from grok_bot.errors import problem

DISCLOSURE = (
    "This is preliminary intake. A person handles exceptions and final housing decisions. "
    "Formal screening is not part of this step."
)
ALLOWED_FIELDS = {
    "household_income_monthly_cents",
    "lease_months",
    "occupant_count",
    "pets_declared",
}
ALLOWED_OPERATORS = {"gte_rent_multiple", "in", "gte", "lte"}
PROHIBITED_FIELDS = {
    "race",
    "color",
    "religion",
    "national_origin",
    "nationality",
    "sex",
    "gender",
    "familial_status",
    "family_status",
    "disability",
    "handicap",
    "date_of_birth",
    "dob",
    "ssn",
    "credit_score",
    "language",
    "name",
    "zip",
    "postal_code",
    "adults",
    "children",
    "child_count",
}


def monthly_cents(amount: int, period: str) -> int:
    if period == "monthly":
        return amount
    if period == "annual":
        return round_half_up_ratio(amount, 1, 12)
    if period == "weekly":
        return round_half_up_ratio(amount * 52, 1, 12)
    if period == "biweekly":
        return round_half_up_ratio(amount * 26, 1, 12)
    problem(422, "VALIDATION_ERROR", "Income period must be weekly, biweekly, monthly, or annual.")


def ensure_prospect(session, organization_id, user_id, listing_id=None) -> dict:
    existing = session.execute(
        text("SELECT id FROM prospects WHERE organization_id = :organization_id AND user_id = :user_id"),
        {"organization_id": organization_id, "user_id": user_id},
    ).scalar()
    if existing:
        if listing_id is not None:
            listing = session.execute(
                text("SELECT property_id, unit_id FROM listings WHERE organization_id = :organization_id AND id = :id"),
                {"organization_id": organization_id, "id": listing_id},
            ).mappings().first()
            if listing is None:
                problem(404, "NOT_FOUND", "Listing not found.")
            session.execute(
                text(
                    """
                    UPDATE prospects
                    SET listing_id = :listing_id, property_id = :property_id, unit_id = :unit_id
                    WHERE organization_id = :organization_id AND id = :id
                    """
                ),
                {
                    "listing_id": listing_id,
                    "property_id": listing["property_id"],
                    "unit_id": listing["unit_id"],
                    "organization_id": organization_id,
                    "id": existing,
                },
            )
        return _prospect(session, organization_id, existing)
    listing = None
    if listing_id is not None:
        listing = session.execute(
            text("SELECT property_id, unit_id FROM listings WHERE organization_id = :organization_id AND id = :id"),
            {"organization_id": organization_id, "id": listing_id},
        ).mappings().first()
        if listing is None:
            problem(404, "NOT_FOUND", "Listing not found.")
    prospect_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO prospects (
              id, organization_id, user_id, listing_id, property_id, unit_id, state, unverified, disclosure_shown
            ) VALUES (
              :id, :organization_id, :user_id, :listing_id, :property_id, :unit_id, 'COLLECTING', true, true
            )
            """
        ),
        {
            "id": prospect_id,
            "organization_id": organization_id,
            "user_id": user_id,
            "listing_id": listing_id,
            "property_id": None if listing is None else listing["property_id"],
            "unit_id": None if listing is None else listing["unit_id"],
        },
    )
    session.execute(
        text(
            """
            INSERT INTO prospect_intakes (id, organization_id, prospect_id)
            VALUES (:id, :organization_id, :prospect_id)
            """
        ),
        {"id": uuid4(), "organization_id": organization_id, "prospect_id": prospect_id},
    )
    return _prospect(session, organization_id, prospect_id)


def receive_inquiry(session, organization_id, body: dict) -> dict:
    existing = session.execute(
        text(
            """
            SELECT id, prospect_id, ambiguous, clarification
            FROM inquiries
            WHERE organization_id = :organization_id AND provider = :provider
              AND provider_message_id = :provider_message_id
            """
        ),
        {"organization_id": organization_id, **{key: body[key] for key in ("provider", "provider_message_id")}},
    ).mappings().first()
    if existing:
        return {
            "id": str(existing["id"]),
            "prospect_id": None if existing["prospect_id"] is None else str(existing["prospect_id"]),
            "ambiguous": existing["ambiguous"],
            "clarification": existing["clarification"],
            "duplicate": True,
        }
    listing = _resolve_listing(session, organization_id, body.get("external_source") or body["provider"], body.get("external_listing_id"), body.get("address_hint"))
    prospect_id = None
    if listing["match"] is not None:
        prospect_id = uuid4()
        session.execute(
            text(
                """
                INSERT INTO prospects (
                  id, organization_id, listing_id, property_id, unit_id, state, unverified, disclosure_shown
                ) VALUES (
                  :id, :organization_id, :listing_id, :property_id, :unit_id, 'COLLECTING', true, true
                )
                """
            ),
            {
                "id": prospect_id,
                "organization_id": organization_id,
                "listing_id": listing["match"]["id"],
                "property_id": listing["match"]["property_id"],
                "unit_id": listing["match"]["unit_id"],
            },
        )
        session.execute(
            text("INSERT INTO prospect_intakes (id, organization_id, prospect_id) VALUES (:id, :organization_id, :prospect_id)"),
            {"id": uuid4(), "organization_id": organization_id, "prospect_id": prospect_id},
        )
    inquiry_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO inquiries (
              id, organization_id, provider, provider_message_id, external_listing_id,
              address_hint, listing_id, prospect_id, ambiguous, clarification
            ) VALUES (
              :id, :organization_id, :provider, :provider_message_id, :external_listing_id,
              :address_hint, :listing_id, :prospect_id, :ambiguous, :clarification
            )
            """
        ),
        {
            "id": inquiry_id,
            "organization_id": organization_id,
            "provider": body["provider"],
            "provider_message_id": body["provider_message_id"],
            "external_listing_id": body.get("external_listing_id"),
            "address_hint": body.get("address_hint"),
            "listing_id": None if listing["match"] is None else listing["match"]["id"],
            "prospect_id": prospect_id,
            "ambiguous": listing["ambiguous"],
            "clarification": listing["clarification"],
        },
    )
    return {
        "id": str(inquiry_id),
        "prospect_id": None if prospect_id is None else str(prospect_id),
        "ambiguous": listing["ambiguous"],
        "clarification": listing["clarification"],
        "duplicate": False,
        "disclosure": DISCLOSURE,
    }


def update_intake(session, organization_id, prospect_id, body: dict, actor_id) -> dict:
    _lock_prospect(session, organization_id, prospect_id)
    current = _intake(session, organization_id, prospect_id)
    merged = dict(current)
    for key in (
        "move_in_date",
        "lease_months",
        "income_original_cents",
        "income_period",
        "occupant_count",
        "pets_declared",
        "assistance_animal_requested",
        "rental_history",
        "income_source",
    ):
        if key in body and body[key] is not None:
            merged[key] = body[key]
    if "income_original_cents" in body or "income_period" in body:
        if merged["income_original_cents"] is not None and merged["income_period"]:
            merged["income_monthly_cents"] = monthly_cents(int(merged["income_original_cents"]), merged["income_period"])
        else:
            merged["income_monthly_cents"] = None
    session.execute(
        text(
            """
            UPDATE prospect_intakes
            SET move_in_date = CAST(:move_in_date AS date),
                lease_months = :lease_months,
                income_original_cents = :income_original_cents,
                income_period = :income_period,
                income_monthly_cents = :income_monthly_cents,
                occupant_count = :occupant_count,
                pets_declared = :pets_declared,
                assistance_animal_requested = :assistance_animal_requested,
                rental_history = :rental_history,
                income_source = :income_source,
                income_unverified = true,
                version = version + 1
            WHERE organization_id = :organization_id AND prospect_id = :prospect_id
            """
        ),
        {"organization_id": organization_id, "prospect_id": prospect_id, **{key: merged[key] for key in (
            "move_in_date", "lease_months", "income_original_cents", "income_period", "income_monthly_cents",
            "occupant_count", "pets_declared", "assistance_animal_requested", "rental_history", "income_source",
        )}},
    )
    session.execute(
        text(
            """
            UPDATE prospects
            SET intake_version = intake_version + 1, state = 'COLLECTING'
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "id": prospect_id},
    )
    for channel, allowed in (body.get("consents") or {}).items():
        if channel not in {"email", "sms"}:
            problem(422, "VALIDATION_ERROR", "Consent channels are email and sms.")
        session.execute(
            text(
                """
                INSERT INTO prospect_consents (id, organization_id, prospect_id, channel, allowed)
                VALUES (:id, :organization_id, :prospect_id, :channel, :allowed)
                ON CONFLICT (organization_id, prospect_id, channel)
                DO UPDATE SET allowed = EXCLUDED.allowed
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "prospect_id": prospect_id,
                "channel": channel,
                "allowed": bool(allowed),
            },
        )
    del actor_id
    stored = _intake(session, organization_id, prospect_id)
    stored["questions"] = questions_for(stored)
    stored["disclosure"] = DISCLOSURE
    stored["income_treated_as_zero"] = False
    return stored


def questions_for(intake: dict) -> list[str]:
    found = []
    if intake.get("income_original_cents") is not None and intake.get("income_period") is None:
        found.append("Is that income weekly, biweekly, monthly, or annual? A missing period is not treated as zero.")
    if intake.get("move_in_date") is None:
        found.append("When would you like to move in?")
    if intake.get("lease_months") is None:
        found.append("How many months would you like the lease to run?")
    if intake.get("income_original_cents") is None:
        found.append("What is the approximate total household income, and is that weekly, biweekly, monthly, or annual? Lawful nonemployment income may be included.")
    if intake.get("occupant_count") is None:
        found.append("How many people would occupy the home?")
    if intake.get("pets_declared") is None:
        found.append("Will you have pets? Assistance-animal requests can be reviewed privately by the manager.")
    if not intake.get("rental_history"):
        found.append("What objective rental history should the manager have: prior landlord contact, dates, or none to report?")
    return found[:2]


def publish_policy(session, organization_id, property_id, body: dict, reviewer_id) -> dict:
    rules = body["rules"]
    for rule in rules:
        field = str(rule.get("field", "")).lower()
        if field in PROHIBITED_FIELDS or field not in ALLOWED_FIELDS:
            problem(422, "PROHIBITED_POLICY_FIELD", "That screening field is not on the allowlist.")
        if rule.get("operator") not in ALLOWED_OPERATORS:
            problem(422, "PROHIBITED_POLICY_FIELD", "That screening operator is not on the allowlist.")
        if rule.get("failure_action") != "HUMAN_REVIEW":
            problem(422, "PROHIBITED_POLICY_FIELD", "A screening rule cannot deny housing.")
    if body.get("automatic_final_denial") is True:
        problem(422, "PROHIBITED_POLICY_FIELD", "Automatic final denial is not available.")
    if body.get("fixture") and not str(body.get("legal_review_reference", "")).startswith("fixture:"):
        problem(422, "VALIDATION_ERROR", "A fixture policy must use a fixture: review reference.")
    version = session.execute(
        text(
            """
            SELECT COALESCE(MAX(version), 0) + 1
            FROM screening_policies
            WHERE organization_id = :organization_id AND property_id = :property_id
            """
        ),
        {"organization_id": organization_id, "property_id": property_id},
    ).scalar()
    policy_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO screening_policies (
              id, organization_id, property_id, version, status, fixture, legal_review_reference,
              review_reason, reviewed_by, effective_at, rules, missing_action, accommodation_action,
              automatic_final_denial
            ) VALUES (
              :id, :organization_id, :property_id, :version, 'REVIEWED_ACTIVE', :fixture, :legal_review_reference,
              :review_reason, :reviewed_by, :effective_at, CAST(:rules AS jsonb), :missing_action, 'HUMAN_REVIEW',
              false
            )
            """
        ),
        {
            "id": policy_id,
            "organization_id": organization_id,
            "property_id": property_id,
            "version": version,
            "fixture": bool(body.get("fixture")),
            "legal_review_reference": body["legal_review_reference"],
            "review_reason": body["review_reason"],
            "reviewed_by": reviewer_id,
            "effective_at": body["effective_at"],
            "rules": json.dumps(rules),
            "missing_action": body.get("missing_action", "NEEDS_INFORMATION"),
        },
    )
    return {"id": str(policy_id), "version": version, "fixture": bool(body.get("fixture")), "automatic_final_denial": False}


def evaluate(session, organization_id, prospect_id, actor_id, key: bytes | None, note: str | None) -> dict:
    prospect = _lock_prospect(session, organization_id, prospect_id)
    intake = _intake(session, organization_id, prospect_id)
    policy = None
    if prospect["property_id"] is not None:
        policy = session.execute(
            text(
                """
                SELECT id, version, rules, missing_action, fixture, property_id
                FROM screening_policies
                WHERE organization_id = :organization_id AND property_id = :property_id
                  AND status = 'REVIEWED_ACTIVE' AND effective_at <= clock_timestamp()
                ORDER BY version DESC
                LIMIT 1
                """
            ),
            {"organization_id": organization_id, "property_id": prospect["property_id"]},
        ).mappings().first()
    hashed = _input_hash(intake)
    missing = _missing(intake)
    if policy is None:
        result = "HUMAN_REVIEW"
        rule_results = []
        configuration = "CONFIGURATION_REQUIRED"
        state = "HUMAN_REVIEW"
    else:
        configuration = None
        rule_results, missing_rules, review = _apply_rules(session, organization_id, policy, intake)
        missing = sorted(set(missing + missing_rules))
        if missing and not review:
            result = policy["missing_action"]
        elif review or (intake["assistance_animal_requested"] and not missing):
            result = "HUMAN_REVIEW"
        else:
            result = "PRELIMINARILY_QUALIFIED"
        state = result
    if intake["assistance_animal_requested"]:
        result = "HUMAN_REVIEW"
        state = "HUMAN_REVIEW"
        _open_accommodation(session, organization_id, prospect_id, prospect["user_id"], key, note or "Assistance-animal review requested.")
    evaluation_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO policy_evaluations (
              id, organization_id, prospect_id, intake_version, policy_id, policy_version,
              input_hash, result, missing_fields, rule_results, formal_screening_permitted, configuration_code
            ) VALUES (
              :id, :organization_id, :prospect_id, :intake_version, :policy_id, :policy_version,
              :input_hash, :result, CAST(:missing_fields AS jsonb), CAST(:rule_results AS jsonb), false, :configuration_code
            )
            """
        ),
        {
            "id": evaluation_id,
            "organization_id": organization_id,
            "prospect_id": prospect_id,
            "intake_version": prospect["intake_version"],
            "policy_id": None if policy is None else policy["id"],
            "policy_version": None if policy is None else policy["version"],
            "input_hash": hashed,
            "result": result,
            "missing_fields": json.dumps(missing),
            "rule_results": json.dumps(rule_results),
            "configuration_code": configuration,
        },
    )
    session.execute(
        text("UPDATE prospects SET state = :state WHERE organization_id = :organization_id AND id = :id"),
        {"state": state, "organization_id": organization_id, "id": prospect_id},
    )
    if result == "HUMAN_REVIEW":
        session.execute(
            text(
                """
                INSERT INTO human_reviews (
                  id, organization_id, prospect_id, evaluation_id, property_id, reason, rule_ids, missing_fields, state
                ) VALUES (
                  :id, :organization_id, :prospect_id, :evaluation_id, :property_id, :reason,
                  CAST(:rule_ids AS jsonb), CAST(:missing_fields AS jsonb), 'OPEN'
                )
                """
            ),
            {
                "id": uuid4(),
                "organization_id": organization_id,
                "prospect_id": prospect_id,
                "evaluation_id": evaluation_id,
                "property_id": prospect["property_id"],
                "reason": configuration or "Reviewed policy requested a person.",
                "rule_ids": json.dumps([item["rule_id"] for item in rule_results if item["result"] == "HUMAN_REVIEW"]),
                "missing_fields": json.dumps(missing),
            },
        )
    del actor_id
    return {
        "prospect_id": str(prospect_id),
        "intake_version": prospect["intake_version"],
        "policy_version": None if policy is None else policy["version"],
        "policy_fixture": None if policy is None else policy["fixture"],
        "result": result,
        "missing_fields": missing,
        "rule_results": rule_results,
        "formal_screening_permitted": False,
        "configuration_code": configuration,
        "input_hash": hashed,
        "final_denial": False,
        "disclosure": DISCLOSURE,
    }


def list_reviews(session, organization_id) -> dict:
    rows = session.execute(
        text(
            """
            SELECT r.id, r.prospect_id, r.property_id, r.reason, r.rule_ids, r.missing_fields,
                   r.state, r.opened_at, p.state AS prospect_state
            FROM human_reviews AS r
            JOIN prospects AS p ON p.organization_id = r.organization_id AND p.id = r.prospect_id
            WHERE r.organization_id = :organization_id AND r.state = 'OPEN'
            ORDER BY r.opened_at
            """
        ),
        {"organization_id": organization_id},
    ).mappings().all()
    return {
        "items": [
            {
                "id": str(row["id"]),
                "prospect_id": str(row["prospect_id"]),
                "property_id": None if row["property_id"] is None else str(row["property_id"]),
                "reason": row["reason"],
                "rule_ids": row["rule_ids"],
                "missing_fields": row["missing_fields"],
                "state": row["state"],
                "prospect_state": row["prospect_state"],
                "opened_at": row["opened_at"].isoformat(),
                "final_housing_decision": False,
            }
            for row in rows
        ]
    }


def resolve_review(session, organization_id, review_id, body: dict, reviewer_id) -> dict:
    row = session.execute(
        text("SELECT * FROM human_reviews WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": review_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Review not found.")
    resolution = body["resolution"]
    if resolution not in {"REQUEST_INFORMATION", "CORRECT_INTAKE", "EXCEPTION", "ACCOMMODATION"}:
        problem(422, "VALIDATION_ERROR", "Unknown review resolution.")
    if resolution == "EXCEPTION" and not (body.get("reason") or "").strip():
        problem(422, "VALIDATION_ERROR", "An exception needs a reason.")
    session.execute(
        text(
            """
            UPDATE human_reviews
            SET state = 'RESOLVED', resolution = :resolution, exception_granted = :exception_granted,
                exception_reason = :reason, reviewer_id = :reviewer_id, resolved_at = clock_timestamp()
            WHERE organization_id = :organization_id AND id = :id
            """
        ),
        {
            "resolution": resolution,
            "exception_granted": resolution == "EXCEPTION",
            "reason": body.get("reason"),
            "reviewer_id": reviewer_id,
            "organization_id": organization_id,
            "id": review_id,
        },
    )
    if resolution == "EXCEPTION":
        session.execute(
            text("UPDATE prospects SET booking_exception = true WHERE organization_id = :organization_id AND id = :id"),
            {"organization_id": organization_id, "id": row["prospect_id"]},
        )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=reviewer_id,
        action="prospect.review_resolved",
        target_type="human_review",
        target_id=review_id,
        target_version=None,
        request_id="prospect",
        before_state={"state": row["state"]},
        after_state={"resolution": resolution, "final_housing_decision": False},
    )
    return {"id": str(review_id), "resolution": resolution, "exception_granted": resolution == "EXCEPTION", "final_housing_decision": False}


def record_disposition(session, organization_id, prospect_id, note: str, reason: str, actor_id) -> dict:
    if not reason.strip() or not note.strip():
        problem(422, "VALIDATION_ERROR", "A person must record both the note and the reason.")
    disposition_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO housing_dispositions (
              id, organization_id, prospect_id, decision_note, reason, decided_by
            ) VALUES (
              :id, :organization_id, :prospect_id, :decision_note, :reason, :decided_by
            )
            """
        ),
        {
            "id": disposition_id,
            "organization_id": organization_id,
            "prospect_id": prospect_id,
            "decision_note": note,
            "reason": reason,
            "decided_by": actor_id,
        },
    )
    write_audit(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="prospect.disposition_recorded",
        target_type="housing_disposition",
        target_id=disposition_id,
        target_version=None,
        request_id="prospect",
        before_state=None,
        after_state={"human": True},
    )
    return {"id": str(disposition_id), "decided_by": str(actor_id), "automated": False}


def _apply_rules(session, organization_id, policy, intake) -> tuple[list[dict], list[str], bool]:
    rules = policy["rules"] if isinstance(policy["rules"], list) else json.loads(policy["rules"])
    rent = None
    if policy["property_id"] is not None:
        listing = session.execute(
            text(
                """
                SELECT asking_rent_cents FROM listings
                WHERE organization_id = :organization_id AND property_id = :property_id AND active = true
                ORDER BY created_at LIMIT 1
                """
            ),
            {"organization_id": organization_id, "property_id": policy["property_id"]},
        ).scalar()
        rent = listing
    results = []
    missing = []
    review = False
    for rule in rules:
        field = rule["field"]
        if field == "pets_declared" and intake["assistance_animal_requested"]:
            results.append({"rule_id": rule["id"], "result": "NOT_APPLIED", "reason": "assistance_animal"})
            continue
        value = _rule_value(intake, field)
        if value is None:
            results.append({"rule_id": rule["id"], "result": "UNKNOWN"})
            missing.append(field)
            continue
        passed = _compare(rule, value, rent)
        if passed:
            results.append({"rule_id": rule["id"], "result": "PASS"})
        else:
            results.append({"rule_id": rule["id"], "result": "HUMAN_REVIEW"})
            review = True
    return results, missing, review


def _compare(rule, value, rent) -> bool:
    operator = rule["operator"]
    if operator == "gte_rent_multiple":
        if rent is None:
            return False
        required = round_half_up_ratio(int(rent), int(rule["ratio_numerator"]), int(rule["ratio_denominator"]))
        return int(value) >= required
    if operator == "in":
        return value in rule["values"]
    if operator == "gte":
        return value >= rule["value"]
    if operator == "lte":
        return value <= rule["value"]
    return False


def _rule_value(intake, field):
    if field == "household_income_monthly_cents":
        return intake["income_monthly_cents"]
    if field == "lease_months":
        return intake["lease_months"]
    if field == "occupant_count":
        return intake["occupant_count"]
    if field == "pets_declared":
        return intake["pets_declared"]
    return None


def _missing(intake) -> list[str]:
    missing = []
    if intake["income_original_cents"] is None or intake["income_period"] is None:
        missing.append("income_period" if intake["income_original_cents"] is not None else "household_income")
    if intake["lease_months"] is None:
        missing.append("lease_months")
    if intake["move_in_date"] is None:
        missing.append("move_in_date")
    if intake["occupant_count"] is None:
        missing.append("occupant_count")
    return missing


def _input_hash(intake: dict) -> str:
    payload = {
        "income_monthly_cents": intake["income_monthly_cents"],
        "income_period": intake["income_period"],
        "income_original_cents": intake["income_original_cents"],
        "lease_months": intake["lease_months"],
        "occupant_count": intake["occupant_count"],
        "pets_declared": intake["pets_declared"],
        "assistance_animal_requested": intake["assistance_animal_requested"],
        "rental_history": intake["rental_history"],
        "move_in_date": None if intake["move_in_date"] is None else str(intake["move_in_date"]),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _open_accommodation(session, organization_id, prospect_id, user_id, key: bytes | None, note: str) -> None:
    if key is None:
        problem(500, "CONFIGURATION_REQUIRED", "Accommodation storage is not configured.")
    ciphertext, nonce, version = encrypt_text(note, key)
    session.execute(
        text(
            """
            INSERT INTO accommodation_cases (
              id, organization_id, prospect_id, subject_user_id, ciphertext, nonce, key_version, state
            ) VALUES (
              :id, :organization_id, :prospect_id, :subject_user_id, :ciphertext, :nonce, :key_version, 'OPEN'
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "prospect_id": prospect_id,
            "subject_user_id": user_id,
            "ciphertext": ciphertext,
            "nonce": nonce,
            "key_version": version,
        },
    )


def _resolve_listing(session, organization_id, source: str, external_id: str | None, hint: str | None) -> dict:
    if external_id:
        rows = session.execute(
            text(
                """
                SELECT id, property_id, unit_id, display_label
                FROM listings
                WHERE organization_id = :organization_id AND external_source = :source
                  AND external_listing_id = :external_id AND active = true
                """
            ),
            {"organization_id": organization_id, "source": source, "external_id": external_id},
        ).mappings().all()
    elif hint:
        rows = session.execute(
            text(
                """
                SELECT id, property_id, unit_id, display_label
                FROM listings
                WHERE organization_id = :organization_id AND active = true
                  AND display_label ILIKE :hint
                """
            ),
            {"organization_id": organization_id, "hint": f"%{hint}%"},
        ).mappings().all()
    else:
        rows = []
    if len(rows) == 1:
        return {"match": rows[0], "ambiguous": False, "clarification": ""}
    return {
        "match": None,
        "ambiguous": True,
        "clarification": "Which listing should this inquiry use? No unit was selected.",
    }


def _prospect(session, organization_id, prospect_id) -> dict:
    row = _lock_prospect(session, organization_id, prospect_id)
    intake = _intake(session, organization_id, prospect_id)
    return {
        "id": str(row["id"]),
        "state": row["state"],
        "unverified": row["unverified"],
        "property_id": None if row["property_id"] is None else str(row["property_id"]),
        "listing_id": None if row["listing_id"] is None else str(row["listing_id"]),
        "disclosure": DISCLOSURE,
        "intake": intake,
        "questions": questions_for(intake),
        "final_housing_decision": False,
    }


def _lock_prospect(session, organization_id, prospect_id):
    row = session.execute(
        text("SELECT * FROM prospects WHERE organization_id = :organization_id AND id = :id FOR UPDATE"),
        {"organization_id": organization_id, "id": prospect_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Prospect not found.")
    return row


def _intake(session, organization_id, prospect_id) -> dict:
    row = session.execute(
        text("SELECT * FROM prospect_intakes WHERE organization_id = :organization_id AND prospect_id = :prospect_id"),
        {"organization_id": organization_id, "prospect_id": prospect_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Intake not found.")
    return {
        "move_in_date": None if row["move_in_date"] is None else row["move_in_date"].isoformat(),
        "lease_months": row["lease_months"],
        "income_original_cents": row["income_original_cents"],
        "income_period": row["income_period"],
        "income_monthly_cents": row["income_monthly_cents"],
        "income_unverified": row["income_unverified"],
        "occupant_count": row["occupant_count"],
        "pets_declared": row["pets_declared"],
        "assistance_animal_requested": row["assistance_animal_requested"],
        "rental_history": row["rental_history"],
        "income_source": row["income_source"],
        "version": row["version"],
    }


def own_prospect_id(session, organization_id, user_id):
    return session.execute(
        text("SELECT id FROM prospects WHERE organization_id = :organization_id AND user_id = :user_id"),
        {"organization_id": organization_id, "user_id": user_id},
    ).scalar()
