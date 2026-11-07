import base64
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from grok_bot.auth.permissions import Principal
from grok_bot.db import set_tenant
from grok_bot.domain.idempotency import find_replay, store_replay
from grok_bot.domain.records import write_audit, write_outbox
from grok_bot.errors import problem


def create_property(session: Session, principal: Principal, data, request_id: str) -> dict:
    property_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO properties (
              id, organization_id, name, address_line1, address_line2, city, region,
              postal_code, country_code, timezone, version, created_by
            ) VALUES (
              :id, :organization_id, :name, :address_line1, :address_line2, :city, :region,
              :postal_code, :country_code, :timezone, 1, :created_by
            )
            """
        ),
        _property_params(property_id, principal, data),
    )
    body = _property_body(session, principal.organization_id, property_id, request_id)
    write_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="property.created",
        target_type="property",
        target_id=property_id,
        target_version=1,
        request_id=request_id,
        before_state=None,
        after_state=_audit_view(body),
    )
    write_outbox(
        session,
        organization_id=principal.organization_id,
        event_type="property.created",
        dedup_key=f"property.created:{property_id}",
        property_id=property_id,
        payload={"property_id": str(property_id), "version": 1},
    )
    return body


def update_property(session: Session, principal: Principal, property_id: UUID, changes: dict, version: int, request_id: str) -> dict:
    current = get_property(session, principal.organization_id, property_id, request_id)
    assignments = []
    params: dict = {
        "id": property_id,
        "organization_id": principal.organization_id,
        "version": version,
    }
    allowed = {
        "name",
        "address_line1",
        "address_line2",
        "city",
        "region",
        "postal_code",
        "country_code",
        "timezone",
    }
    for key, value in changes.items():
        if key not in allowed:
            continue
        assignments.append(f"{key} = :{key}")
        params[key] = value
    assignments.append("version = version + 1")
    updated = session.execute(
        text(
            f"""
            UPDATE properties
            SET {", ".join(assignments)}
            WHERE organization_id = :organization_id AND id = :id AND version = :version
            RETURNING id
            """
        ),
        params,
    ).first()
    if updated is None:
        problem(
            409,
            "VERSION_CONFLICT",
            "The property changed since it was loaded.",
            {"current_version": current["version"]},
        )
    body = _property_body(session, principal.organization_id, property_id, request_id)
    write_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="property.updated",
        target_type="property",
        target_id=property_id,
        target_version=body["version"],
        request_id=request_id,
        before_state=_audit_view(current),
        after_state=_audit_view(body),
    )
    write_outbox(
        session,
        organization_id=principal.organization_id,
        event_type="property.updated",
        dedup_key=f"property.updated:{property_id}:{body['version']}",
        property_id=property_id,
        payload={"property_id": str(property_id), "version": body["version"]},
    )
    return body


def get_property(session: Session, organization_id: UUID, property_id: UUID, request_id: str) -> dict:
    row = session.execute(
        text(_property_select() + " WHERE p.organization_id = :organization_id AND p.id = :id"),
        {"organization_id": organization_id, "id": property_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Property not found.")
    return _row_to_property(row, request_id)


def list_properties(session: Session, organization_id: UUID, *, limit: int, cursor: str | None, request_id: str) -> dict:
    cursor_ts, cursor_id = _decode_cursor(cursor)
    rows = session.execute(
        text(
            _property_select()
            + """
            WHERE p.organization_id = :organization_id
              AND (CAST(:cursor_ts AS timestamptz) IS NULL OR (p.created_at, p.id) > (CAST(:cursor_ts AS timestamptz), CAST(:cursor_id AS uuid)))
            ORDER BY p.created_at, p.id
            LIMIT :limit
            """
        ),
        {
            "organization_id": organization_id,
            "cursor_ts": cursor_ts,
            "cursor_id": cursor_id,
            "limit": limit + 1,
        },
    ).mappings().all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page:
        last = page[-1]
        next_cursor = _encode_cursor(last["created_at"], last["id"])
    return {
        "items": [_row_to_property(row, request_id) for row in page],
        "next_cursor": next_cursor,
        "request_id": request_id,
    }


def create_unit(session: Session, principal: Principal, property_id: UUID, label: str, request_id: str) -> dict:
    get_property(session, principal.organization_id, property_id, request_id)
    unit_id = uuid4()
    try:
        with session.begin_nested():
            session.execute(
                text(
                    """
                    INSERT INTO units (id, organization_id, property_id, label, version)
                    VALUES (:id, :organization_id, :property_id, :label, 1)
                    """
                ),
                {
                    "id": unit_id,
                    "organization_id": principal.organization_id,
                    "property_id": property_id,
                    "label": label,
                },
            )
    except IntegrityError as exc:
        if _constraint_name(exc) == "units_label_per_property":
            problem(409, "DUPLICATE_UNIT_LABEL", "A unit with this label already exists on the property.")
        raise
    body = get_unit(session, principal.organization_id, property_id, unit_id, request_id)
    write_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="unit.created",
        target_type="unit",
        target_id=unit_id,
        target_version=1,
        request_id=request_id,
        before_state=None,
        after_state={"label": label, "property_id": str(property_id)},
    )
    write_outbox(
        session,
        organization_id=principal.organization_id,
        event_type="unit.created",
        dedup_key=f"unit.created:{unit_id}",
        property_id=property_id,
        payload={"unit_id": str(unit_id), "property_id": str(property_id), "version": 1},
    )
    return body


def update_unit(
    session: Session,
    principal: Principal,
    property_id: UUID,
    unit_id: UUID,
    label: str,
    version: int,
    request_id: str,
) -> dict:
    current = get_unit(session, principal.organization_id, property_id, unit_id, request_id)
    try:
        with session.begin_nested():
            updated = session.execute(
                text(
                    """
                    UPDATE units
                    SET label = :label, version = version + 1
                    WHERE organization_id = :organization_id
                      AND property_id = :property_id
                      AND id = :id
                      AND version = :version
                    RETURNING id
                    """
                ),
                {
                    "label": label,
                    "organization_id": principal.organization_id,
                    "property_id": property_id,
                    "id": unit_id,
                    "version": version,
                },
            ).first()
    except IntegrityError as exc:
        if _constraint_name(exc) == "units_label_per_property":
            problem(409, "DUPLICATE_UNIT_LABEL", "A unit with this label already exists on the property.")
        raise
    if updated is None:
        problem(
            409,
            "VERSION_CONFLICT",
            "The unit changed since it was loaded.",
            {"current_version": current["version"]},
        )
    body = get_unit(session, principal.organization_id, property_id, unit_id, request_id)
    write_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="unit.updated",
        target_type="unit",
        target_id=unit_id,
        target_version=body["version"],
        request_id=request_id,
        before_state={"label": current["label"]},
        after_state={"label": body["label"]},
    )
    write_outbox(
        session,
        organization_id=principal.organization_id,
        event_type="unit.updated",
        dedup_key=f"unit.updated:{unit_id}:{body['version']}",
        property_id=property_id,
        payload={"unit_id": str(unit_id), "version": body["version"]},
    )
    return body


def get_unit(session: Session, organization_id: UUID, property_id: UUID, unit_id: UUID, request_id: str) -> dict:
    row = session.execute(
        text(
            """
            SELECT id, organization_id, property_id, label, version, created_at
            FROM units
            WHERE organization_id = :organization_id AND property_id = :property_id AND id = :id
            """
        ),
        {"organization_id": organization_id, "property_id": property_id, "id": unit_id},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "Unit not found.")
    return _row_to_unit(row, request_id)


def list_units(session: Session, organization_id: UUID, property_id: UUID, *, limit: int, cursor: str | None, request_id: str) -> dict:
    get_property(session, organization_id, property_id, request_id)
    cursor_ts, cursor_id = _decode_cursor(cursor)
    rows = session.execute(
        text(
            """
            SELECT id, organization_id, property_id, label, version, created_at
            FROM units
            WHERE organization_id = :organization_id
              AND property_id = :property_id
              AND (CAST(:cursor_ts AS timestamptz) IS NULL OR (created_at, id) > (CAST(:cursor_ts AS timestamptz), CAST(:cursor_id AS uuid)))
            ORDER BY created_at, id
            LIMIT :limit
            """
        ),
        {
            "organization_id": organization_id,
            "property_id": property_id,
            "cursor_ts": cursor_ts,
            "cursor_id": cursor_id,
            "limit": limit + 1,
        },
    ).mappings().all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page:
        last = page[-1]
        next_cursor = _encode_cursor(last["created_at"], last["id"])
    return {
        "items": [_row_to_unit(row, request_id) for row in page],
        "next_cursor": next_cursor,
        "request_id": request_id,
    }


def run_idempotent_create(
    session: Session,
    principal: Principal,
    *,
    key: str,
    hashed: str,
    create,
) -> tuple[dict, str]:
    existing = find_replay(session, principal.organization_id, key, hashed)
    if existing is not None:
        return existing["body"], "replayed"
    try:
        with session.begin_nested():
            body = create()
            store_replay(
                session,
                organization_id=principal.organization_id,
                key=key,
                hashed=hashed,
                status=201,
                body=body,
            )
    except IntegrityError as exc:
        session.rollback()
        set_tenant(session, principal.organization_id, principal.user_id)
        if _constraint_name(exc) == "idempotency_org_key":
            existing = find_replay(session, principal.organization_id, key, hashed)
            if existing is not None:
                return existing["body"], "replayed"
            problem(409, "IDEMPOTENCY_CONFLICT", "This Idempotency-Key was already used for a different request.")
        raise
    return body, "created"


def _property_params(property_id: UUID, principal: Principal, data) -> dict:
    return {
        "id": property_id,
        "organization_id": principal.organization_id,
        "name": data.name,
        "address_line1": data.address_line1,
        "address_line2": data.address_line2,
        "city": data.city,
        "region": data.region,
        "postal_code": data.postal_code,
        "country_code": data.country_code,
        "timezone": data.timezone,
        "created_by": principal.user_id,
    }


def _property_select() -> str:
    return """
        SELECT p.id, p.organization_id, p.name, p.address_line1, p.address_line2, p.city,
               p.region, p.postal_code, p.country_code, p.timezone, p.version, p.created_at,
               (SELECT count(*) FROM units AS u
                 WHERE u.organization_id = p.organization_id AND u.property_id = p.id) AS unit_count
        FROM properties AS p
    """


def _property_body(session: Session, organization_id: UUID, property_id: UUID, request_id: str) -> dict:
    return get_property(session, organization_id, property_id, request_id)


def _row_to_property(row, request_id: str) -> dict:
    return {
        "id": str(row["id"]),
        "organization_id": str(row["organization_id"]),
        "name": row["name"],
        "address_line1": row["address_line1"],
        "address_line2": row["address_line2"],
        "city": row["city"],
        "region": row["region"],
        "postal_code": row["postal_code"],
        "country_code": str(row["country_code"]).strip(),
        "timezone": row["timezone"],
        "version": row["version"],
        "unit_count": int(row["unit_count"]),
        "created_at": _iso(row["created_at"]),
        "request_id": request_id,
    }


def _row_to_unit(row, request_id: str) -> dict:
    return {
        "id": str(row["id"]),
        "organization_id": str(row["organization_id"]),
        "property_id": str(row["property_id"]),
        "label": row["label"],
        "version": row["version"],
        "created_at": _iso(row["created_at"]),
        "request_id": request_id,
    }


def _audit_view(body: dict) -> dict:
    return {
        "name": body["name"],
        "address_line1": body["address_line1"],
        "city": body["city"],
        "region": body["region"],
        "postal_code": body["postal_code"],
        "country_code": body["country_code"],
        "timezone": body["timezone"],
        "version": body["version"],
    }


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = json.dumps({"i": str(row_id), "t": _iso(created_at)}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[str | None, str | None]:
    if cursor is None:
        return None, None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        datetime.fromisoformat(data["t"])
        UUID(data["i"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        problem(422, "INVALID_CURSOR", "The pagination cursor is invalid.")
        raise AssertionError from exc
    return data["t"], data["i"]


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    return getattr(diag, "constraint_name", None)
