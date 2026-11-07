import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.redaction import redact


def write_audit(
    session: Session,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    target_version: int | None,
    request_id: str,
    before_state: dict | None,
    after_state: dict | None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO audit_events (
              id, organization_id, actor_id, actor_type, action, target_type,
              target_id, target_version, request_id, before_state, after_state
            ) VALUES (
              :id, :organization_id, :actor_id, :actor_type, :action, :target_type,
              :target_id, :target_version, :request_id,
              CAST(:before_state AS jsonb), CAST(:after_state AS jsonb)
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "actor_id": actor_id,
            "actor_type": "user" if actor_id else "system",
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "target_version": target_version,
            "request_id": request_id,
            "before_state": _json(before_state),
            "after_state": _json(after_state),
        },
    )


def write_outbox(
    session: Session,
    *,
    organization_id: UUID,
    event_type: str,
    dedup_key: str,
    property_id: UUID | None,
    payload: dict,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO outbox_events (
              id, organization_id, event_type, payload, dedup_key, property_id, status
            ) VALUES (
              :id, :organization_id, :event_type, CAST(:payload AS jsonb),
              :dedup_key, :property_id, 'PENDING'
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "event_type": event_type,
            "payload": json.dumps(redact(payload), separators=(",", ":"), sort_keys=True),
            "dedup_key": dedup_key,
            "property_id": property_id,
        },
    )


def _json(value: dict | None) -> str | None:
    if value is None:
        return None
    return json.dumps(redact(value), separators=(",", ":"), sort_keys=True)
