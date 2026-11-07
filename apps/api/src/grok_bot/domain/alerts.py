"""Durable alert rows. Nothing is delivered."""

import json
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.domain.controls import outbound_flags


def raise_alert(session: Session, organization_id: UUID, kind: str, payload: dict) -> dict:
    alert_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO alert_events (id, organization_id, kind, payload, status)
            VALUES (:id, :organization_id, :kind, CAST(:payload AS jsonb), 'PENDING')
            """
        ),
        {
            "id": alert_id,
            "organization_id": organization_id,
            "kind": kind,
            "payload": json.dumps(payload, sort_keys=True),
        },
    )
    return {"id": str(alert_id), "status": "PENDING", "delivered_at": None}


def dispatch_alerts(session: Session, organization_id: UUID, now, *, fail: bool = False, max_attempts: int = 3) -> dict:
    flags = outbound_flags(session, organization_id)
    rows = session.execute(
        text(
            """
            SELECT id, kind, payload, attempt_count, fallback_of
            FROM alert_events
            WHERE organization_id = :organization_id AND status = 'PENDING' AND available_at <= :now
            ORDER BY created_at, id
            """
        ),
        {"organization_id": organization_id, "now": now},
    ).mappings().all()
    processed = []
    for row in rows:
        if not flags["messaging_enabled"]:
            _mark(session, row["id"], "SUPPRESSED", int(row["attempt_count"]), now)
            processed.append({"id": str(row["id"]), "status": "SUPPRESSED", "delivered_at": None})
            continue
        if fail:
            attempts = int(row["attempt_count"]) + 1
            if attempts >= max_attempts and row["fallback_of"] is None:
                _mark(session, row["id"], "FAILED", attempts, now)
                fallback_id = uuid4()
                session.execute(
                    text(
                        """
                        INSERT INTO alert_events (
                          id, organization_id, kind, payload, status, fallback_of
                        ) VALUES (
                          :id, :organization_id, :kind, CAST(:payload AS jsonb), 'PENDING', :fallback_of
                        )
                        """
                    ),
                    {
                        "id": fallback_id,
                        "organization_id": organization_id,
                        "kind": f"{row['kind']}_FALLBACK",
                        "payload": json.dumps({"fallback_of": str(row["id"])}),
                        "fallback_of": row["id"],
                    },
                )
                processed.append({"id": str(row["id"]), "status": "FAILED", "fallback_id": str(fallback_id), "delivered_at": None})
            else:
                status = "FAILED" if attempts >= max_attempts else "PENDING"
                _mark(session, row["id"], status, attempts, now + timedelta(seconds=1))
                processed.append({"id": str(row["id"]), "status": status, "delivered_at": None})
            continue
        _mark(session, row["id"], "FAILED", int(row["attempt_count"]) + 1, now)
        processed.append({"id": str(row["id"]), "status": "FAILED", "delivered_at": None})
    return {"processed": processed, "delivered": False}


def _mark(session, alert_id, status: str, attempts: int, available) -> None:
    session.execute(
        text(
            """
            UPDATE alert_events
            SET status = :status, attempt_count = :attempts, available_at = :available
            WHERE id = :id AND delivered_at IS NULL
            """
        ),
        {"status": status, "attempts": attempts, "available": available, "id": alert_id},
    )
