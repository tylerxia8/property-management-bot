import threading
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from grok_bot.db import set_tenant
from grok_bot.domain.screening import monthly_cents
from tests.support import PROPERTY, bearer, login, seed_member


def test_income_normalization_half_up_once():
    assert monthly_cents(6, "annual") == 1
    assert monthly_cents(3, "biweekly") == 7
    assert monthly_cents(3, "weekly") == 13
    assert monthly_cents(125, "monthly") == 125


def test_pro_01_missing_period_is_not_zero(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    updated = client.patch(
        f"/v1/prospects/{prospect['id']}/intake",
        headers=staff["prospect"],
        json={"income_original_cents": 250000},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["income_original_cents"] == 250000
    assert updated.json()["income_monthly_cents"] is None
    assert updated.json()["income_treated_as_zero"] is False
    assert any("not treated as zero" in question for question in updated.json()["questions"])
    evaluated = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert evaluated.status_code == 200, evaluated.text
    body = evaluated.json()
    assert body["result"] == "NEEDS_INFORMATION"
    assert "income_period" in body["missing_fields"]
    assert body["final_denial"] is False
    assert body["formal_screening_permitted"] is False
    with migrator_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT income_original_cents, income_monthly_cents FROM prospect_intakes WHERE prospect_id = :id"),
            {"id": prospect["id"]},
        ).one()
        dispositions = conn.execute(
            text("SELECT count(*) FROM housing_dispositions WHERE prospect_id = :id"),
            {"id": prospect["id"]},
        ).scalar()
    assert stored.income_original_cents == 250000
    assert stored.income_monthly_cents is None
    assert dispositions == 0


def test_clearing_income_period_removes_derived_income_and_preserves_omitted_fields(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=300000)
    response = client.patch(
        f"/v1/prospects/{prospect['id']}/intake", headers=staff["prospect"],
        json={"income_period": None},
    )
    assert response.status_code == 200, response.text
    assert response.json()["income_period"] is None
    assert response.json()["income_monthly_cents"] is None
    assert response.json()["income_original_cents"] == 300000
    assert response.json()["lease_months"] == 12
    result = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert result.status_code == 200, result.text
    assert result.json()["result"] == "NEEDS_INFORMATION"
    assert "income_period" in result.json()["missing_fields"]
    assert result.json()["final_denial"] is False


def test_pro_02_qualified_unverified_booking_orders_no_report(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=300000)
    evaluated = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["result"] == "PRELIMINARILY_QUALIFIED"
    assert evaluated.json()["formal_screening_permitted"] is False
    with migrator_engine.connect() as conn:
        unverified = conn.execute(
            text("SELECT income_unverified, unverified FROM prospect_intakes JOIN prospects ON prospects.id = prospect_intakes.prospect_id WHERE prospects.id = :id"),
            {"id": prospect["id"]},
        ).one()
    assert unverified.income_unverified is True
    assert unverified.unverified is True
    hold = _hold(client, staff, prospect["id"])
    assert hold["status"] == "HELD"
    assert hold["external_event_created"] is False
    report = client.post(f"/v1/prospects/{prospect['id']}/consumer-reports", headers=staff["manager"])
    assert report.status_code == 409
    assert report.json()["error"]["code"] == "REPORT_ORDERING_DISABLED"


def test_pro_03_invitation_and_report_before_tour_are_rejected(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=300000)
    client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    invited = client.post(
        f"/v1/prospects/{prospect['id']}/application-invitations",
        headers=staff["manager"],
        json={},
    )
    assert invited.status_code == 409
    assert invited.json()["error"]["code"] == "TOUR_NOT_COMPLETED"
    report = client.post(f"/v1/prospects/{prospect['id']}/consumer-reports", headers=staff["prospect"])
    assert report.status_code == 409
    assert report.json()["error"]["code"] == "REPORT_ORDERING_DISABLED"
    with migrator_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM application_invitations WHERE prospect_id = :id"), {"id": prospect["id"]}).scalar() == 0


def test_pro_04_below_fixture_threshold_is_review_not_denial(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=3)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=100000)
    evaluated = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["result"] == "HUMAN_REVIEW"
    assert evaluated.json()["final_denial"] is False
    assert evaluated.json()["policy_fixture"] is True
    reviews = client.get("/v1/human-reviews", headers=staff["manager"])
    assert reviews.status_code == 200, reviews.text
    assert reviews.json()["items"][0]["final_housing_decision"] is False
    assert reviews.json()["items"][0]["prospect_state"] == "HUMAN_REVIEW"
    blocked = client.post("/v1/prospects/{id}/dispositions".format(id=prospect["id"]), headers=staff["ai"], json={"decision_note": "deny", "reason": "model"})
    assert blocked.status_code == 403
    with migrator_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM housing_dispositions WHERE organization_id = :id"), {"id": staff["org_id"]}).scalar() == 0


def test_pro_05_assistance_animal_is_private_and_not_a_pet_denial(client, migrator_engine, app):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2, pets=True)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=300000, pets=True, assistance=True)
    evaluated = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["result"] == "HUMAN_REVIEW"
    assert all(item["result"] != "HUMAN_REVIEW" or item.get("reason") == "assistance_animal" or item["rule_id"] != "pets" for item in evaluated.json()["rule_results"])
    assert any(item["rule_id"] == "pets" and item["result"] == "NOT_APPLIED" for item in evaluated.json()["rule_results"])
    assert "Assistance-animal review requested." not in evaluated.text
    _as(app, staff, "accounting")
    with app.state.engine.connect() as conn:
        set_tenant(conn, staff["org_id"], staff["accounting_id"])
        assert conn.execute(text("SELECT count(*) FROM accommodation_cases")).scalar() == 0
        set_tenant(conn, staff["org_id"], staff["other_id"])
        assert conn.execute(text("SELECT count(*) FROM accommodation_cases")).scalar() == 0
        set_tenant(conn, staff["org_id"], staff["manager_id"])
        assert conn.execute(text("SELECT count(*) FROM accommodation_cases")).scalar() == 1


def test_pro_06_protected_fields_do_not_change_the_evaluation(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=300000)
    first = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"]).json()
    second = client.post(
        f"/v1/prospects/{prospect['id']}/evaluate",
        headers=staff["prospect"],
        json={"race": "ignored", "language": "ignored", "postal_code": "00000", "name": "Ignored"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["input_hash"] == first["input_hash"]
    assert second.json()["result"] == first["result"]
    rejected = client.post(
        f"/v1/properties/{staff['property_id']}/screening-policies",
        headers=staff["manager"],
        json={
            "legal_review_reference": "fixture:bad",
            "review_reason": "should fail",
            "effective_at": "2026-01-01T00:00:00Z",
            "fixture": True,
            "rules": [{"id": "race", "field": "race", "operator": "in", "values": [1], "failure_action": "HUMAN_REVIEW"}],
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "PROHIBITED_POLICY_FIELD"
    denial = client.post(
        f"/v1/properties/{staff['property_id']}/screening-policies",
        headers=staff["manager"],
        json={
            "legal_review_reference": "fixture:deny",
            "review_reason": "should fail",
            "effective_at": "2026-01-01T00:00:00Z",
            "fixture": True,
            "automatic_final_denial": True,
            "rules": [{"id": "income", "field": "household_income_monthly_cents", "operator": "gte_rent_multiple", "ratio_numerator": 2, "ratio_denominator": 1, "failure_action": "DENY"}],
        },
    )
    assert denial.status_code == 422


def test_pro_07_one_hold_wins_the_same_window(client, migrator_engine, app):
    staff = _people(client, migrator_engine, extra_prospect=True)
    _publish_fixture(client, staff, ratio=2)
    first = _start(client, staff, who="prospect")
    second = _start(client, staff, who="racer")
    _complete(client, staff, first["id"], income=300000, who="prospect")
    _complete(client, staff, second["id"], income=300000, who="racer")
    client.post(f"/v1/prospects/{first['id']}/evaluate", headers=staff["prospect"])
    client.post(f"/v1/prospects/{second['id']}/evaluate", headers=staff["racer"])
    barrier = threading.Barrier(2)
    results = []

    def attempt(headers, prospect_id):
        barrier.wait()
        response = client.post("/v1/appointments/holds", headers=headers, json=_hold_body(staff, prospect_id))
        results.append(response.status_code)

    threads = [
        threading.Thread(target=attempt, args=(staff["prospect"], first["id"])),
        threading.Thread(target=attempt, args=(staff["racer"], second["id"])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [201, 409]
    with migrator_engine.connect() as conn:
        active = conn.execute(
            text("SELECT count(*) FROM tour_appointments WHERE organization_id = :id AND status = 'HELD'"),
            {"id": staff["org_id"]},
        ).scalar()
    assert active == 1
    del app


def test_pro_08_dst_and_occupied_access(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=300000)
    client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    gap = client.post("/v1/appointments/holds", headers=staff["prospect"], json=_hold_body(staff, prospect["id"], local_start="2026-03-08T02:30:00"))
    assert gap.status_code == 409
    assert gap.json()["error"]["code"] == "NONEXISTENT_LOCAL_TIME"
    ambiguous = client.post("/v1/appointments/holds", headers=staff["prospect"], json=_hold_body(staff, prospect["id"], local_start="2026-11-01T01:30:00"))
    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "AMBIGUOUS_LOCAL_TIME"
    clarified = client.post(
        "/v1/appointments/holds",
        headers=staff["prospect"],
        json=_hold_body(staff, prospect["id"], local_start="2026-11-01T01:30:00", dst_resolution="later", unit_id=staff["occupied_unit_id"]),
    )
    assert clarified.status_code == 201, clarified.text
    occupied = client.post(
        f"/v1/appointments/{clarified.json()['id']}/confirm",
        headers=staff["manager"],
        json={"manager_local": True},
    )
    assert occupied.status_code == 409
    assert occupied.json()["error"]["code"] == "ACCESS_NOT_RECORDED"
    recorded = client.post(
        f"/v1/appointments/{clarified.json()['id']}/access-evidence",
        headers=staff["manager"],
        json={"evidence": "Manager recorded the access basis for this occupied unit."},
    )
    assert recorded.status_code == 200, recorded.text
    confirmed = client.post(
        f"/v1/appointments/{clarified.json()['id']}/confirm",
        headers=staff["manager"],
        json={"manager_local": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "MANAGER_CONFIRMED"
    assert confirmed.json()["external_event_created"] is False


def test_pro_09_pending_calendar_retry_is_one_event(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=300000)
    client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    hold = _hold(client, staff, prospect["id"])
    assert client.put(
        "/v1/kill-switches",
        headers=staff["manager"],
        json={"messaging_enabled": False, "calendar_enabled": True, "payment_enabled": False},
    ).status_code == 200
    first = client.post(f"/v1/appointments/{hold['id']}/confirm", headers=staff["manager"], json={"manager_local": False})
    second = client.post(f"/v1/appointments/{hold['id']}/confirm", headers=staff["manager"], json={"manager_local": False})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "CONFIRMATION_PENDING"
    assert first.json()["external_event_created"] is False
    assert second.json()["external_event_key"] == first.json()["external_event_key"]
    with migrator_engine.connect() as conn:
        jobs = conn.execute(
            text("SELECT count(*) FROM outbox_events WHERE organization_id = :id AND event_type = 'CalendarSyncRequested'"),
            {"id": staff["org_id"]},
        ).scalar()
    assert jobs == 1


def test_pro_10_cancel_and_opt_out_suppress_reminders(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    client.patch(
        f"/v1/prospects/{prospect['id']}/intake",
        headers=staff["prospect"],
        json={"consents": {"email": True, "sms": False}},
    )
    _complete(client, staff, prospect["id"], income=300000)
    client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    hold = _hold(client, staff, prospect["id"])
    client.post(f"/v1/appointments/{hold['id']}/confirm", headers=staff["manager"], json={"manager_local": False})
    with migrator_engine.connect() as conn:
        sms = conn.execute(
            text("SELECT status, delivered_at FROM reminder_jobs WHERE appointment_id = :id AND channel = 'sms'"),
            {"id": hold["id"]},
        ).mappings().all()
        email = conn.execute(
            text("SELECT status FROM reminder_jobs WHERE appointment_id = :id AND channel = 'email'"),
            {"id": hold["id"]},
        ).scalars().all()
    assert sms
    assert all(row["status"] == "OPTED_OUT" and row["delivered_at"] is None for row in sms)
    assert set(email) == {"SCHEDULED"}
    canceled = client.post(f"/v1/appointments/{hold['id']}/cancel", headers=staff["manager"])
    assert canceled.status_code == 200, canceled.text
    with migrator_engine.connect() as conn:
        statuses = conn.execute(
            text("SELECT status, delivered_at FROM reminder_jobs WHERE appointment_id = :id AND channel = 'email'"),
            {"id": hold["id"]},
        ).mappings().all()
    assert statuses
    assert all(row["status"] == "SUPPRESSED" and row["delivered_at"] is None for row in statuses)
    moved_hold = _hold(client, staff, prospect["id"])
    client.post(f"/v1/appointments/{moved_hold['id']}/confirm", headers=staff["manager"], json={"manager_local": False})
    moved = client.post(
        f"/v1/appointments/{moved_hold['id']}/reschedule",
        headers=staff["manager"],
        json=_hold_body(staff, prospect["id"], local_start="2026-11-12T15:00:00"),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["previous_reminders"] == "SUPPRESSED"
    with migrator_engine.connect() as conn:
        old = conn.execute(
            text("SELECT status FROM reminder_jobs WHERE appointment_id = :id AND channel = 'email'"),
            {"id": moved_hold["id"]},
        ).scalars().all()
    assert old
    assert set(old) == {"SUPPRESSED"}


def test_pro_11_ambiguous_listing_and_duplicate_message(client, migrator_engine):
    staff = _people(client, migrator_engine)
    other = client.post(
        "/v1/listings",
        headers=staff["manager"],
        json={
            "property_id": staff["property_id"],
            "unit_id": staff["unit_id"],
            "external_source": "zillow",
            "external_listing_id": "zillow-other",
            "display_label": "Elm Street duplicate",
            "asking_rent_cents": 100000,
        },
    )
    assert other.status_code == 201, other.text
    inquiry = client.post(
        "/v1/inquiries",
        headers=staff["manager"],
        json={"provider": "zillow", "provider_message_id": "msg-1", "address_hint": "Elm"},
    )
    assert inquiry.status_code == 201, inquiry.text
    assert inquiry.json()["ambiguous"] is True
    assert inquiry.json()["prospect_id"] is None
    assert "Which listing" in inquiry.json()["clarification"]
    again = client.post(
        "/v1/inquiries",
        headers=staff["manager"],
        json={"provider": "zillow", "provider_message_id": "msg-1", "address_hint": "Elm"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["duplicate"] is True
    assert again.json()["id"] == inquiry.json()["id"]
    clear = client.post(
        "/v1/inquiries",
        headers=staff["manager"],
        json={"provider": "zillow", "provider_message_id": "msg-2", "external_listing_id": "zillow-elm"},
    )
    assert clear.status_code == 201, clear.text
    assert clear.json()["prospect_id"]
    replay = client.post(
        "/v1/inquiries",
        headers=staff["manager"],
        json={"provider": "zillow", "provider_message_id": "msg-2", "external_listing_id": "zillow-elm"},
    )
    assert replay.json()["prospect_id"] == clear.json()["prospect_id"]
    with migrator_engine.connect() as conn:
        prospects = conn.execute(text("SELECT count(*) FROM prospects WHERE organization_id = :id"), {"id": staff["org_id"]}).scalar()
        tours = conn.execute(text("SELECT count(*) FROM tour_appointments WHERE organization_id = :id"), {"id": staff["org_id"]}).scalar()
    assert prospects == 1
    assert tours == 0


def test_pro_12_old_evaluation_survives_a_new_policy(client, migrator_engine):
    staff = _people(client, migrator_engine)
    _publish_fixture(client, staff, ratio=2)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=250000)
    first = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert first.json()["result"] == "PRELIMINARILY_QUALIFIED"
    _publish_fixture(client, staff, ratio=5)
    second = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert second.json()["result"] == "HUMAN_REVIEW"
    assert second.json()["policy_version"] != first.json()["policy_version"]


def test_inquiry_typo_offers_confirmation_and_does_not_override_external_id(client, migrator_engine):
    staff = _people(client, migrator_engine)
    request = {"provider": "zillow", "provider_message_id": "typo-1", "address_hint": "Elmm Street"}
    response = client.post("/v1/inquiries", headers=staff["manager"], json=request)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ambiguous"] and body["prospect_id"] is None
    assert "Elm Street" in body["clarification"]
    replay = client.post("/v1/inquiries", headers=staff["manager"], json=request).json()
    assert replay["clarification"] == body["clarification"]
    assert replay["duplicate"]
    request.update(provider_message_id="unknown-external", external_listing_id="does-not-exist")
    unknown = client.post("/v1/inquiries", headers=staff["manager"], json=request).json()
    assert unknown["prospect_id"] is None and "Possible listings" not in unknown["clarification"]
    with migrator_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT result, policy_version, input_hash FROM policy_evaluations WHERE prospect_id = :id ORDER BY created_at"),
            {"id": prospect["id"]},
        ).mappings().all()
    with pytest.raises(DBAPIError):
        with migrator_engine.begin() as conn:
            conn.execute(text("UPDATE policy_evaluations SET result = 'PRELIMINARILY_QUALIFIED'"))
    assert stored[0]["result"] == "PRELIMINARILY_QUALIFIED"
    assert stored[0]["input_hash"] == first.json()["input_hash"]
    assert stored[1]["result"] == "HUMAN_REVIEW"
    blocked = client.post("/v1/appointments/holds", headers=staff["prospect"], json=_hold_body(staff, prospect["id"]))
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "HUMAN_REVIEW_REQUIRED"
    review_id = client.get("/v1/human-reviews", headers=staff["manager"]).json()["items"][0]["id"]
    resolved = client.post(
        f"/v1/human-reviews/{review_id}/resolve",
        headers=staff["manager"],
        json={"resolution": "EXCEPTION", "reason": "Manager recorded an exception for this tour."},
    )
    assert resolved.status_code == 200, resolved.text
    held = _hold(client, staff, prospect["id"])
    assert held["status"] == "HELD"


def test_portal_actor_cannot_read_other_people_rows(client, migrator_engine, app):
    staff = _people(client, migrator_engine)
    with app.state.engine.connect() as conn:
        set_tenant(conn, staff["org_id"], staff["prospect_id"])
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM leases")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM journal_entries")).scalar() == 0
        set_tenant(conn, staff["org_id"], staff["manager_id"])
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 1
        set_tenant(conn, staff["org_id"], None)
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0
        set_tenant(conn, staff["org_id"], uuid4())
        assert conn.execute(text("SELECT count(*) FROM properties")).scalar() == 0


def test_no_policy_does_not_invent_a_threshold(client, migrator_engine):
    staff = _people(client, migrator_engine)
    prospect = _start(client, staff)
    _complete(client, staff, prospect["id"], income=999999)
    evaluated = client.post(f"/v1/prospects/{prospect['id']}/evaluate", headers=staff["prospect"])
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["result"] == "HUMAN_REVIEW"
    assert evaluated.json()["configuration_code"] == "CONFIGURATION_REQUIRED"
    assert evaluated.json()["policy_version"] is None
    assert evaluated.json()["final_denial"] is False


def _people(client, migrator_engine, extra_prospect=False):
    org_id = uuid4()
    specs = [
        ("admin", "organization_administrator"),
        ("manager", "property_manager"),
        ("accounting", "accounting_staff"),
        ("prospect", "prospect"),
        ("other", "prospect"),
        ("ai", "ai_service"),
        ("tenant", "tenant"),
    ]
    if extra_prospect:
        specs.append(("racer", "prospect"))
    people = {}
    with migrator_engine.begin() as conn:
        for name, role in specs:
            user_id = uuid4()
            subject = f"{name}-{user_id.hex[:8]}@example.test"
            seed_member(conn, org_id=org_id, user_id=user_id, subject=subject, password="local-password-value", roles=[role])
            people[name] = {"id": user_id, "subject": subject}
    tokens = {name: bearer(login(client, person["subject"], "local-password-value")) for name, person in people.items()}
    property_id = client.post("/v1/properties", headers={**tokens["admin"], "Idempotency-Key": f"p-{org_id}"}, json=PROPERTY).json()["id"]
    unit_id = client.post(
        f"/v1/properties/{property_id}/units",
        headers={**tokens["admin"], "Idempotency-Key": f"u-{org_id}"},
        json={"label": "Vacant"},
    ).json()["id"]
    occupied_unit_id = client.post(
        f"/v1/properties/{property_id}/units",
        headers={**tokens["admin"], "Idempotency-Key": f"uo-{org_id}"},
        json={"label": "Occupied"},
    ).json()["id"]
    lease = client.post(
        "/v1/leases",
        headers={**tokens["accounting"], "Idempotency-Key": f"l-{org_id}"},
        json={"unit_id": occupied_unit_id, "start_date": "2026-01-01", "end_date": "2027-01-01", "agreed_rent_cents": 100000},
    )
    assert lease.status_code == 201, lease.text
    listing = client.post(
        "/v1/listings",
        headers=tokens["manager"],
        json={
            "property_id": property_id,
            "unit_id": unit_id,
            "external_source": "zillow",
            "external_listing_id": "zillow-elm",
            "display_label": "Elm Street listing",
            "asking_rent_cents": 100000,
        },
    )
    assert listing.status_code == 201, listing.text
    schedule = client.post(
        f"/v1/properties/{property_id}/tour-schedules",
        headers=tokens["manager"],
        json={
            "duration_minutes": 30,
            "buffer_minutes": 15,
            "hold_minutes": 5,
            "min_notice_minutes": 0,
            "day_start": "09:00:00",
            "day_end": "17:00:00",
            "open_weekdays": [1, 2, 3, 4, 5, 6, 7],
            "timezone": "America/New_York",
            "fixture": True,
            "label": "fixture:prd-proposed-30-15-5",
        },
    )
    assert schedule.status_code == 201, schedule.text
    resource = client.post(
        f"/v1/properties/{property_id}/scheduling-resources",
        headers=tokens["manager"],
        json={"display_name": "Tour agent"},
    )
    assert resource.status_code == 201, resource.text
    staff = {
        "org_id": org_id,
        "property_id": property_id,
        "unit_id": unit_id,
        "occupied_unit_id": occupied_unit_id,
        "listing_id": listing.json()["id"],
        "resource_id": resource.json()["id"],
    }
    for name, person in people.items():
        staff[name] = tokens[name]
        staff[f"{name}_id"] = person["id"]
    return staff


def _publish_fixture(client, staff, ratio, pets=False):
    rules = [
        {
            "id": "income",
            "field": "household_income_monthly_cents",
            "operator": "gte_rent_multiple",
            "ratio_numerator": ratio,
            "ratio_denominator": 1,
            "failure_action": "HUMAN_REVIEW",
        }
    ]
    if pets:
        rules.append({"id": "pets", "field": "pets_declared", "operator": "in", "values": [0], "failure_action": "HUMAN_REVIEW"})
    response = client.post(
        f"/v1/properties/{staff['property_id']}/screening-policies",
        headers=staff["manager"],
        json={
            "legal_review_reference": "fixture:illustrative-not-a-requirement",
            "review_reason": "Test fixture labeled as not a real rental requirement.",
            "effective_at": "2026-01-01T00:00:00Z",
            "fixture": True,
            "rules": rules,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _start(client, staff, who="prospect"):
    response = client.post("/v1/prospects", headers=staff[who], json={"listing_id": staff["listing_id"]})
    assert response.status_code == 201, response.text
    assert "preliminary intake" in response.json()["disclosure"]
    return response.json()


def _complete(client, staff, prospect_id, income, who="prospect", pets=False, assistance=False):
    response = client.patch(
        f"/v1/prospects/{prospect_id}/intake",
        headers=staff[who],
        json={
            "move_in_date": "2026-12-01",
            "lease_months": 12,
            "income_original_cents": income,
            "income_period": "monthly",
            "occupant_count": 1,
            "pets_declared": pets,
            "assistance_animal_requested": assistance,
            "rental_history": "Prior tenancy 2024-2025, no objective complaint filed.",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _hold_body(staff, prospect_id, local_start="2026-11-10T15:00:00", dst_resolution=None, unit_id=None):
    body = {
        "prospect_id": prospect_id,
        "property_id": staff["property_id"],
        "resource_id": staff["resource_id"],
        "unit_id": staff["unit_id"] if unit_id is None else unit_id,
        "local_start": local_start,
        "timezone": "America/New_York",
    }
    if dst_resolution:
        body["dst_resolution"] = dst_resolution
    return body


def _hold(client, staff, prospect_id, who="prospect"):
    response = client.post("/v1/appointments/holds", headers=staff[who], json=_hold_body(staff, prospect_id))
    assert response.status_code == 201, response.text
    return response.json()


def _as(app, staff, name):
    del app, staff, name
