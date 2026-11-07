from fastapi import APIRouter, Request

from grok_bot.api.deps import request_id_of
from grok_bot.api.success import ERROR_RESPONSES, HealthOut

router = APIRouter(responses=ERROR_RESPONSES)


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> dict:
    return {
        "status": "ok",
        "local_auth_enabled": request.app.state.settings.allows_local_auth,
        "request_id": request_id_of(request),
    }
