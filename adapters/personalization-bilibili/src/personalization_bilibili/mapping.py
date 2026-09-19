from __future__ import annotations

from personalization_core.public import (
    EntityCreate,
    EntityRef,
    EventCreate,
    EventIngestionInput,
    EvidenceCreate,
    EvidenceSourceType,
    SubjectRef,
)

from .models import BilibiliVideo, BilibiliWatchEvent

SOURCE = "personalization-bilibili"
SCHEMA_VERSION = "bilibili-adapter-1"


def to_entity(video: BilibiliVideo, subject: SubjectRef) -> EntityCreate:
    return EntityCreate(
        entity_type="video",
        external_id=video.video_id,
        attributes={
            "creator_id": video.creator_id,
            "duration_seconds": video.duration_seconds,
            "topics": list(video.topics),
            "popularity_score": video.popularity_score,
        },
        content_text=video.title,
        schema_version=SCHEMA_VERSION,
    )


def to_event_input(
    watch: BilibiliWatchEvent, subject: SubjectRef
) -> EventIngestionInput:
    event_type = f"bilibili.video.{watch.event_type}"
    event_key = f"watch:{watch.event_id}"
    return EventIngestionInput(
        event=EventCreate(
            event_type=event_type,
            entity=EntityRef(
                subject=subject,
                entity_type="video",
                external_id=watch.video.video_id,
            ),
            source=SOURCE,
            idempotency_key=event_key,
            value=watch.watched_seconds,
            polarity=watch.polarity,
            properties={
                "video_id": watch.video.video_id,
                "watched_seconds": watch.watched_seconds,
                "adapter_event_id": watch.event_id,
            },
            occurred_at=watch.occurred_at,
            schema_version=SCHEMA_VERSION,
        ),
        evidence=EvidenceCreate(
            source_type=EvidenceSourceType.IMPORT,
            source_ref=f"bilibili:watch:{watch.event_id}",
            metadata={
                "adapter": "personalization-bilibili",
                "adapter_event_id": watch.event_id,
                "video_id": watch.video.video_id,
                "event_type": event_type,
            },
            occurred_at=watch.occurred_at,
        ),
    )
