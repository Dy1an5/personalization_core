from __future__ import annotations

import ast
import builtins
import importlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from personalization_bilibili import (
    BilibiliVideo,
    BilibiliWatchEvent,
    to_entity,
    to_event_input,
)
from personalization_bilibili.features import (
    CreatorExtractor,
    DurationExtractor,
    PopularityExtractor,
    TopicExtractor,
    register_feature_plugins,
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

FIXTURE = Path(__file__).parent / "fixtures/anonymous_watch.json"
NOW = datetime(2026, 9, 19, 4, tzinfo=UTC)


def subject(namespace: str = "bilibili") -> SubjectRef:
    return SubjectRef(
        tenant_id=TenantId("tenant-anon"),
        namespace=Namespace(namespace),
        subject_id=SubjectId("subject-anon"),
    )


def sample() -> BilibiliWatchEvent:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return BilibiliWatchEvent.model_validate(payload)


def test_mapping_preserves_scope_utc_idempotency_and_evidence() -> None:
    watch = sample()
    ref = subject()
    entity = to_entity(watch.video, ref)
    incoming = to_event_input(watch, ref)

    assert entity.entity_type == "video"
    assert entity.external_id == watch.video.video_id
    assert incoming.event.entity is not None
    assert incoming.event.entity.subject == ref
    assert incoming.event.occurred_at.tzinfo is UTC
    assert incoming.event.idempotency_key == "watch:watch-anon-001"
    assert incoming.evidence is not None
    assert incoming.evidence.source_ref == "bilibili:watch:watch-anon-001"
    assert incoming.evidence.metadata["adapter"] == "personalization-bilibili"


def test_input_validation_rejects_invalid_platform_data() -> None:
    with pytest.raises(ValidationError):
        BilibiliVideo(
            video_id="",
            title="title",
            creator_id="creator",
            duration_seconds=-1,
            popularity_score=2,
        )
    with pytest.raises(ValidationError):
        BilibiliWatchEvent(
            video=sample().video,
            event_id="event",
            event_type="viewed",
            occurred_at=datetime(2026, 9, 19, 4),
            watched_seconds=1,
        )


@pytest.mark.asyncio
async def test_four_extractors_flow_to_feature_state_and_profile() -> None:
    ref = subject()
    watch = sample()
    registry = FeatureExtractorRegistry.with_builtins()
    register_feature_plugins(registry)
    factory = InMemoryUnitOfWorkFactory()
    engine = PersonalizationEngine.from_components(
        uow_factory=factory,
        clock=FakeClock(NOW),
        feature_registry=registry,
    )

    entity = await engine.events.upsert_entity(ref, to_entity(watch.video, ref))
    ingested = await engine.events.ingest_event(ref, to_event_input(watch, ref))
    result = await engine.features.process_event(ref, ingested.event.id)
    replay = await engine.features.process_event(ref, ingested.event.id)

    assert result.created_observation_count == 5
    assert replay.created_observation_count == 0
    assert replay.replayed_observation_count == 5
    assert entity.external_id == watch.video.video_id
    states = await engine.features.list_states(ref)
    assert {(state.dimension, state.value_key) for state in states} == {
        ("creator", "creator:creator-anon-007"),
        ("duration", "medium"),
        ("popularity", "high"),
        ("topic", "topic:data"),
        ("topic", "topic:python"),
    }
    assert all(state.evidence_ids for state in states)
    profile = await engine.profiles.refresh(ref)
    assert {item.dimension for item in profile.preferences} == {
        "creator",
        "duration",
        "popularity",
        "topic",
    }
    await engine.close()


def test_feature_registration_is_explicit() -> None:
    registry = FeatureExtractorRegistry.with_builtins()
    register_feature_plugins(registry)
    assert {
        type(item) for item in registry.extractors_for("bilibili.video.viewed")
    } == {
        CreatorExtractor,
        DurationExtractor,
        PopularityExtractor,
        TopicExtractor,
    }


def test_adapter_production_imports_are_allowlisted_and_isolated() -> None:
    allowed = {
        "pydantic",
        "personalization_core",
        "typing",
        "collections",
        "__future__",
    }
    source_root = Path(__file__).parents[1] / "src"
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
                assert names <= allowed, (path, names - allowed)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module is not None
                top_level = node.module.split(".")[0]
                assert top_level in allowed, (path, top_level)
                if top_level == "personalization_core":
                    assert node.module == "personalization_core.public"

    original_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith(
            (
                "personalization_core.domain",
                "personalization_core.application",
                "personalization_core.infrastructure",
            )
        ):
            raise AssertionError(f"internal Core import blocked: {name}")
        return original_import(name, *args, **kwargs)

    builtins.__import__ = blocked_import
    try:
        importlib.reload(importlib.import_module("personalization_bilibili"))
    finally:
        builtins.__import__ = original_import
