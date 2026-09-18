from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.entities import Entity
from personalization_core.domain.types import JsonValue, NonEmptyString


class SemanticAttribute(StrictFrozenDomainModel):
    key: NonEmptyString
    value: JsonValue
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


@runtime_checkable
class SemanticEnricher(Protocol):
    name: str
    version: str

    async def enrich(self, entity: Entity) -> list[SemanticAttribute]:
        raise NotImplementedError
