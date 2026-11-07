from uuid import uuid4

import pytest

from tests.support import PROPERTY, bearer, login, seed_member


def test_unauthenticated_envelope(client):
    response = client.get("/v1/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert body["request_id"].startswith("req_")
    assert response.headers["X-Request-Id"] == body["request_id"]


def test_role_boundaries_and_if_match(client, migrator_engine):
    org_id = uuid4()
    admin_id = uuid4()
    manager_id = uuid4()
    accounting_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=admin_id,
            subject="admin@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
            org_name="Harbor",
        )
        seed_member(
            conn,
            org_id=org_id,
            user_id=manager_id,
            subject="manager@example.test",
            password="local-manager-password",
            roles=["property_manager"],
        )
        seed_member(
            conn,
            org_id=org_id,
            user_id=accounting_id,
            subject="accounting@example.test",
            password="local-accounting-password",
            roles=["accounting_staff"],
        )
    admin = bearer(login(client, "admin@example.test", "local-admin-password"))
    manager = bearer(login(client, "manager@example.test", "local-manager-password"))
    accounting = bearer(login(client, "accounting@example.test", "local-accounting-password"))

    assert client.post("/v1/properties", headers=manager, json=PROPERTY).status_code == 403
    missing_key = client.post("/v1/properties", headers=admin, json=PROPERTY)
    assert missing_key.status_code == 422
    assert missing_key.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    created = client.post(
        "/v1/properties",
        headers={**admin, "Idempotency-Key": "create-elm"},
        json=PROPERTY,
    )
    assert created.status_code == 201, created.text
    property_id = created.json()["id"]
    assert created.json()["organization_id"] == str(org_id)
    assert created.json()["version"] == 1

    replay = client.post(
        "/v1/properties",
        headers={**admin, "Idempotency-Key": "create-elm"},
        json=PROPERTY,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == property_id
    conflict = client.post(
        "/v1/properties",
        headers={**admin, "Idempotency-Key": "create-elm"},
        json={**PROPERTY, "name": "Different"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    extra = client.post(
        "/v1/properties",
        headers={**admin, "Idempotency-Key": "extra-org"},
        json={**PROPERTY, "organization_id": str(uuid4())},
    )
    assert extra.status_code == 422

    assert client.get("/v1/properties", headers=accounting).status_code == 200
    assert client.patch(
        f"/v1/properties/{property_id}",
        headers={**accounting, "If-Match": "1"},
        json={"name": "No"},
    ).status_code == 403
    missing_match = client.patch(
        f"/v1/properties/{property_id}",
        headers=manager,
        json={"name": "Renamed"},
    )
    assert missing_match.status_code == 428
    assert missing_match.json()["error"]["code"] == "PRECONDITION_REQUIRED"
    stale = client.patch(
        f"/v1/properties/{property_id}",
        headers={**manager, "If-Match": "9"},
        json={"name": "Renamed"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    renamed = client.patch(
        f"/v1/properties/{property_id}",
        headers={**manager, "If-Match": "1"},
        json={"name": "Renamed"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["version"] == 2
    assert client.patch(
        f"/v1/properties/{property_id}",
        headers={**admin, "If-Match": "2"},
        json={"name": "Admin cannot patch"},
    ).status_code == 403

    other = client.get(f"/v1/properties/{uuid4()}", headers=admin)
    assert other.status_code == 404


def test_portal_roles_are_forbidden(client, migrator_engine):
    org_id = uuid4()
    for role in ("owner", "tenant", "prospect", "contractor", "ai_service", "worker"):
        user_id = uuid4()
        subject = f"{role}@example.test"
        with migrator_engine.begin() as conn:
            seed_member(
                conn,
                org_id=org_id,
                user_id=user_id,
                subject=subject,
                password="local-portal-password",
                roles=[role],
                org_name="Portal",
            )
        token = bearer(login(client, subject, "local-portal-password"))
        response = client.get("/v1/properties", headers=token)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


def test_multiple_org_wide_roles_union_and_scoped_grant_is_ignored(client, migrator_engine):
    org_id = uuid4()
    user_id = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_id,
            user_id=user_id,
            subject="both@example.test",
            password="local-admin-password",
            roles=["organization_administrator", "property_manager"],
        )
        seed_member(
            conn,
            org_id=org_id,
            user_id=uuid4(),
            subject="scoped@example.test",
            password="local-manager-password",
            roles=["accounting_staff"],
        )
        conn = None
    with migrator_engine.begin() as conn:
        from sqlalchemy import text

        scoped_user = conn.execute(text("SELECT id FROM users WHERE subject = 'scoped@example.test'")).scalar()
        conn.execute(
            text(
                """
                INSERT INTO role_grants (
                  id, organization_id, user_id, role, resource_type, resource_id, active_from
                ) VALUES (
                  :id, :organization_id, :user_id, 'property_manager', 'property', :resource_id, clock_timestamp()
                )
                """
            ),
            {"id": uuid4(), "organization_id": org_id, "user_id": scoped_user, "resource_id": uuid4()},
        )
    both = login(client, "both@example.test", "local-admin-password")
    me = client.get("/v1/me", headers=bearer(both))
    assert me.status_code == 200
    assert "properties.create" in me.json()["capabilities"]
    assert "properties.update" in me.json()["capabilities"]
    scoped = client.get("/v1/me", headers=bearer(login(client, "scoped@example.test", "local-manager-password")))
    assert scoped.json()["roles"] == ["accounting_staff"]
    assert "properties.update" not in scoped.json()["capabilities"]


def test_expired_grant_cannot_sign_in(client, migrator_engine):
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=uuid4(),
            user_id=uuid4(),
            subject="expired@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
            active_from="1999-01-01T00:00:00Z",
            active_until="2000-01-01T00:00:00Z",
        )
    response = client.post(
        "/v1/auth/local/login",
        json={"subject": "expired@example.test", "password": "local-admin-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Subject or password is incorrect."


def test_unknown_subject_and_wrong_password_match(client, migrator_engine):
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=uuid4(),
            user_id=uuid4(),
            subject="known@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
        )
    wrong = client.post(
        "/v1/auth/local/login",
        json={"subject": "known@example.test", "password": "not-the-real-password"},
    )
    missing = client.post(
        "/v1/auth/local/login",
        json={"subject": "missing@example.test", "password": "local-admin-password"},
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["error"]["message"] == missing.json()["error"]["message"]


def test_ambiguous_subject_is_not_guessed(client, migrator_engine):
    for name in ("one", "two"):
        with migrator_engine.begin() as conn:
            seed_member(
                conn,
                org_id=uuid4(),
                user_id=uuid4(),
                subject="shared@example.test",
                password="local-admin-password",
                roles=["organization_administrator"],
                org_name=name,
            )
    response = client.post(
        "/v1/auth/local/login",
        json={"subject": "shared@example.test", "password": "local-admin-password"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AMBIGUOUS_IDENTITY"


def test_pagination_and_cross_org_get(client, migrator_engine):
    org_a = uuid4()
    org_b = uuid4()
    with migrator_engine.begin() as conn:
        seed_member(
            conn,
            org_id=org_a,
            user_id=uuid4(),
            subject="a@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
        )
        seed_member(
            conn,
            org_id=org_b,
            user_id=uuid4(),
            subject="b@example.test",
            password="local-admin-password",
            roles=["organization_administrator"],
        )
    token_a = bearer(login(client, "a@example.test", "local-admin-password"))
    token_b = bearer(login(client, "b@example.test", "local-admin-password"))
    ids = []
    for index in range(3):
        response = client.post(
            "/v1/properties",
            headers={**token_a, "Idempotency-Key": f"page-{index}"},
            json={**PROPERTY, "name": f"House {index}"},
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    hidden = client.post(
        "/v1/properties",
        headers={**token_b, "Idempotency-Key": "other-org"},
        json={**PROPERTY, "name": "Other"},
    )
    assert hidden.status_code == 201
    assert client.get(f"/v1/properties/{hidden.json()['id']}", headers=token_a).status_code == 404
    too_big = client.get("/v1/properties?limit=201", headers=token_a)
    assert too_big.status_code == 422
    seen = []
    cursor = None
    while True:
        path = "/v1/properties?limit=2" if cursor is None else f"/v1/properties?limit=2&cursor={cursor}"
        page = client.get(path, headers=token_a)
        assert page.status_code == 200, page.text
        seen.extend(item["id"] for item in page.json()["items"])
        cursor = page.json()["next_cursor"]
        if cursor is None:
            break
    assert seen == ids


def test_tampered_token_is_rejected(client, member):
    token = member["token"]
    response = client.get("/v1/me", headers=bearer(token[:-4] + "abcd"))
    assert response.status_code == 401


def test_openapi_lists_foundation_routes(client, app):
    document = client.get("/openapi.json")
    assert document.status_code == 200
    paths = document.json()["paths"]
    assert "/v1/properties" in paths
    assert "/v1/me" in paths
    assert "/v1/distribution-batches" not in paths
    assert app.state.engine.dialect.name == "postgresql"
