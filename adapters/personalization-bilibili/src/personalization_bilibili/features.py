from __future__ import annotations

from collections.abc import Sequence

from personalization_core.public import (
    Entity,
    Event,
    FeatureExtractorRegistry,
    FeatureObservationDraft,
)

EVENT_TYPES = frozenset(
    {
        "bilibili.video.viewed",
        "bilibili.video.liked",
        "bilibili.video.completed",
    }
)


def _score(event: Event) -> float:
    if event.value is not None:
        return max(-1.0, min(1.0, abs(event.value)))
    return 1.0


def _confidence(event: Event) -> float:
    return 1.0 if event.value is not None else 0.8


class CreatorExtractor:
    name = "bilibili.creator"
    version = "1.0"
    supported_event_types = EVENT_TYPES

    async def extract(
        self, event: Event, entity: Entity | None
    ) -> Sequence[FeatureObservationDraft]:
        if entity is None:
            return []
        creator_id = entity.attributes.get("creator_id")
        if not isinstance(creator_id, str) or not creator_id.strip():
            return []
        return [
            FeatureObservationDraft(
                dimension="creator",
                value_key=f"creator:{creator_id}",
                value={"creator_id": creator_id},
                score=_score(event),
                polarity=event.polarity,
                confidence=_confidence(event),
                occurred_at=event.occurred_at,
            )
        ]


class DurationExtractor:
    name = "bilibili.duration"
    version = "1.0"
    supported_event_types = EVENT_TYPES

    async def extract(
        self, event: Event, entity: Entity | None
    ) -> Sequence[FeatureObservationDraft]:
        if entity is None:
            return []
        duration = entity.attributes.get("duration_seconds")
        watched = event.properties.get("watched_seconds")
        if not isinstance(duration, (int, float)) or not isinstance(
            watched, (int, float)
        ):
            return []
        if duration < 0 or watched < 0:
            return []
        if duration <= 300:
            bucket = "short"
        elif duration <= 900:
            bucket = "medium"
        else:
            bucket = "long"
        completion = 1.0 if duration == 0 else min(1.0, watched / duration)
        return [
            FeatureObservationDraft(
                dimension="duration",
                value_key=bucket,
                value={
                    "bucket": bucket,
                    "duration_seconds": duration,
                    "watched_seconds": watched,
                },
                score=completion,
                polarity=event.polarity,
                confidence=1.0,
                occurred_at=event.occurred_at,
            )
        ]


class TopicExtractor:
    name = "bilibili.topic"
    version = "1.0"
    supported_event_types = EVENT_TYPES

    async def extract(
        self, event: Event, entity: Entity | None
    ) -> Sequence[FeatureObservationDraft]:
        if entity is None:
            return []
        topics = entity.attributes.get("topics")
        if not isinstance(topics, list):
            return []
        return [
            FeatureObservationDraft(
                dimension="topic",
                value_key=f"topic:{topic}",
                value={"topic": topic},
                score=_score(event),
                polarity=event.polarity,
                confidence=_confidence(event),
                occurred_at=event.occurred_at,
            )
            for topic in topics
            if isinstance(topic, str) and topic.strip()
        ]


class PopularityExtractor:
    name = "bilibili.popularity"
    version = "1.0"
    supported_event_types = EVENT_TYPES

    async def extract(
        self, event: Event, entity: Entity | None
    ) -> Sequence[FeatureObservationDraft]:
        if entity is None:
            return []
        raw_score = entity.attributes.get("popularity_score")
        if not isinstance(raw_score, (int, float)) or not 0 <= raw_score <= 1:
            return []
        if raw_score < 1 / 3:
            bucket = "low"
        elif raw_score < 2 / 3:
            bucket = "medium"
        else:
            bucket = "high"
        return [
            FeatureObservationDraft(
                dimension="popularity",
                value_key=bucket,
                value={"bucket": bucket, "popularity_score": raw_score},
                score=_score(event),
                polarity=event.polarity,
                confidence=1.0,
                occurred_at=event.occurred_at,
            )
        ]


def register_feature_plugins(
    registry: FeatureExtractorRegistry,
) -> FeatureExtractorRegistry:
    for extractor in (
        CreatorExtractor(),
        DurationExtractor(),
        TopicExtractor(),
        PopularityExtractor(),
    ):
        registry.register_extractor(extractor)
    return registry
