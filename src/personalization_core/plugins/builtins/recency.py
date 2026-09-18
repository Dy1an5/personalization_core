from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from personalization_core.domain.enums import Polarity
from personalization_core.domain.features import FeatureObservation, FeatureStateDraft


class RecencyDecayAggregator:
    name = "recency_decay"
    version = "1.0"

    def __init__(
        self,
        dimension: str = "*",
        short_half_life: timedelta = timedelta(days=7),
        long_half_life: timedelta = timedelta(days=30),
    ) -> None:
        if not dimension.strip():
            raise ValueError("dimension must not be blank")
        if short_half_life.total_seconds() <= 0:
            raise ValueError("short_half_life must be positive")
        if long_half_life.total_seconds() <= 0:
            raise ValueError("long_half_life must be positive")
        self.dimension = dimension
        self.short_half_life = short_half_life
        self.long_half_life = long_half_life

    def aggregate(
        self,
        observations: Sequence[FeatureObservation],
        now: datetime,
    ) -> FeatureStateDraft:
        if not observations:
            raise ValueError("cannot aggregate an empty observation sequence")

        ordered = sorted(
            observations, key=lambda item: (item.occurred_at, str(item.id))
        )
        latest = ordered[-1]
        counts = _counts(ordered)
        return FeatureStateDraft(
            dimension=latest.dimension,
            value_key=latest.value_key,
            value=dict(latest.value),
            long_term_score=_weighted_average(ordered, now, self.long_half_life),
            short_term_score=_weighted_average(ordered, now, self.short_half_life),
            confidence=_confidence(
                len(ordered), counts, latest.occurred_at, now, self.long_half_life
            ),
            positive_evidence_count=counts[0],
            negative_evidence_count=counts[1],
            neutral_evidence_count=counts[2],
            first_evidence_at=ordered[0].occurred_at,
            last_evidence_at=latest.occurred_at,
            evidence_ids=_unique_evidence_ids(ordered),
        )


def _signed_score(observation: FeatureObservation) -> float:
    if observation.polarity is Polarity.POSITIVE:
        return abs(observation.score)
    if observation.polarity is Polarity.NEGATIVE:
        return -abs(observation.score)
    return observation.score


def _age_seconds(observed_at: datetime, now: datetime) -> float:
    return max(0.0, (now - observed_at).total_seconds())


def _weighted_average(
    observations: Sequence[FeatureObservation],
    now: datetime,
    half_life: timedelta,
) -> float:
    half_life_seconds = half_life.total_seconds()
    weights = [
        math.exp(-math.log(2) * _age_seconds(item.occurred_at, now) / half_life_seconds)
        for item in observations
    ]
    weighted_total = sum(
        weight * _signed_score(item)
        for item, weight in zip(observations, weights, strict=True)
    )
    return weighted_total / sum(weights)


def _counts(observations: Sequence[FeatureObservation]) -> tuple[int, int, int]:
    positive = sum(item.polarity is Polarity.POSITIVE for item in observations)
    negative = sum(item.polarity is Polarity.NEGATIVE for item in observations)
    neutral = len(observations) - positive - negative
    return positive, negative, neutral


def _unique_evidence_ids(observations: Sequence[FeatureObservation]) -> list[UUID]:
    seen: set[UUID] = set()
    result: list[UUID] = []
    for observation in observations:
        if observation.evidence_id not in seen:
            seen.add(observation.evidence_id)
            result.append(observation.evidence_id)
    return result


def _confidence(
    observation_count: int,
    counts: tuple[int, int, int],
    latest_at: datetime,
    now: datetime,
    freshness_window: timedelta,
) -> float:
    sample_factor = min(1.0, observation_count / 5)
    consistency = max(counts) / observation_count
    freshness = math.exp(
        -_age_seconds(latest_at, now) / freshness_window.total_seconds()
    )
    return min(1.0, max(0.0, sample_factor * consistency * freshness))
