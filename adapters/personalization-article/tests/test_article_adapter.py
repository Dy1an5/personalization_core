from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from personalization_article import (
    Article,
    ArticleRead,
    register_feature_plugins,
    to_entity,
    to_event_input,
)
from pydantic import ValidationError

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

FIXTURE = Path(__file__).parent / "fixtures/anonymous_read.json"
NOW = datetime(2026, 9, 19, 4, 5, tzinfo=UTC)


def subject() -> SubjectRef:
    return SubjectRef(
        tenant_id=TenantId("tenant-anon"),
        namespace=Namespace("article"),
        subject_id=SubjectId("subject-anon"),
    )


def sample() -> ArticleRead:
    return ArticleRead.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_article_mapping_and_validation() -> None:
    read = sample()
    ref = subject()
    entity = to_entity(read.article, ref)
    incoming = to_event_input(read, ref)

    assert entity.entity_type == "article"
    assert entity.external_id == "article-anon-003"
    assert incoming.event.event_type == "article.read"
    assert incoming.event.entity is not None
    assert incoming.event.entity.subject == ref
    assert incoming.event.properties["progress"] == 0.75
    assert incoming.evidence is not None
    assert incoming.evidence.source_ref == "article:read:read-anon-003"

    with pytest.raises(ValidationError):
        ArticleRead(
            article=Article(article_id="a", title="A"),
            event_id="r",
            occurred_at=NOW,
            progress=1.1,
        )


@pytest.mark.asyncio
async def test_article_feature_isolated_from_bilibili_dimensions() -> None:
    ref = subject()
    read = sample()
    registry = FeatureExtractorRegistry.with_builtins()
    register_feature_plugins(registry)
    factory = InMemoryUnitOfWorkFactory()
    engine = PersonalizationEngine.from_components(
        uow_factory=factory,
        clock=FakeClock(NOW),
        feature_registry=registry,
    )

    await engine.events.upsert_entity(ref, to_entity(read.article, ref))
    ingested = await engine.events.ingest_event(ref, to_event_input(read, ref))
    await engine.features.process_event(ref, ingested.event.id)
    states = await engine.features.list_states(ref)

    assert {(state.dimension, state.value_key) for state in states} == {
        ("article_topic", "article:data"),
        ("article_topic", "article:python"),
    }
    assert all(
        state.dimension != "topic" and not state.value_key.startswith("topic:")
        for state in states
    )
    await engine.close()


def test_article_adapter_only_imports_public_core() -> None:
    source_root = Path(__file__).parents[1] / "src"
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module is not None
                if node.module.startswith("personalization_core"):
                    assert node.module == "personalization_core.public"
