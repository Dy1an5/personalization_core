from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import Field

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.types import JsonValue, NonEmptyString


class TextDocument(StrictFrozenDomainModel):
    id: UUID
    subject: SubjectRef
    text: NonEmptyString
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class TextSearchHit(StrictFrozenDomainModel):
    id: UUID
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    matched_terms: list[NonEmptyString] = Field(default_factory=list)

    @property
    def terms(self) -> list[str]:
        return list(self.matched_terms)


@runtime_checkable
class FullTextIndex(Protocol):
    name: str
    index_version: str

    async def upsert(self, documents: Sequence[TextDocument]) -> None:
        raise NotImplementedError

    async def search(
        self, subject: SubjectRef, query: str, limit: int
    ) -> list[TextSearchHit]:
        raise NotImplementedError

    async def delete_subject(self, subject: SubjectRef) -> None:
        raise NotImplementedError
