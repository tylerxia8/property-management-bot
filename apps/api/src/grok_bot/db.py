from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def build_engine(url: str, *, pool_size: int = 5, max_overflow: int = 5) -> Engine:
    engine = create_engine(
        url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "checkout")
    def _clear_tenant(dbapi_connection, connection_record, connection_proxy) -> None:
        previous = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("SELECT set_config('app.organization_id', '', false)")
            cursor.execute("SELECT set_config('app.actor_id', '', false)")
            cursor.close()
        finally:
            dbapi_connection.autocommit = previous

    return engine


def set_tenant(session: Session, organization_id: UUID, actor_id: UUID | None) -> None:
    session.execute(
        text(
            "SELECT set_config('app.organization_id', :organization_id, true), "
            "set_config('app.actor_id', :actor_id, true)"
        ),
        {
            "organization_id": str(organization_id),
            "actor_id": "" if actor_id is None else str(actor_id),
        },
    )
