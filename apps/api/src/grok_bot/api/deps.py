from collections.abc import Generator
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.auth.permissions import Principal
from grok_bot.auth.tokens import TokenError, verify_token
from grok_bot.db import set_tenant
from grok_bot.errors import problem


def get_session(request: Request) -> Generator[Session, None, None]:
    session = Session(request.app.state.engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def request_id_of(request: Request) -> str:
    current = getattr(request.state, "request_id", None)
    if not current:
        current = "req_missing"
        request.state.request_id = current
    return current


def get_principal(request: Request, session: Session = Depends(get_session)) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    token = header.split(" ", 1)[1].strip()
    settings = request.app.state.settings
    try:
        payload = verify_token(token, settings.session_secret)
    except TokenError:
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    if payload.get("amr") != "local_dev" or not settings.allows_local_auth or payload.get("env") != settings.app_env:
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    try:
        user_id = UUID(payload["sub"])
        organization_id = UUID(payload["org"])
    except (KeyError, ValueError):
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    set_tenant(session, organization_id, user_id)
    user = session.execute(
        text(
            """
            SELECT id, organization_id, display_name
            FROM users
            WHERE id = :user_id AND organization_id = :organization_id
            """
        ),
        {"user_id": user_id, "organization_id": organization_id},
    ).mappings().first()
    if user is None:
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    roles = session.execute(
        text(
            """
            SELECT role
            FROM role_grants
            WHERE user_id = :user_id
              AND organization_id = :organization_id
              AND resource_type IS NULL
              AND resource_id IS NULL
              AND active_from <= clock_timestamp()
              AND (active_until IS NULL OR active_until > clock_timestamp())
            ORDER BY role
            """
        ),
        {"user_id": user_id, "organization_id": organization_id},
    ).scalars().all()
    if not roles:
        problem(401, "UNAUTHENTICATED", "Sign-in is required.")
    return Principal(
        user_id=user["id"],
        organization_id=user["organization_id"],
        display_name=user["display_name"],
        roles=tuple(roles),
        auth_method="local_dev",
    )


def require_capability(principal: Principal, capability: str) -> None:
    if not principal.allows(capability):
        problem(403, "FORBIDDEN", "You do not have access to this action.")


def require_version(if_match: str | None) -> int:
    if if_match is None or not if_match.strip():
        problem(428, "PRECONDITION_REQUIRED", "If-Match is required.")
    raw = if_match.strip()
    if raw.startswith("W/"):
        raw = raw[2:].strip()
    raw = raw.strip('"')
    try:
        version = int(raw)
    except ValueError:
        problem(428, "PRECONDITION_REQUIRED", "If-Match must be the resource version.")
    if version < 1:
        problem(428, "PRECONDITION_REQUIRED", "If-Match must be the resource version.")
    return version


def require_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip():
        problem(422, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required for this command.")
    key = value.strip()
    if len(key) > 200:
        problem(422, "VALIDATION_ERROR", "Idempotency-Key must be 200 characters or fewer.")
    return key
