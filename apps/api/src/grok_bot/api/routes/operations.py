from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session
from grok_bot.auth.permissions import Principal
from grok_bot.errors import problem

router = APIRouter()


@router.get("/operations/queue")
def get_queue(principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    if not (principal.allows("distributions.approve") or principal.allows("receipts.read")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    organization_id = principal.organization_id
    dead = _count(session, "SELECT count(*) FROM outbox_events WHERE organization_id = :organization_id AND status = 'FAILED'", organization_id)
    unknown = _count(
        session,
        "SELECT count(*) FROM distribution_items WHERE organization_id = :organization_id AND status = 'UNKNOWN'",
        organization_id,
    )
    expiring = _count(
        session,
        """
        SELECT count(*) FROM distribution_batches
        WHERE organization_id = :organization_id AND status = 'APPROVED' AND expires_at IS NOT NULL
        """,
        organization_id,
    )
    unassigned = _count(
        session,
        """
        SELECT count(*) FROM maintenance_tickets AS t
        WHERE t.organization_id = :organization_id AND t.emergency IS TRUE
          AND NOT EXISTS (
            SELECT 1 FROM assignments AS a
            WHERE a.organization_id = t.organization_id AND a.ticket_id = t.id
          )
        """,
        organization_id,
    )
    return {
        "dead_letters": dead,
        "unknown_payments": unknown,
        "approved_batches": expiring,
        "unassigned_emergency_tickets": unassigned,
        "alerts_sent": False,
        "delivery_enabled": False,
    }


def _count(session, sql: str, organization_id) -> int:
    return int(session.execute(text(sql), {"organization_id": organization_id}).scalar() or 0)
