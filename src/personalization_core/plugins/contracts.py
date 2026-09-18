from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from personalization_core.domain.entities import Entity
from personalization_core.domain.events import Event
from personalization_core.domain.features import (
    FeatureObservation,
    FeatureObservationDraft,
    FeatureStateDraft,
)


class FeatureExtractor(Protocol):
    name: str
    version: str
    supported_event_types: frozenset[str]

    async def extract(
        self,
        event: Event,
        entity: Entity | None,
    ) -> Sequence[FeatureObservationDraft]:
        raise NotImplementedError


class FeatureAggregator(Protocol):
    name: str
    version: str
    dimension: str

    def aggregate(
        self,
        observations: Sequence[FeatureObservation],
        now: datetime,
    ) -> FeatureStateDraft:
        raise NotImplementedError
