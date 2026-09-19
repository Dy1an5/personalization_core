from __future__ import annotations

from personalization_core.public import (
    EntityCreate,
    EntityRef,
    EventCreate,
    EventIngestionInput,
    EvidenceCreate,
    EvidenceSourceType,
    Polarity,
    SubjectRef,
)

from .models import Article, ArticleRead

SOURCE = "personalization-article"
SCHEMA_VERSION = "article-adapter-1"


def to_entity(article: Article, subject: SubjectRef) -> EntityCreate:
    return EntityCreate(
        entity_type="article",
        external_id=article.article_id,
        attributes={"topics": list(article.topics)},
        content_text=article.title,
        schema_version=SCHEMA_VERSION,
    )


def to_event_input(read: ArticleRead, subject: SubjectRef) -> EventIngestionInput:
    event_key = f"read:{read.event_id}"
    return EventIngestionInput(
        event=EventCreate(
            event_type="article.read",
            entity=EntityRef(
                subject=subject,
                entity_type="article",
                external_id=read.article.article_id,
            ),
            source=SOURCE,
            idempotency_key=event_key,
            value=read.progress,
            polarity=Polarity.POSITIVE,
            properties={
                "article_id": read.article.article_id,
                "progress": read.progress,
                "adapter_event_id": read.event_id,
            },
            occurred_at=read.occurred_at,
            schema_version=SCHEMA_VERSION,
        ),
        evidence=EvidenceCreate(
            source_type=EvidenceSourceType.IMPORT,
            source_ref=f"article:read:{read.event_id}",
            metadata={
                "adapter": "personalization-article",
                "adapter_event_id": read.event_id,
                "article_id": read.article.article_id,
            },
            occurred_at=read.occurred_at,
        ),
    )
