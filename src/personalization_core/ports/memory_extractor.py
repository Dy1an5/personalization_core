from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import Field

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.memory import MemoryCandidate, MemoryRecord
from personalization_core.domain.types import NonEmptyString, UtcDatetime


class ConversationMessage(StrictFrozenDomainModel):
    role: NonEmptyString
    content: NonEmptyString
    occurred_at: UtcDatetime
    evidence_ref: NonEmptyString
    metadata: dict[str, str] = Field(default_factory=dict)


@runtime_checkable
class MemoryExtractor(Protocol):
    name: str
    version: str

    async def extract(
        self, messages: Sequence[ConversationMessage]
    ) -> Sequence[MemoryExtraction]:
        raise NotImplementedError


class MemoryExtraction(StrictFrozenDomainModel):
    candidate: MemoryCandidate
    evidence_ref: NonEmptyString
    evidence_quote: NonEmptyString


@runtime_checkable
class MemoryContentFilter(Protocol):
    def allow(self, candidate: MemoryCandidate, message: ConversationMessage) -> bool:
        raise NotImplementedError


@runtime_checkable
class MemoryMergeStrategy(Protocol):
    def choose(
        self, existing: MemoryRecord | None, incoming: MemoryCandidate
    ) -> MemoryRecord | None:
        raise NotImplementedError


@runtime_checkable
class MemoryConfirmationPolicy(Protocol):
    def can_confirm(self, memory: MemoryRecord) -> bool:
        raise NotImplementedError


class AllowAllMemoryContentFilter:
    def allow(self, candidate: MemoryCandidate, message: ConversationMessage) -> bool:
        return True


class ExactKeyMergeStrategy:
    """默认不执行语义相似判断；精确槽位由 Application Service 处理。"""

    def choose(
        self, existing: MemoryRecord | None, incoming: MemoryCandidate
    ) -> MemoryRecord | None:
        return None


class EvidenceConfidenceConfirmationPolicy:
    def __init__(self, min_evidence_count: int, min_confidence: float) -> None:
        if min_evidence_count < 0:
            raise ValueError("min_evidence_count must be non-negative")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        self.min_evidence_count = min_evidence_count
        self.min_confidence = min_confidence

    def can_confirm(self, memory: MemoryRecord) -> bool:
        return (
            memory.evidence_count >= self.min_evidence_count
            and memory.confidence >= self.min_confidence
        )
