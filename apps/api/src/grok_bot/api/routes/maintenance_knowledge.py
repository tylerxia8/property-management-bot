import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from grok_bot.api.deps import get_principal, get_session, require_idempotency_key
from grok_bot.api.success import ERROR_RESPONSES
from grok_bot.auth.permissions import Principal
from grok_bot.domain.maintenance_knowledge import APPROVED_INSTRUCTIONS, listing, save
from grok_bot.domain.maintenance_guidance import FAMILIES

router = APIRouter(responses=ERROR_RESPONSES)


class KnowledgeFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("problem_key", check_fields=False)
    @classmethod
    def known_problem(cls, value: str | None) -> str | None:
        if value is not None and value not in FAMILIES:
            raise ValueError("Choose a supported maintenance problem.")
        return value

    @field_validator("title", "model", "part_details", check_fields=False)
    @classmethod
    def safe_metadata(cls, value: str | None) -> str | None:
        if value is not None and (not re.fullmatch(r"[A-Za-z0-9 .,/()×'\"_-]*", value) or re.search(r"(?:sk-|ghp_|gho_|github_pat_|AKIA|ASIA|eyJ)[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{40,}", value) or re.search(r"\b(api|key|token|secret|password|passcode|code|pin|access|credential|bearer|unlock|bypass|wire|wiring|voltage|gas|electrical|breaker|repair|remove|disconnect|open|replace|install|ignore|instructions|prompt|system)\b", value, re.I)):
            raise ValueError("Use only appliance names, model identifiers, and part dimensions; exclude credentials and repair instructions.")
        return value

    @field_validator("instructions", check_fields=False)
    @classmethod
    def approved_instructions(cls, value: str | None) -> str | None:
        if value is not None and value not in APPROVED_INSTRUCTIONS:
            raise ValueError("Choose an approved low-risk instruction from the knowledge list.")
        return value

    @field_validator("reference_media_ids", check_fields=False)
    @classmethod
    def distinct_references(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Choose each reference photo only once.")
        return value


class KnowledgeCreate(KnowledgeFields):
    property_id: UUID
    title: str = Field(min_length=1, max_length=120)
    problem_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    model: str = Field(default="", max_length=120)
    part_details: str = Field(default="", max_length=300)
    instructions: str = Field(min_length=1, max_length=1000)
    reference_media_ids: list[UUID] = Field(default_factory=list, max_length=6)
    verified: bool = False


class KnowledgePatch(KnowledgeFields):
    version: int = Field(strict=True, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    problem_key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,79}$")
    model: str | None = Field(default=None, max_length=120)
    part_details: str | None = Field(default=None, max_length=300)
    instructions: str | None = Field(default=None, min_length=1, max_length=1000)
    reference_media_ids: list[UUID] | None = Field(default=None, max_length=6)
    verified: bool | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def nonnull_changes(self):
        if self.model_fields_set == {"version"} or any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Provide at least one non-null change with the version.")
        return self


class KnowledgeEntry(BaseModel):
    id: UUID
    property_id: UUID
    title: str
    problem_key: str
    model: str
    part_details: str
    instructions: str
    reference_media_ids: list[UUID]
    verified: bool
    verified_at: datetime | None
    verified_by: UUID | None
    version: int
    active: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeProperty(BaseModel):
    id: UUID
    name: str


class KnowledgeReferenceMedia(BaseModel):
    id: UUID
    property_id: UUID
    content_type: str
    created_at: datetime


class KnowledgeList(BaseModel):
    entries: list[KnowledgeEntry]
    properties: list[KnowledgeProperty]
    reference_media: list[KnowledgeReferenceMedia]
    approved_instructions: list[str]
    problem_keys: list[str]


@router.get("/maintenance-knowledge", response_model=KnowledgeList)
def get_knowledge(principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return listing(session, principal)


@router.post("/maintenance-knowledge", response_model=KnowledgeEntry)
def create_knowledge(body: KnowledgeCreate, request: Request, idempotency_key: str = Header(alias="Idempotency-Key"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return save(session, principal, None, body.model_dump(mode="json"), require_idempotency_key(idempotency_key), request.app.state.clock.now())


@router.patch("/maintenance-knowledge/{entry_id}", response_model=KnowledgeEntry)
def patch_knowledge(entry_id: UUID, body: KnowledgePatch, request: Request, idempotency_key: str = Header(alias="Idempotency-Key"), principal: Principal = Depends(get_principal), session: Session = Depends(get_session, scope="function")):
    return save(session, principal, entry_id, body.model_dump(mode="json", exclude_unset=True), require_idempotency_key(idempotency_key), request.app.state.clock.now())
