"""Organization outbound switches. Missing values stay off."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.errors import problem


def outbound_flags(session: Session, organization_id: UUID) -> dict:
    raw = session.execute(
        text("SELECT settings FROM organizations WHERE id = :id"),
        {"id": organization_id},
    ).scalar()
    if isinstance(raw, str):
        raw = json.loads(raw)
    outbound = {} if not isinstance(raw, dict) else raw.get("outbound") or {}
    return {
        "messaging_enabled": bool(outbound.get("messaging_enabled", False)),
        "calendar_enabled": bool(outbound.get("calendar_enabled", False)),
        "payment_enabled": bool(outbound.get("payment_enabled", False)),
    }


def set_outbound_flags(session: Session, organization_id: UUID, flags: dict) -> dict:
    value = {
        "messaging_enabled": bool(flags["messaging_enabled"]),
        "calendar_enabled": bool(flags["calendar_enabled"]),
        "payment_enabled": bool(flags["payment_enabled"]),
    }
    session.execute(
        text("SELECT app_set_outbound(:organization_id, CAST(:value AS jsonb))"),
        {"organization_id": organization_id, "value": json.dumps(value)},
    )
    stored = outbound_flags(session, organization_id)
    if stored != value:
        problem(403, "FORBIDDEN", "The outbound switches were not stored.")
    return stored
