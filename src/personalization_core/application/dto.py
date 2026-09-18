from __future__ import annotations

from enum import StrEnum

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.errors import ErrorCode
from personalization_core.domain.events import Event, EventCreate
from personalization_core.domain.evidence import Evidence, EvidenceCreate


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
