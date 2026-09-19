from __future__ import annotations

from collections.abc import Sequence

from personalization_core.public import (
    Entity,
    Event,
    FeatureExtractorRegistry,
    FeatureObservationDraft,
)


class ArticleTopicExtractor:
    name = "article.topic"
    version = "1.0"
    supported_event_types = frozenset({"article.read"})

    async def extract(
        self, event: Event, entity: Entity | None
    ) -> Sequence[FeatureObservationDraft]:
        if entity is None:
            return []
        topics = entity.attributes.get("topics")
        progress = event.properties.get("progress")
        if not isinstance(topics, list) or not isinstance(progress, (int, float)):
            return []
        return [
            FeatureObservationDraft(
                dimension="article_topic",
                value_key=f"article:{topic}",
                value={"topic": topic},
                score=max(0.0, min(1.0, progress)),
                polarity=event.polarity,
                confidence=1.0,
                occurred_at=event.occurred_at,
            )
            for topic in topics
            if isinstance(topic, str) and topic.strip()
        ]


def register_feature_plugins(
    registry: FeatureExtractorRegistry,
) -> FeatureExtractorRegistry:
    registry.register_extractor(ArticleTopicExtractor())
    return registry
