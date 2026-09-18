from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from personalization_core.domain.enums import Polarity
from personalization_core.domain.features import FeatureObservation, FeatureStateDraft


class FrequencyAggregator:
    name = "frequency"
    version = "1.0"

    def __init__(self, dimension: str = "*", recent_count: int = 10) -> None:
        if not dimension.strip():
            raise ValueError("dimension must not be blank")
        if recent_count < 1:
            raise ValueError("recent_count must be positive")
        self.dimension = dimension
        self.recent_count = recent_count

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
        recent = ordered[-self.recent_count :]
        signed_scores = [_signed_score(item) for item in ordered]
        recent_scores = [_signed_score(item) for item in recent]
        counts = _counts(ordered)
        latest = ordered[-1]
        return FeatureStateDraft(
            dimension=latest.dimension,
            value_key=latest.value_key,
            value=dict(latest.value),
            long_term_score=_average(signed_scores),
            short_term_score=_average(recent_scores),
            confidence=_confidence(
                len(ordered), counts, latest.occurred_at, now, timedelta(days=30)
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


def _counts(observations: Sequence[FeatureObservation]) -> tuple[int, int, int]:
    positive = sum(item.polarity is Polarity.POSITIVE for item in observations)
    negative = sum(item.polarity is Polarity.NEGATIVE for item in observations)
    neutral = len(observations) - positive - negative
    return positive, negative, neutral


def _average(scores: Sequence[float]) -> float:
    return sum(scores) / len(scores)


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
    age = max(0.0, (now - latest_at).total_seconds())
    freshness = math.exp(-age / freshness_window.total_seconds())
    return min(1.0, max(0.0, sample_factor * consistency * freshness))
