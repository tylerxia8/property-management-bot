"""PostgreSQL outbox worker. Delivery stays off. Redis is not used."""

import json
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.db import set_tenant
from grok_bot.domain.accounting import approve_invoice
from grok_bot.errors import problem


def dispatch_outbox(session: Session, organization_id: UUID, actor_id: UUID, now, *, max_attempts: int = 5) -> dict:
    set_tenant(session, organization_id, actor_id)
    if not _staff(session, organization_id, actor_id):
        problem(403, "FORBIDDEN", "The worker actor is not staff in this organization.")
    rows = session.execute(
        text(
            """
            SELECT id, event_type, payload, attempt_count
            FROM outbox_events
            WHERE organization_id = :organization_id
              AND status = 'PENDING'
              AND available_at <= :now
              AND event_type IN ('InvoiceApproved', 'WorkerProbe')
            ORDER BY created_at, id
            """
        ),
        {"organization_id": organization_id, "now": now},
    ).mappings().all()
    processed = []
    for row in rows:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        try:
            with session.begin_nested():
                _apply(session, organization_id, actor_id, row["event_type"], payload)
            _progress(session, organization_id, row["id"], "DISPATCHED", int(row["attempt_count"]), now, None)
            processed.append({"id": str(row["id"]), "status": "DISPATCHED", "delivered": False})
        except Exception as exc:
            attempts = int(row["attempt_count"]) + 1
            status = "FAILED" if attempts >= max_attempts else "PENDING"
            available = now if status == "FAILED" else now + timedelta(seconds=2**attempts)
            _progress(session, organization_id, row["id"], status, attempts, available, str(exc)[:500])
            processed.append({"id": str(row["id"]), "status": status, "delivered": False, "attempts": attempts})
    return {"processed": processed, "delivered": False, "redis": False}


def _apply(session, organization_id, actor_id, event_type: str, payload: dict) -> None:
    if str(payload.get("actor_id", actor_id)) != str(actor_id):
        raise RuntimeError("worker actor does not match the signed actor")
    if event_type == "WorkerProbe":
        if payload.get("fail"):
            raise RuntimeError("probe failure")
        return
    if event_type != "InvoiceApproved":
        raise RuntimeError("no local handler for this event; nothing was delivered")
    if not _manager(session, organization_id, actor_id):
        raise RuntimeError("invoice approval requires a manager actor")
    approve_invoice(session, organization_id, UUID(payload["invoice_id"]), date.fromisoformat(payload["posting_date"]))


def _progress(session, organization_id, event_id, status: str, attempts: int, available, error: str | None) -> None:
    session.execute(
        text(
            """
            SELECT app_outbox_progress(
              :organization_id, :event_id, :status, :attempt_count, :available_at, :last_error
            )
            """
        ),
        {
            "organization_id": organization_id,
            "event_id": event_id,
            "status": status,
            "attempt_count": attempts,
            "available_at": available,
            "last_error": error,
        },
    )


def _staff(session, organization_id, actor_id) -> bool:
    return _has_role(session, organization_id, actor_id, ("property_manager", "organization_administrator", "accounting_staff"))


def _manager(session, organization_id, actor_id) -> bool:
    return _has_role(session, organization_id, actor_id, ("property_manager", "organization_administrator"))


def _has_role(session, organization_id, actor_id, roles: tuple[str, ...]) -> bool:
    found = session.execute(
        text(
            """
            SELECT role FROM role_grants
            WHERE organization_id = :organization_id
              AND user_id = :user_id
              AND resource_type IS NULL
              AND active_from <= clock_timestamp()
              AND (active_until IS NULL OR active_until > clock_timestamp())
            """
        ),
        {"organization_id": organization_id, "user_id": actor_id},
    ).scalars().all()
    return any(role in roles for role in found)
