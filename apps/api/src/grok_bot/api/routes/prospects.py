from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, request_id_of, require_capability
from grok_bot.auth.permissions import Principal
from grok_bot.domain.screening import (
    DISCLOSURE,
    ensure_prospect,
    evaluate,
    list_reviews,
    own_prospect_id,
    publish_policy,
    receive_inquiry,
    record_disposition,
    resolve_review,
    update_intake,
)
from grok_bot.domain.tours import (
    add_resource,
    cancel_tour,
    complete_tour,
    confirm_tour,
    create_hold,
    invite_application,
    list_slots,
    publish_schedule,
    record_access,
    reschedule,
)
from grok_bot.errors import problem
from grok_bot.api.success import (
    ERROR_RESPONSES,
    AccessOut,
    AppointmentOut,
    DispositionOut,
    ErrorEnvelope,
    EvaluationOut,
    InquiryOut,
    IntakeMessageOut,
    IntakeUpdatedOut,
    InvitationOut,
    ListingCreatedOut,
    ListingPageOut,
    PolicyOut,
    ProspectOut,
    RescheduleOut,
    ResourceOut,
    ReviewPageOut,
    ReviewResolvedOut,
    ScheduleOut,
    SlotPageOut,
    TourCancelOut,
    TourCompleteOut,
)

router = APIRouter(responses=ERROR_RESPONSES)


class ListingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: UUID
    unit_id: UUID | None = None
    external_source: str
    external_listing_id: str
    display_label: str
    asking_rent_cents: int = Field(ge=0)


class InquiryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    provider_message_id: str
    external_listing_id: str | None = None
    address_hint: str | None = None


class IntakeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    move_in_date: str | None = None
    lease_months: int | None = None
    income_original_cents: int | None = Field(default=None, ge=0)
    income_period: str | None = None
    occupant_count: int | None = None
    pets_declared: bool | None = None
    assistance_animal_requested: bool | None = None
    rental_history: str | None = None
    income_source: str | None = None
    accommodation_note: str | None = None
    consents: dict[str, bool] | None = None


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    field: str
    operator: str
    failure_action: str = "HUMAN_REVIEW"
    ratio_numerator: int | None = None
    ratio_denominator: int | None = None
    values: list[int] | None = None
    value: int | None = None


class PolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal_review_reference: str
    review_reason: str
    effective_at: datetime
    rules: list[PolicyRule]
    missing_action: str = "NEEDS_INFORMATION"
    fixture: bool = False
    automatic_final_denial: bool = False


class ScheduleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_minutes: int
    buffer_minutes: int
    hold_minutes: int
    min_notice_minutes: int
    day_start: str
    day_end: str
    open_weekdays: list[int]
    timezone: str
    fixture: bool = False
    label: str = ""


class ResourceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str


class HoldBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prospect_id: UUID
    property_id: UUID
    resource_id: UUID
    unit_id: UUID | None = None
    local_start: str
    local_end: str | None = None
    timezone: str
    dst_resolution: str | None = None


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manager_local: bool = False


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: str
    reason: str | None = None


class DispositionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_note: str
    reason: str


class InvitationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_reference: str | None = None


class AccessBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: str


def _require_own(principal: Principal, session: Session, prospect_id: UUID) -> None:
    if principal.allows("prospects.review"):
        return
    if not principal.allows("prospects.own"):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    owned = own_prospect_id(session, principal.organization_id, principal.user_id)
    if owned != prospect_id:
        problem(404, "NOT_FOUND", "Prospect not found.")


@router.get("/listings", response_model=ListingPageOut)
def get_listings(principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    if not (principal.allows("prospects.own") or principal.allows("screening.publish") or principal.allows("prospects.review")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    from sqlalchemy import text

    rows = session.execute(
        text(
            """
            SELECT id, property_id, display_label, asking_rent_cents
            FROM listings
            WHERE organization_id = :organization_id AND active = true
            ORDER BY display_label
            """
        ),
        {"organization_id": principal.organization_id},
    ).mappings().all()
    return {
        "items": [
            {
                "id": str(row["id"]),
                "property_id": str(row["property_id"]),
                "display_label": row["display_label"],
                "asking_rent_cents": row["asking_rent_cents"],
            }
            for row in rows
        ]
    }


@router.post("/listings", response_model=ListingCreatedOut, status_code=201)
def post_listing(body: ListingBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "screening.publish")
    from uuid import uuid4
    from sqlalchemy import text

    listing_id = uuid4()
    session.execute(
        text(
            """
            INSERT INTO listings (
              id, organization_id, property_id, unit_id, external_source, external_listing_id,
              display_label, asking_rent_cents
            ) VALUES (
              :id, :organization_id, :property_id, :unit_id, :external_source, :external_listing_id,
              :display_label, :asking_rent_cents
            )
            """
        ),
        {"id": listing_id, "organization_id": principal.organization_id, **body.model_dump()},
    )
    return JSONResponse(status_code=201, content={"id": str(listing_id), "request_id": request_id_of(request)})


@router.post("/inquiries", response_model=InquiryOut, responses={201: {"model": InquiryOut}})
def post_inquiry(body: InquiryBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "prospects.review")
    result = receive_inquiry(session, principal.organization_id, body.model_dump())
    result["request_id"] = request_id_of(request)
    return JSONResponse(status_code=200 if result["duplicate"] else 201, content=result)


class ProspectStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: UUID | None = None


@router.post("/prospects", response_model=ProspectOut, status_code=201)
def post_prospect(body: ProspectStart, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "prospects.own")
    result = ensure_prospect(session, principal.organization_id, principal.user_id, body.listing_id)
    result["request_id"] = request_id_of(request)
    result["disclosure"] = DISCLOSURE
    return JSONResponse(status_code=201, content=result)


@router.patch("/prospects/{prospect_id}/intake", response_model=IntakeUpdatedOut)
def patch_intake(prospect_id: UUID, body: IntakeBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    _require_own(principal, session, prospect_id)
    result = update_intake(session, principal.organization_id, prospect_id, body.model_dump(exclude_unset=True), principal.user_id)
    result["request_id"] = request_id_of(request)
    return result


@router.post("/prospects/{prospect_id}/messages", response_model=IntakeMessageOut)
def post_messages(prospect_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    _require_own(principal, session, prospect_id)
    result = update_intake(session, principal.organization_id, prospect_id, {}, principal.user_id)
    result["request_id"] = request_id_of(request)
    result["model_adapter"] = "disabled"
    return result


@router.post("/properties/{property_id}/screening-policies", response_model=PolicyOut, status_code=201)
def post_policy(property_id: UUID, body: PolicyBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "screening.publish")
    payload = body.model_dump()
    payload["rules"] = body.model_dump()["rules"]
    return JSONResponse(status_code=201, content=publish_policy(session, principal.organization_id, property_id, payload, principal.user_id))


@router.post("/prospects/{prospect_id}/evaluate", response_model=EvaluationOut)
def post_evaluate(prospect_id: UUID, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    _require_own(principal, session, prospect_id)
    result = evaluate(
        session,
        principal.organization_id,
        prospect_id,
        principal.user_id,
        request.app.state.settings.contact_key_bytes,
        None,
    )
    result["request_id"] = request_id_of(request)
    return result


@router.get("/human-reviews", response_model=ReviewPageOut)
def get_reviews(principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "prospects.review")
    return list_reviews(session, principal.organization_id)


@router.post("/human-reviews/{review_id}/resolve", response_model=ReviewResolvedOut)
def post_resolve(review_id: UUID, body: ReviewBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "prospects.review")
    return resolve_review(session, principal.organization_id, review_id, body.model_dump(), principal.user_id)


@router.post("/properties/{property_id}/tour-schedules", response_model=ScheduleOut, status_code=201)
def post_schedule(property_id: UUID, body: ScheduleBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "tours.manage")
    return JSONResponse(status_code=201, content=publish_schedule(session, principal.organization_id, property_id, body.model_dump()))


@router.post("/properties/{property_id}/scheduling-resources", response_model=ResourceOut, status_code=201)
def post_resource(property_id: UUID, body: ResourceBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "tours.manage")
    return JSONResponse(status_code=201, content=add_resource(session, principal.organization_id, property_id, body.display_name))


@router.get("/tour-slots", response_model=SlotPageOut)
def get_slots(request: Request, property_id: UUID = Query(), principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    if not (principal.allows("tours.request") or principal.allows("tours.manage")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    return list_slots(session, principal.organization_id, property_id, request.app.state.clock)


@router.post("/appointments/holds", response_model=AppointmentOut, status_code=201)
def post_hold(body: HoldBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    if principal.allows("tours.request"):
        _require_own(principal, session, body.prospect_id)
    elif not principal.allows("tours.manage"):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    result = create_hold(session, principal.organization_id, body.model_dump(), request.app.state.clock)
    return JSONResponse(status_code=201, content=result)


@router.post("/appointments/{appointment_id}/confirm", response_model=AppointmentOut)
def post_confirm(appointment_id: UUID, body: ConfirmBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "tours.manage")
    return confirm_tour(session, principal.organization_id, appointment_id, principal.user_id, body.manager_local)


@router.post("/appointments/{appointment_id}/reschedule", response_model=RescheduleOut)
def post_reschedule(appointment_id: UUID, body: HoldBody, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "tours.manage")
    return reschedule(session, principal.organization_id, appointment_id, body.model_dump(), request.app.state.clock)


@router.post("/appointments/{appointment_id}/cancel", response_model=TourCancelOut)
def post_cancel(appointment_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    if not (principal.allows("tours.manage") or principal.allows("tours.request")):
        problem(403, "FORBIDDEN", "You do not have access to this action.")
    return cancel_tour(session, principal.organization_id, appointment_id)


@router.post("/appointments/{appointment_id}/complete", response_model=TourCompleteOut)
def post_complete(appointment_id: UUID, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "tours.manage")
    return complete_tour(session, principal.organization_id, appointment_id, principal.user_id)


@router.post("/appointments/{appointment_id}/access-evidence", response_model=AccessOut)
def post_access(appointment_id: UUID, body: AccessBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "tours.manage")
    return record_access(session, principal.organization_id, appointment_id, body.evidence)


@router.post("/prospects/{prospect_id}/application-invitations", response_model=InvitationOut, status_code=201)
def post_invitation(prospect_id: UUID, body: InvitationBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "invitations.write")
    return JSONResponse(status_code=201, content=invite_application(session, principal.organization_id, prospect_id, principal.user_id, body.external_reference))


@router.post("/prospects/{prospect_id}/dispositions", response_model=DispositionOut)
def post_disposition(prospect_id: UUID, body: DispositionBody, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)):
    require_capability(principal, "dispositions.write")
    return record_disposition(session, principal.organization_id, prospect_id, body.decision_note, body.reason, principal.user_id)


@router.post("/prospects/{prospect_id}/consumer-reports", response_model=ErrorEnvelope, status_code=409)
def post_report(prospect_id: UUID, principal: Principal = Depends(get_principal)):
    del prospect_id, principal
    problem(409, "REPORT_ORDERING_DISABLED", "No consumer-report provider is configured. No report was ordered.")
