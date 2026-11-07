from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_session, request_id_of
from grok_bot.domain.webhooks import accept_webhook

router = APIRouter()


@router.post("/webhooks/{provider}")
async def post_webhook(provider: str, request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    result = accept_webhook(
        session,
        request.app.state.settings,
        provider,
        body,
        request.headers.get("x-webhook-signature"),
        request.app.state.clock.now(),
    )
    result["request_id"] = request_id_of(request)
    return JSONResponse(status_code=202, content=result)
