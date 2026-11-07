from fastapi import APIRouter, Request

from grok_bot.api.deps import request_id_of

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    return {
        "status": "ok",
        "local_auth_enabled": request.app.state.settings.allows_local_auth,
        "request_id": request_id_of(request),
    }
