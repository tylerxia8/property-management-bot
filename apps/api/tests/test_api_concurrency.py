from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.support import PROPERTY, bearer, login, seed_member


def test_failed_commit_cannot_return_success(app, client, migrator_engine, monkeypatch):
    from grok_bot.api import deps

    with migrator_engine.begin() as conn:
        seed_member(conn, org_id=uuid4(), user_id=uuid4(), subject="commit-admin@example.test",
                    password="local-admin-password", roles=["organization_administrator"])
    token = bearer(login(client, "commit-admin@example.test", "local-admin-password"))

    class FailedCommit(Session):
        def commit(self):
            raise RuntimeError("Deliberate commit failure")

    monkeypatch.setattr(deps, "Session", FailedCommit)
    with TestClient(app, raise_server_exceptions=False) as failing:
        response = failing.post("/v1/properties", headers={**token, "Idempotency-Key": "commit-failure"},
                                json={**PROPERTY, "name": "Must not be committed"})
    assert response.status_code == 500
    with migrator_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM properties WHERE name = 'Must not be committed'")).scalar() == 0


def test_created_property_is_committed_before_response_starts(app, client, migrator_engine):
    with migrator_engine.begin() as conn:
        seed_member(conn, org_id=uuid4(), user_id=uuid4(), subject="visible-admin@example.test",
                    password="local-admin-password", roles=["organization_administrator"])
    token = bearer(login(client, "visible-admin@example.test", "local-admin-password"))
    observed = []

    async def observe(scope, receive, send):
        async def checked(message):
            if scope.get("path") == "/v1/properties" and message["type"] == "http.response.start":
                with migrator_engine.connect() as conn:
                    observed.append(conn.execute(text("SELECT count(*) FROM properties WHERE name = 'Visible before response'")).scalar())
            await send(message)
        await app(scope, receive, checked)

    with TestClient(observe) as observer:
        response = observer.post("/v1/properties", headers={**token, "Idempotency-Key": "visible-before-response"},
                                 json={**PROPERTY, "name": "Visible before response"})
    assert response.status_code == 201, response.text
    assert observed == [1]


def test_concurrent_if_match_allows_one_update(app, client, migrator_engine):
    org_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=uuid4(),
            subject="race-admin@example.test",
            password="local-admin-password",
            roles=["organization_administrator", "property_manager"],
        )
    token = bearer(login(client, "race-admin@example.test", "local-admin-password"))
    created = client.post(
        "/v1/properties",
        headers={**token, "Idempotency-Key": "race-create"},
        json=PROPERTY,
    )
    assert created.status_code == 201, created.text
    property_id = created.json()["id"]

    def patch(name: str):
        with TestClient(app) as local:
            return local.patch(
                f"/v1/properties/{property_id}",
                headers={**token, "If-Match": "1"},
                json={"name": name},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(patch, ("Left", "Right")))
    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 409]
    final = client.get(f"/v1/properties/{property_id}", headers=token)
    assert final.json()["version"] == 2


def test_concurrent_same_idempotency_key_creates_one_property(app, client, migrator_engine):
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=uuid4(),
            user_id=uuid4(),
            subject="idem-admin@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
        )
    token = bearer(login(client, "idem-admin@example.test", "local-admin-password"))

    def post():
        with TestClient(app) as local:
            return local.post(
                "/v1/properties",
                headers={**token, "Idempotency-Key": "same-key"},
                json=PROPERTY,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(), (1, 2)))
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    listed = client.get("/v1/properties", headers=token)
    assert len(listed.json()["items"]) == 1
