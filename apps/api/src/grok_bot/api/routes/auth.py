from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, request_id_of
from grok_bot.api.schemas import LoginBody
from grok_bot.auth.constants import LOCAL_DEV_ISSUER
from grok_bot.auth.permissions import Principal
from grok_bot.auth.tokens import mint_local_token
from grok_bot.domain.distributions import record_step_up
from grok_bot.errors import problem

router = APIRouter()


@router.post("/auth/local/login")
def local_login(body: LoginBody, request: Request, session: Session = Depends(get_session)) -> dict:
    settings = request.app.state.settings
    if not settings.allows_local_auth:
        problem(404, "NOT_FOUND", "Not found.")
    rows = session.execute(
        text(
            """
            SELECT user_id, organization_id, display_name, role
            FROM app_local_login(:issuer, :subject, :password)
            """
        ),
        {"issuer": LOCAL_DEV_ISSUER, "subject": body.subject, "password": body.password},
    ).mappings().all()
    organizations = {row["organization_id"] for row in rows}
    if len(organizations) > 1:
        problem(
            409,
            "AMBIGUOUS_IDENTITY",
            "This subject matches more than one organization. An administrator must resolve it.",
        )
    if len(organizations) != 1:
        problem(401, "UNAUTHENTICATED", "Subject or password is incorrect.")
    first = rows[0]
    token = mint_local_token(
        secret=settings.session_secret,
        user_id=first["user_id"],
        organization_id=first["organization_id"],
        environment=settings.app_env,
        ttl_seconds=settings.local_token_ttl_seconds,
    )
    return {
        "token": token,
        "token_type": "bearer",
        "auth_method": "local_dev",
        "production_oidc": False,
        "user_id": str(first["user_id"]),
        "organization_id": str(first["organization_id"]),
        "display_name": first["display_name"],
        "request_id": request_id_of(request),
    }


@router.post("/auth/local/step-up")
def local_step_up(body: LoginBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)) -> dict:
    if not request.app.state.settings.allows_local_auth:
        problem(404, "NOT_FOUND", "Not found.")
    if body.subject != "" and body.password == "":
        problem(401, "UNAUTHENTICATED", "Step-up requires the local password.")
    checked = session.execute(
        text("SELECT user_id FROM app_local_login(:issuer, :subject, :password)"),
        {"issuer": LOCAL_DEV_ISSUER, "subject": body.subject, "password": body.password},
    ).scalar()
    if checked != principal.user_id:
        problem(401, "UNAUTHENTICATED", "Step-up requires the local password.")
    result = record_step_up(session, principal.organization_id, principal.user_id, request.app.state.clock.now())
    result["request_id"] = request_id_of(request)
    return result
