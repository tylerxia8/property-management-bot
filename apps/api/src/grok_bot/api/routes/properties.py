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
from grok_bot.api.schemas import PropertyPatch, PropertyWrite
from grok_bot.auth.permissions import Principal
from grok_bot.domain.idempotency import request_hash
from grok_bot.domain.portfolio import create_property, get_property, list_properties, run_idempotent_create, update_property

router = APIRouter()


@router.get("/properties")
def list_properties_route(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> dict:
    require_capability(principal, "properties.read")
    return list_properties(
        session,
        principal.organization_id,
        limit=limit,
        cursor=cursor,
        request_id=request_id_of(request),
    )


@router.post("/properties")
def create_property_route(
    body: PropertyWrite,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    require_capability(principal, "properties.create")
    key = require_idempotency_key(idempotency_key)
    payload = body.model_dump()
    hashed = request_hash("POST", "/v1/properties", payload)
    result, status = run_idempotent_create(
        session,
        principal,
        key=key,
        hashed=hashed,
        create=lambda: create_property(session, principal, body, request_id_of(request)),
    )
    return _created(result, status)


@router.get("/properties/{property_id}")
def get_property_route(
    property_id: UUID,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
) -> JSONResponse:
    require_capability(principal, "properties.read")
    body = get_property(session, principal.organization_id, property_id, request_id_of(request))
    return JSONResponse(status_code=200, content=body, headers={"ETag": f'"{body["version"]}"'})


@router.patch("/properties/{property_id}")
def patch_property_route(
    property_id: UUID,
    body: PropertyPatch,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: Session = Depends(get_session),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    require_capability(principal, "properties.update")
    version = require_version(if_match)
    updated = update_property(
        session,
        principal,
        property_id,
        body.model_dump(exclude_unset=True),
        version,
        request_id_of(request),
    )
    return JSONResponse(status_code=200, content=updated, headers={"ETag": f'"{updated["version"]}"'})


def _created(body: dict, idempotency_status: str) -> JSONResponse:
    return JSONResponse(
        status_code=201,
        content=body,
        headers={"ETag": f'"{body["version"]}"', "Idempotency-Status": idempotency_status},
    )
