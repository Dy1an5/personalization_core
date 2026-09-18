from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.enums import (
    MemoryKind,
    MemoryScope,
    Polarity,
)
from personalization_core.domain.errors import ErrorCode
from personalization_core.domain.events import Event, EventCreate
from personalization_core.domain.evidence import Evidence, EvidenceCreate
from personalization_core.domain.memory import MemoryRecord, PreferenceTarget
from personalization_core.domain.types import JsonValue, NonEmptyString, UtcDatetime

PageLimit = Annotated[int, Field(ge=1, le=200)]


class EventIngestionInput(StrictFrozenDomainModel):
    event: EventCreate
    evidence: EvidenceCreate | None = None


class BatchMode(StrEnum):
    ATOMIC = "atomic"
    BEST_EFFORT = "best_effort"


class EventIngestionStatus(StrEnum):
    CREATED = "created"
    REPLAYED = "replayed"
    FAILED = "failed"


class EventIngestionResult(StrictFrozenDomainModel):
    status: EventIngestionStatus
    event: Event
    evidence: Evidence | None


class BatchItemResult(StrictFrozenDomainModel):
    index: int
    status: EventIngestionStatus
    event: Event | None = None
    evidence: Evidence | None = None
    error_code: ErrorCode | None = None
    error_message: str | None = None


class BatchIngestionResult(StrictFrozenDomainModel):
    mode: BatchMode
    items: list[BatchItemResult]
    created_count: int
    replayed_count: int
    failed_count: int


class EventPage(StrictFrozenDomainModel):
    items: list[Event]
    limit: int
    offset: int
    has_more: bool
    next_offset: int | None


class MemoryCreateInput(StrictFrozenDomainModel):
    key: NonEmptyString
    kind: MemoryKind
    content: NonEmptyString
    structured_value: dict[str, JsonValue] | None = None
    target: PreferenceTarget | None = None
    polarity: Polarity = Polarity.UNKNOWN
    scope: MemoryScope = MemoryScope.GLOBAL
    scope_value: NonEmptyString | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: UtcDatetime | None = None
    valid_until: UtcDatetime | None = None
    evidence: EvidenceCreate | None = None
    actor: NonEmptyString = "user"
    reason: NonEmptyString = "manual memory creation"


class MemoryPatchInput(StrictFrozenDomainModel):
    expected_revision: int = Field(ge=1)
    actor: NonEmptyString = "user"
    reason: NonEmptyString = "manual memory update"
    content: NonEmptyString | None = None
    structured_value: dict[str, JsonValue] | None = None
    target: PreferenceTarget | None = None
    polarity: Polarity | None = None
    scope: MemoryScope | None = None
    scope_value: NonEmptyString | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    valid_from: UtcDatetime | None = None
    valid_until: UtcDatetime | None = None


class MemoryPage(StrictFrozenDomainModel):
    items: list[MemoryRecord]
    limit: PageLimit
    offset: int = Field(ge=0)
    has_more: bool
    next_offset: int | None = None


class MemoryExtractionStatus(StrEnum):
    CREATED = "created"
    MERGED = "merged"
    REUSED = "reused"


class MemoryExtractionItem(StrictFrozenDomainModel):
    status: MemoryExtractionStatus
    memory: MemoryRecord
    evidence_id: UUID


class MemoryExtractionResult(StrictFrozenDomainModel):
    extractor_name: NonEmptyString
    extractor_version: NonEmptyString
    items: list[MemoryExtractionItem]
