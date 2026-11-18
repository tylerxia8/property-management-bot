import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.errors import problem
from grok_bot.domain import idempotency


def find_replay(session: Session, organization_id: UUID, actor_id: UUID, ticket_id: UUID, key: str, hashed: str) -> dict | None:
    row = session.execute(
        text(
            """
            SELECT request_hash, response_status, response_body
            FROM maintenance_action_keys
            WHERE organization_id = :organization_id AND actor_id = :actor_id AND ticket_id = :ticket_id AND key = :key
            """
        ),
        {"organization_id": organization_id, "actor_id": actor_id, "ticket_id": ticket_id, "key": key},
    ).mappings().first()
    if row is None:
        if session.scalar(text("SELECT app_actor_is_staff()")):
            return idempotency.find_replay(session, organization_id, key, hashed)
        return None
    if row["request_hash"] != hashed:
        problem(
            409,
            "IDEMPOTENCY_CONFLICT",
            "This Idempotency-Key was already used for a different request.",
        )
    body = row["response_body"]
    if isinstance(body, str):
        body = json.loads(body)
    return {"status": row["response_status"], "body": body}


def store_replay(
    session: Session,
    *,
    organization_id: UUID,
    actor_id: UUID,
    ticket_id: UUID,
    key: str,
    hashed: str,
    status: int,
    body: dict,
) -> None:
    if session.scalar(text("SELECT app_actor_is_staff()")):
        idempotency.store_replay(session, organization_id=organization_id, key=key, hashed=hashed, status=status, body=body)
        return
    session.execute(
        text(
            """
            INSERT INTO maintenance_action_keys (
              id, organization_id, actor_id, ticket_id, key, request_hash, response_status, response_body
            ) VALUES (
              :id, :organization_id, :actor_id, :ticket_id, :key, :request_hash, :response_status, CAST(:response_body AS jsonb)
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "actor_id": actor_id,
            "ticket_id": ticket_id,
            "key": key,
            "request_hash": hashed,
            "response_status": status,
            "response_body": json.dumps(body, separators=(",", ":"), sort_keys=True),
        },
    )
