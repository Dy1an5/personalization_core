from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import Field

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.types import NonEmptyString


class RerankCandidate(StrictFrozenDomainModel):
    id: UUID
    text: NonEmptyString


class RerankResult(StrictFrozenDomainModel):
    id: UUID
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


@runtime_checkable
class Reranker(Protocol):
    name: str

    async def rerank(
        self, query: str, candidates: Sequence[RerankCandidate], limit: int
    ) -> list[RerankResult]:
        raise NotImplementedError
