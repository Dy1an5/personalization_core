from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import Field

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.memory import MemoryCandidate
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
    ) -> list[MemoryCandidate]:
        raise NotImplementedError
