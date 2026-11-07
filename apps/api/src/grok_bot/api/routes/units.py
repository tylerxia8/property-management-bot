from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from grok_bot.api.deps import (
    get_principal,
    get_session,
    request_id_of,
    require_capability,
    require_idempotency_key,
    require_version,
)
from grok_bot.api.schemas import UnitPatch, UnitWrite
from grok_bot.auth.permissions import Principal
from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.portfolio import create_unit, list_units, run_idempotent_create, update_unit
from grok_bot.api.success import ERROR_RESPONSES, UnitOut, UnitPageOut

router = APIRouter(responses=ERROR_RESPONSES)


@router.get("/properties/{property_id}/units", response_model=UnitPageOut)
def list_units_route(
    property_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session, scope="function"),
) -> dict:
    require_capability(principal, "units.read")
    return list_units(
        session,
        principal.organization_id,
        property_id,
        limit=limit,
        cursor=cursor,
        request_id=request_id_of(request),
    )


@router.post("/properties/{property_id}/units", response_model=UnitOut, status_code=201)
def create_unit_route(
    property_id: UUID,
    body: UnitWrite,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session, scope="function"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    require_capability(principal, "units.create")
    key = require_idempotency_key(idempotency_key)
    path = f"/v1/properties/{property_id}/units"
    hashed = request_hash("POST", path, body.model_dump())
    result, status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=hashed,
        create=lambda: create_unit(session, principal, property_id, body.label, request_id_of(request)),
    )
    return JSONResponse(
        status_code=201,
        content=result,
        headers={"ETag": f'"{result["version"]}"', "Idempotency-Status": status},
    )


@router.patch("/properties/{property_id}/units/{unit_id}", response_model=UnitOut)
def patch_unit_route(
    property_id: UUID,
    unit_id: UUID,
    body: UnitPatch,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session, scope="function"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    require_capability(principal, "units.update")
    version = require_version(if_match)
    updated = update_unit(
        session,
        principal,
        property_id,
        unit_id,
        body.label,
        version,
        request_id_of(request),
    )
    return JSONResponse(status_code=200, content=updated, headers={"ETag": f'"{updated["version"]}"'})
