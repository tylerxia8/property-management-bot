"""Role switch for the isolated fixture sample. Production does not mount this route."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_session, request_id_of
from grok_bot.api.success import ERROR_RESPONSES, LoginOut
from grok_bot.auth.tokens import mint_local_token
from grok_bot.errors import problem

router = APIRouter(responses=ERROR_RESPONSES)

SAMPLE_ROLES = ("property_manager", "accounting_staff", "tenant", "prospect", "owner")


class DemoSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str


@router.post("/demo/session", response_model=LoginOut)
def demo_session(body: DemoSessionBody, request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings
    if not settings.allows_demo_session:
        problem(404, "NOT_FOUND", "Not found.")
    if body.role not in SAMPLE_ROLES:
        problem(422, "VALIDATION_ERROR", "That fixture role is not in the sample.")
    row = session.execute(
        text("SELECT user_id, organization_id, display_name FROM app_demo_sample_session(:role)"),
        {"role": body.role},
    ).mappings().first()
    if row is None:
        problem(404, "NOT_FOUND", "That fixture role is not in this database.")
    token = mint_local_token(
        secret=settings.session_secret,
        user_id=row["user_id"],
        organization_id=row["organization_id"],
        environment=settings.app_env,
        ttl_seconds=settings.local_token_ttl_seconds,
    )
    return {
        "token": token,
        "token_type": "bearer",
        "auth_method": "local_dev",
        "production_oidc": False,
        "user_id": str(row["user_id"]),
        "organization_id": str(row["organization_id"]),
        "display_name": row["display_name"],
        "request_id": request_id_of(request),
    }
