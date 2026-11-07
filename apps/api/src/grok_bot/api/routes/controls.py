from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, require_capability
from grok_bot.api.success import ERROR_RESPONSES, AlertOut, SwitchOut
from grok_bot.auth.permissions import Principal
from grok_bot.domain.alerts import dispatch_alerts, raise_alert
from grok_bot.domain.controls import outbound_flags, set_outbound_flags

router = APIRouter(responses=ERROR_RESPONSES)


class SwitchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messaging_enabled: bool
    calendar_enabled: bool
    payment_enabled: bool


class AlertBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    fail: bool = False


@router.get("/kill-switches", response_model=SwitchOut)
def get_switches(principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "distributions.approve")
    return outbound_flags(session, principal.organization_id)


@router.put("/kill-switches", response_model=SwitchOut)
def put_switches(body: SwitchBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "distributions.approve")
    return set_outbound_flags(session, principal.organization_id, body.model_dump())


@router.post("/alerts", response_model=AlertOut)
def post_alert(body: AlertBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    require_capability(principal, "maintenance.acknowledge")
    created = raise_alert(session, principal.organization_id, body.kind, {"requested": True})
    result = dispatch_alerts(
        session,
        principal.organization_id,
        request.app.state.clock.now(),
        fail=body.fail,
    )
    result["id"] = created["id"]
    result["delivered_at"] = None
    return result
