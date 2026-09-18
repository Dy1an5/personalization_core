from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Protocol, runtime_checkable
from uuid import UUID

from pydantic import Field

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.types import JsonValue, NonEmptyString

VectorComponent = Annotated[float, Field(allow_inf_nan=False)]


class VectorDocument(StrictFrozenDomainModel):
    id: UUID
    subject: SubjectRef
    text: NonEmptyString
    vector: list[VectorComponent] = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class VectorSearchHit(StrictFrozenDomainModel):
    id: UUID
    score: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


@runtime_checkable
class VectorIndex(Protocol):
    index_version: str

    async def upsert(self, documents: Sequence[VectorDocument]) -> None:
        raise NotImplementedError

    async def search(
        self, subject: SubjectRef, query_vector: Sequence[float], limit: int
    ) -> list[VectorSearchHit]:
        raise NotImplementedError

    async def delete_subject(self, subject: SubjectRef) -> None:
        raise NotImplementedError
