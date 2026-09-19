from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from personalization_article import (
    Article,
    ArticleRead,
)
from personalization_article import (
    register_feature_plugins as register_article_plugins,
)
from personalization_article import (
    to_entity as article_to_entity,
)
from personalization_article import (
    to_event_input as article_to_event_input,
)
from personalization_bilibili import (
    BilibiliWatchEvent,
)
from personalization_bilibili import (
    register_feature_plugins as register_bilibili_plugins,
)
from personalization_bilibili import (
    to_entity as bilibili_to_entity,
)
from personalization_bilibili import (
    to_event_input as bilibili_to_event_input,
)

from personalization_core.infrastructure.persistence.sqlalchemy_models import Base
from personalization_core.public import (
    FeatureExtractorRegistry,
    Namespace,
    PersonalizationEngine,
    SubjectId,
    SubjectRef,
    TenantId,
)
from tests.fixtures.fakes import FakeClock
from tests.fixtures.in_memory import InMemoryUnitOfWorkFactory

NOW = datetime(2026, 9, 19, 4, 5, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures/anonymous_watch.json"


def scoped_subject(namespace: str) -> SubjectRef:
    return SubjectRef(
        tenant_id=TenantId("tenant-anon"),
        namespace=Namespace(namespace),
        subject_id=SubjectId("subject-anon"),
    )


def bilibili_sample() -> BilibiliWatchEvent:
    return BilibiliWatchEvent.model_validate(
        json.loads(FIXTURE.read_text(encoding="utf-8"))
    )


@pytest.mark.asyncio
async def test_two_adapters_share_one_engine_without_cross_talk() -> None:
    bilibili_subject = scoped_subject("bilibili")
    article_subject = scoped_subject("article")
    watch = bilibili_sample()
    read = ArticleRead(
        article=Article(
            article_id="article-anon-003",
            title="匿名数据工程文章",
            topics=["data", "python"],
        ),
        event_id="read-anon-003",
        occurred_at=NOW,
        progress=0.75,
    )

    registry = FeatureExtractorRegistry.with_builtins()
    register_bilibili_plugins(registry)
    register_article_plugins(registry)
    factory = InMemoryUnitOfWorkFactory()
    engine = PersonalizationEngine.from_components(
        uow_factory=factory,
        clock=FakeClock(NOW),
        feature_registry=registry,
    )

    await engine.events.upsert_entity(
        bilibili_subject, bilibili_to_entity(watch.video, bilibili_subject)
    )
    await engine.events.upsert_entity(
        article_subject, article_to_entity(read.article, article_subject)
    )
    bilibili_input = bilibili_to_event_input(watch, bilibili_subject)
    article_input = article_to_event_input(read, article_subject)
    bilibili_first = await engine.events.ingest_event(bilibili_subject, bilibili_input)
    article_first = await engine.events.ingest_event(article_subject, article_input)
    assert (
        await engine.events.ingest_event(bilibili_subject, bilibili_input)
    ).status.value == "replayed"
    assert (
        await engine.events.ingest_event(article_subject, article_input)
    ).status.value == "replayed"

    bilibili_processed = await engine.features.process_event(
        bilibili_subject, bilibili_first.event.id
    )
    article_processed = await engine.features.process_event(
        article_subject, article_first.event.id
    )
    bilibili_replay = await engine.features.process_event(
        bilibili_subject, bilibili_first.event.id
    )
    article_replay = await engine.features.process_event(
        article_subject, article_first.event.id
    )

    assert bilibili_processed.created_observation_count == 5
    assert article_processed.created_observation_count == 2
    assert bilibili_replay.created_observation_count == 0
    assert article_replay.created_observation_count == 0
    assert bilibili_replay.replayed_observation_count == 5
    assert article_replay.replayed_observation_count == 2

    observations = list(factory.store.observations.values())
    bilibili_observations = [
        item for item in observations if item.subject == bilibili_subject
    ]
    article_observations = [
        item for item in observations if item.subject == article_subject
    ]
    assert len(bilibili_observations) == 5
    assert len(article_observations) == 2
    assert {item.dimension for item in bilibili_observations} == {
        "creator",
        "duration",
        "popularity",
        "topic",
    }
    assert {item.dimension for item in article_observations} == {"article_topic"}
    assert all(item.subject == bilibili_subject for item in bilibili_observations)
    assert all(item.subject == article_subject for item in article_observations)

    bilibili_states = await engine.features.list_states(bilibili_subject)
    article_states = await engine.features.list_states(article_subject)
    assert all(item.subject == bilibili_subject for item in bilibili_states)
    assert all(item.subject == article_subject for item in article_states)
    assert {(item.dimension, item.value_key) for item in bilibili_states} == {
        ("creator", "creator:creator-anon-007"),
        ("duration", "medium"),
        ("popularity", "high"),
        ("topic", "topic:data"),
        ("topic", "topic:python"),
    }
    assert {(item.dimension, item.value_key) for item in article_states} == {
        ("article_topic", "article:data"),
        ("article_topic", "article:python"),
    }
    assert not any(item.dimension == "article_topic" for item in bilibili_states)
    assert not any(item.dimension == "topic" for item in article_states)

    bilibili_profile = await engine.profiles.refresh(bilibili_subject)
    article_profile = await engine.profiles.refresh(article_subject)
    assert bilibili_profile.subject == bilibili_subject
    assert article_profile.subject == article_subject
    assert {
        (item.dimension, item.value_key) for item in bilibili_profile.preferences
    } == {
        ("creator", "creator:creator-anon-007"),
        ("duration", "medium"),
        ("popularity", "high"),
        ("topic", "topic:data"),
        ("topic", "topic:python"),
    }
    assert {
        (item.dimension, item.value_key) for item in article_profile.preferences
    } == {
        ("article_topic", "article:data"),
        ("article_topic", "article:python"),
    }
    await engine.close()


EXPECTED_MIGRATION_FILES = {
    "0001_initial.py",
    "0002_privacy_audit.py",
}
EXPECTED_TABLE_COLUMNS = {
    "subjects": (
        "id",
        "tenant_id",
        "namespace",
        "external_subject_id",
        "metadata",
        "created_at",
        "updated_at",
        "deleted_at",
    ),
    "entities": (
        "id",
        "subject_pk",
        "entity_type",
        "external_id",
        "attributes",
        "content_text",
        "content_hash",
        "schema_version",
        "first_seen_at",
        "last_seen_at",
        "deleted_at",
    ),
    "events": (
        "id",
        "subject_pk",
        "event_type",
        "entity_type",
        "entity_external_id",
        "source",
        "idempotency_key",
        "value",
        "polarity",
        "properties",
        "occurred_at",
        "observed_at",
        "schema_version",
    ),
    "evidence": (
        "id",
        "subject_pk",
        "source_type",
        "source_ref",
        "event_id",
        "excerpt",
        "metadata",
        "occurred_at",
        "created_at",
    ),
    "memories": (
        "id",
        "subject_pk",
        "key",
        "kind",
        "content",
        "structured_value",
        "target_dimension",
        "target_value_key",
        "authority",
        "polarity",
        "scope",
        "scope_value",
        "scope_key",
        "confidence",
        "state",
        "valid_from",
        "valid_until",
        "evidence_count",
        "revision",
        "created_at",
        "updated_at",
        "deleted_at",
    ),
    "memory_evidence": ("memory_id", "evidence_id"),
    "memory_revisions": (
        "id",
        "subject_pk",
        "memory_id",
        "revision",
        "snapshot",
        "actor",
        "reason",
        "transition",
        "created_at",
    ),
    "feature_observations": (
        "id",
        "subject_pk",
        "dimension",
        "value_key",
        "value",
        "score",
        "polarity",
        "confidence",
        "occurred_at",
        "source_event_id",
        "evidence_id",
        "extractor_name",
        "extractor_version",
        "created_at",
    ),
    "feature_states": (
        "id",
        "subject_pk",
        "dimension",
        "value_key",
        "value",
        "long_term_score",
        "short_term_score",
        "confidence",
        "positive_evidence_count",
        "negative_evidence_count",
        "neutral_evidence_count",
        "first_evidence_at",
        "last_evidence_at",
        "aggregator_name",
        "algorithm_version",
        "updated_at",
    ),
    "feature_state_evidence": ("feature_state_id", "evidence_id"),
    "profile_snapshots": (
        "id",
        "subject_pk",
        "version",
        "status",
        "generated_at",
        "algorithm_version",
        "source_watermark",
        "coverage",
        "preferences",
        "warnings",
    ),
    "processing_runs": (
        "id",
        "subject_pk",
        "operation",
        "status",
        "algorithm_version",
        "started_at",
        "finished_at",
        "processed_count",
        "failed_count",
        "error_code",
    ),
    "audit_log": ("id", "subject_pk", "action", "occurred_at", "metadata"),
    "purge_audit_log": (
        "id",
        "scope_digest",
        "occurred_at",
        "action",
        "metadata",
    ),
}


def test_phase18_schema_and_migration_snapshot_is_unchanged() -> None:
    migration_dir = REPOSITORY_ROOT / "migrations/versions"
    migration_files = {
        path.name for path in migration_dir.glob("*.py") if path.name != "__init__.py"
    }
    assert migration_files == EXPECTED_MIGRATION_FILES
    assert (migration_dir / "0001_initial.py").read_text(encoding="utf-8").count(
        'revision = "0001_initial"'
    ) == 1
    assert (migration_dir / "0002_privacy_audit.py").read_text(encoding="utf-8").count(
        'revision = "0002_privacy_audit"'
    ) == 1

    assert set(Base.metadata.tables) == set(EXPECTED_TABLE_COLUMNS)
    for table_name, expected_columns in EXPECTED_TABLE_COLUMNS.items():
        actual_columns = tuple(
            column.name for column in Base.metadata.tables[table_name].columns
        )
        assert actual_columns == expected_columns
        assert not {
            "bvid",
            "cid",
            "creator_id",
            "popularity_score",
        } & set(actual_columns)

    migration_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(migration_dir.glob("*.py"))
    ).lower()
    assert "bvid" not in migration_text
    assert "cid" not in migration_text
