from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from personalization_core.application.dto import (
    BatchMode,
    EventIngestionInput,
    MemoryCreateInput,
    MemoryPatchInput,
    ProfileRefreshOptions,
)
from personalization_core.domain.context import ContextRequest
from personalization_core.domain.entities import EntityCreate
from personalization_core.domain.enums import (
    MemoryAuthority,
    MemoryKind,
    MemoryScope,
    Polarity,
)
from personalization_core.domain.events import EventCreate
from personalization_core.domain.memory import PreferenceTarget
from personalization_core.domain.types import JsonValue
from personalization_core.ports.memory_extractor import ConversationMessage

MAX_BODY_BYTES = 256 * 1024
MAX_BATCH_ITEMS = 500
MAX_PAGE_LIMIT = 200
DEFAULT_PAGE_LIMIT = 50
MAX_MEMORY_CONTENT = 2_000
MAX_CONTEXT_QUERY = 4_000

NonEmptyApiString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]
MemoryContent = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_MEMORY_CONTENT
    ),
]
ContextQuery = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=MAX_CONTEXT_QUERY)
]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntityRequest(ApiModel):
    entity_type: NonEmptyApiString
    external_id: NonEmptyApiString
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    content_text: str | None = None
    schema_version: NonEmptyApiString

    def to_domain(self) -> EntityCreate:
        return EntityCreate.model_validate(self.model_dump())


class EventRequest(ApiModel):
    event: EventCreate
    evidence: Any = None

    @field_validator("evidence", mode="before")
    @classmethod
    def validate_evidence(cls, value: Any) -> Any:
        if value is None:
            return None
        from personalization_core.domain.evidence import EvidenceCreate

        return EvidenceCreate.model_validate(value)

    def to_domain(self) -> EventIngestionInput:
        return EventIngestionInput.model_validate(self.model_dump())


class BatchEventRequest(ApiModel):
    events: list[EventRequest] = Field(min_length=1, max_length=MAX_BATCH_ITEMS)
    mode: BatchMode = BatchMode.ATOMIC

    def to_domain(self) -> tuple[list[EventIngestionInput], BatchMode]:
        return [item.to_domain() for item in self.events], self.mode


class MemoryCreateRequest(ApiModel):
    key: NonEmptyApiString
    kind: MemoryKind
    content: MemoryContent
    structured_value: dict[str, JsonValue] | None = None
    target: PreferenceTarget | None = None
    polarity: Polarity = Polarity.UNKNOWN
    scope: MemoryScope = MemoryScope.GLOBAL
    scope_value: NonEmptyApiString | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    evidence: Any = None
    actor: NonEmptyApiString = "user"
    reason: NonEmptyApiString = "manual memory creation"

    @field_validator("evidence", mode="before")
    @classmethod
    def validate_evidence(cls, value: Any) -> Any:
        if value is None:
            return None
        from personalization_core.domain.evidence import EvidenceCreate

        return EvidenceCreate.model_validate(value)

    def to_domain(self) -> MemoryCreateInput:
        return MemoryCreateInput.model_validate(self.model_dump())


class MemoryPatchRequest(ApiModel):
    expected_revision: int = Field(ge=1)
    actor: NonEmptyApiString = "user"
    reason: NonEmptyApiString = "manual memory update"
    content: MemoryContent | None = None
    structured_value: dict[str, JsonValue] | None = None
    target: PreferenceTarget | None = None
    polarity: Polarity | None = None
    scope: MemoryScope | None = None
    scope_value: NonEmptyApiString | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    def to_domain(self) -> MemoryPatchInput:
        return MemoryPatchInput.model_validate(self.model_dump(exclude_unset=True))


class MemorySearchRequest(ApiModel):
    key: NonEmptyApiString | None = None
    kind: MemoryKind | None = None
    authority: MemoryAuthority | None = None
    scope: MemoryScope | None = None
    scope_value: NonEmptyApiString | None = None
    target_dimension: NonEmptyApiString | None = None
    target_value_key: NonEmptyApiString | None = None
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    offset: int = Field(default=0, ge=0)


class ConversationRequest(ApiModel):
    messages: list[ConversationMessage] = Field(min_length=1)


class MemoryActionRequest(ApiModel):
    expected_revision: int = Field(ge=1)
    actor: NonEmptyApiString = "user"
    reason: NonEmptyApiString = "memory state transition"


class ProfileRefreshRequest(ApiModel):
    as_of: datetime | None = None
    use_case: NonEmptyApiString | None = None
    topic: NonEmptyApiString | None = None
    entity: NonEmptyApiString | None = None
    force_new_snapshot: bool = False

    def to_domain(self) -> ProfileRefreshOptions:
        return ProfileRefreshOptions.model_validate(self.model_dump())


class ContextResolveRequest(ApiModel):
    query: ContextQuery | None = None
    use_case: NonEmptyApiString | None = None
    topic: NonEmptyApiString | None = None
    entity: NonEmptyApiString | None = None
    as_of: datetime | None = None
    token_budget: int | None = Field(default=None, ge=1, le=1_000_000)
    recent_limit: int = Field(default=5, ge=1, le=200)
    long_term_limit: int = Field(default=10, ge=1, le=200)
    include_inferred: bool = False

    def to_domain(self, subject: Any) -> ContextRequest:
        return ContextRequest.model_validate({"subject": subject, **self.model_dump()})


class PurgeRequest(ApiModel):
    confirmation: NonEmptyApiString


class SuccessEnvelope(ApiModel):
    data: Any
    request_id: str


class ErrorBody(ApiModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(ApiModel):
    error: ErrorBody
    request_id: str


def page_params(limit: int = DEFAULT_PAGE_LIMIT, offset: int = 0) -> tuple[int, int]:
    """Shared query validation for routes that expose offset pagination."""
    return limit, offset
