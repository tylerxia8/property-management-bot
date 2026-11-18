import re
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from grok_bot.db import set_tenant
from grok_bot.errors import problem
from grok_bot.settings import Settings


def record_health(engine: Engine, settings: Settings, error_type: str | None = None) -> None:
    if error_type is not None and not re.fullmatch(r"[A-Za-z]{1,80}", error_type):
        error_type = "WorkerError"
    with Session(engine) as session:
        if settings.twilio_configured:
            from grok_bot.domain.twilio_phone import service_scope

            service_scope(session, settings)
            organization_id = settings.twilio_organization_id
        elif settings.allows_demo_session:
            manager = session.execute(text("SELECT organization_id,user_id FROM app_demo_sample_session('property_manager')")).mappings().first()
            if manager is None:
                return
            organization_id = manager["organization_id"]
            set_tenant(session, organization_id, manager["user_id"])
        else:
            return
        if not session.scalar(text("SELECT public.app_actor_is_manager()")):
            problem(403, "FORBIDDEN", "Worker health requires an active manager grant.")
        session.execute(text("""
            INSERT INTO maintenance_worker_health(organization_id,worker_key,heartbeat_at,last_success_at,last_error_type,failure_count)
            VALUES(:org,'maintenance_phone',clock_timestamp(),CASE WHEN CAST(:error AS text) IS NULL THEN clock_timestamp() END,:error,CASE WHEN CAST(:error AS text) IS NULL THEN 0 ELSE 1 END)
            ON CONFLICT (organization_id,worker_key) DO UPDATE SET
                heartbeat_at=clock_timestamp(),
                last_success_at=CASE WHEN CAST(:error AS text) IS NULL THEN clock_timestamp() ELSE maintenance_worker_health.last_success_at END,
                last_error_type=:error,
                failure_count=maintenance_worker_health.failure_count+CASE WHEN CAST(:error AS text) IS NULL THEN 0 ELSE 1 END
        """), {"org": organization_id, "error": error_type})
        session.commit()


def worker_health(session: Session, organization_id: UUID, now: datetime) -> dict:
    if not session.scalar(text("SELECT public.app_actor_is_manager()")):
        problem(403, "FORBIDDEN", "Worker health requires an active manager grant.")
    row = session.execute(text("SELECT heartbeat_at,last_success_at,last_error_type,failure_count FROM maintenance_worker_health WHERE organization_id=:org AND worker_key='maintenance_phone'"), {"org": organization_id}).mappings().first()
    if row is None:
        return {"status": "not_started", "heartbeat_at": None, "last_success_at": None, "last_error_type": None, "failure_count": 0}
    status = "stale" if now - row["heartbeat_at"] > timedelta(minutes=2) else "error" if row["last_error_type"] is not None else "healthy"
    return {"status": status, **dict(row)}
