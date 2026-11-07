from fastapi import APIRouter, Depends, Request

from grok_bot.api.deps import get_principal, request_id_of
from grok_bot.auth.permissions import Principal

router = APIRouter()


@router.get("/me")
def me(request: Request, principal: Principal = Depends(get_principal)) -> dict:
    return {
        "user_id": str(principal.user_id),
        "organization_id": str(principal.organization_id),
        "display_name": principal.display_name,
        "roles": list(principal.roles),
        "grants": principal.grant_dicts(),
        "capabilities": principal.capabilities(),
        "auth_method": principal.auth_method,
        "production_oidc": False,
        "request_id": request_id_of(request),
    }
