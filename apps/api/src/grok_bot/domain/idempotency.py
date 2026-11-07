import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.errors import problem


def request_hash(method: str, path: str, body: dict) -> str:
    encoded = json.dumps(
        {"body": body, "method": method.upper(), "path": path},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def find_replay(session: Session, organization_id: UUID, key: str, hashed: str) -> dict | None:
    row = session.execute(
        text(
            """
            SELECT request_hash, response_status, response_body
            FROM idempotency_records
            WHERE organization_id = :organization_id AND key = :key
            """
        ),
        {"organization_id": organization_id, "key": key},
    ).mappings().first()
    if row is None:
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
    key: str,
    hashed: str,
    status: int,
    body: dict,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO idempotency_records (
              id, organization_id, key, request_hash, response_status, response_body
            ) VALUES (
              :id, :organization_id, :key, :request_hash, :response_status, CAST(:response_body AS jsonb)
            )
            """
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "key": key,
            "request_hash": hashed,
            "response_status": status,
            "response_body": json.dumps(body, separators=(",", ":"), sort_keys=True),
        },
    )
