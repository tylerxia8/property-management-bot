from uuid import uuid4
from grok_bot.api.success import TicketOut
from pydantic import TypeAdapter
from tests.support import seed_member, bearer, login
from tests.test_maintenance import _staff, _report, _upload_and_complete
from io import BytesIO
from PIL import Image


def test_workspace_homes_list_pagination_and_access(client, migrator_engine):
    staff = _staff(client, migrator_engine)
    context = client.get("/v1/maintenance-context", headers=staff["tenant"]).json()
    assert context["homes"][0]["lease_id"] == staff["lease_id"]
    assert context["can_manage"] is False
    one = _report(client, staff["tenant"], "Kitchen pipe drips")
    two = _report(client, staff["tenant"], "Bedroom window sticks")
    manager_ticket = _report(client, staff["manager"], "Shared hallway light")
    page = client.get("/v1/maintenance-tickets?limit=1", headers=staff["tenant"]).json()
    assert [i["id"] for i in page["items"]] == [two["id"]]
    assert page["items"][0]["unit_label"] == "1"
    older = client.get(
        "/v1/maintenance-tickets",
        params={"before": page["next_cursor"]},
        headers=staff["tenant"],
    ).json()
    assert [i["id"] for i in older["items"]] == [one["id"]]
    assert (
        len(
            client.get("/v1/maintenance-tickets", headers=staff["manager"]).json()[
                "items"
            ]
        )
        == 3
    )
    assert (
        client.get(
            "/v1/maintenance-tickets/" + manager_ticket["id"], headers=staff["tenant"]
        ).status_code
        == 404
    )
    assert (
        client.get("/v1/maintenance-tickets", headers=staff["accounting"]).status_code
        == 403
    )
    other_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=staff["org_id"],
            user_id=other_id,
            subject="other-tenant@example.test",
            password="local-password-value",
            roles=["tenant"],
        )
    other = bearer(login(client, "other-tenant@example.test", "local-password-value"))
    assert client.get("/v1/maintenance-tickets", headers=other).json()["items"] == []
    assert (
        client.get("/v1/maintenance-tickets/" + one["id"], headers=other).status_code
        == 404
    )
    assert client.get("/v1/maintenance-context", headers=other).json()["homes"] == []
    foreign = _staff(client, migrator_engine)
    assert (
        client.get("/v1/maintenance-tickets", headers=foreign["manager"]).json()[
            "items"
        ]
        == []
    )


def test_report_retry_validation_and_home_binding(client, migrator_engine):
    staff = _staff(client, migrator_engine)
    headers = {**staff["tenant"], "Idempotency-Key": "maintenance-retry"}
    payload = {
        "description": "Kitchen sink drips",
        "lease_id": staff["lease_id"],
        "unit_id": staff["unit_id"],
    }
    one = client.post("/v1/maintenance-tickets", headers=headers, json=payload)
    two = client.post("/v1/maintenance-tickets", headers=headers, json=payload)
    assert one.status_code == two.status_code == 201, one.text
    assert one.json()["id"] == two.json()["id"]
    assert (
        len(
            client.get("/v1/maintenance-tickets", headers=staff["tenant"]).json()[
                "items"
            ]
        )
        == 1
    )
    conflict = client.post(
        "/v1/maintenance-tickets",
        headers=headers,
        json={"description": "Different problem"},
    )
    assert conflict.status_code == 409
    for description in ["", "   ", "x" * 5001]:
        assert (
            client.post(
                "/v1/maintenance-tickets",
                headers=staff["tenant"],
                json={"description": description},
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/v1/maintenance-tickets",
            headers=staff["tenant"],
            json={"description": "Leak", "unit_id": str(uuid4())},
        ).status_code
        == 422
    )


def test_structured_followups_do_not_fill_unrelated_fields_and_survive_reload(
    client, migrator_engine
):
    staff = _staff(client, migrator_engine)
    ticket = _report(client, staff["tenant"], "Sink drips")
    url = "/v1/maintenance-tickets/" + ticket["id"]
    answered = client.post(
        url + "/messages",
        headers=staff["tenant"],
        json={"body": "Kitchen sink", "field_key": "exact_location"},
    ).json()
    fields = {f["field_key"]: f for f in answered["intake"]}
    assert fields["exact_location"]["value_text"] == "Kitchen sink"
    assert fields["onset_frequency"]["status"] == "UNKNOWN"
    assert "Which room" not in " ".join(answered["next_questions"])
    update = client.post(
        url + "/messages",
        headers=staff["tenant"],
        json={"body": "The drip is slowing down", "field_key": "general"},
    ).json()
    assert "onset_frequency" in update["missing_fields"]
    assert len(update["messages"]) == 2
    assert (
        client.post(
            url + "/messages",
            headers=staff["tenant"],
            json={"body": " ", "field_key": "general"},
        ).status_code
        == 422
    )
    sent = client.post(
        url + "/messages",
        headers=staff["tenant"],
        json={"body": "That's all, hand off to the manager"},
    ).json()
    assert sent["handoff"] is True
    assert sent["status"] == "MANAGER_REVIEW"
    changed = client.post(
        url + "/transitions",
        headers=staff["manager"],
        json={
            "action": "set_status",
            "status": "IN_PROGRESS",
            "reason": "Plumber visit underway.",
        },
    )
    assert changed.status_code == 200, changed.text
    loaded = client.get(url, headers=staff["tenant"]).json()
    TypeAdapter(TicketOut).validate_python(loaded)
    assert loaded["status"] == "IN_PROGRESS"
    assert loaded["history"][-1]["reason"] == "Plumber visit underway."
    assert loaded["messages"][0]["body"] == "Kitchen sink"


def test_safety_in_optional_fields_and_explicit_answers(client, migrator_engine):
    staff = _staff(client, migrator_engine)
    response = client.post(
        "/v1/maintenance-tickets",
        headers=staff["tenant"],
        json={"description": "Kitchen issue", "safety_concerns": "I smell gas"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["emergency"] is True
    assert "electrical switches" in response.json()["safety_message"]
    assert response.json()["next_questions"] == []
    ticket = _report(client, staff["tenant"], "Ceiling stain")
    response = client.post(
        "/v1/maintenance-tickets/" + ticket["id"] + "/messages",
        headers=staff["tenant"],
        json={"body": "Water is flooding the room", "field_key": "exact_location"},
    )
    assert response.json()["emergency"] is True


def test_attached_photo_is_visible_and_satisfies_photo_question(
    client, migrator_engine, fixture_scanner
):
    staff = _staff(client, migrator_engine)
    ticket = _report(client, staff["tenant"], "Sink drips")
    payload = BytesIO()
    Image.new("RGB", (40, 40), "blue").save(payload, format="PNG")
    uploaded = _upload_and_complete(
        client,
        staff["tenant"],
        ticket["id"],
        payload.getvalue(),
        "image/png",
        "sink.png",
    )
    assert uploaded["status"] == "READY"
    loaded = client.get(
        "/v1/maintenance-tickets/" + ticket["id"], headers=staff["manager"]
    ).json()
    assert loaded["media"][0]["id"] == uploaded["id"]
    assert "media" not in loaded["missing_fields"]


def test_category_routing_and_hazard_word_boundaries():
    from grok_bot.domain.maintenance import _category, _classify

    for description, category in [
        ("Fridge stopped working", "appliance"),
        ("Mold in closet", "pest_mold"),
        ("Roof damage", "structural"),
        ("Door lock jammed", "lock"),
        ("No cooling upstairs", "hvac"),
    ]:
        assert _category(description) == category
    assert _classify("The fireplace door latch is loose") == (False, False)
    assert _classify("A fire is spreading")[0] is True
    assert _classify("Carbon monoxide alarm sounding")[0] is True
    assert _classify("There is a gas smell")[0] is True
