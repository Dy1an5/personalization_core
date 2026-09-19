from __future__ import annotations

import inspect
from collections.abc import Sequence
from datetime import datetime
from typing import get_type_hints

import personalization_core.public as public


EXPECTED_PUBLIC_API_VERSION = "0.1.0"
EXPECTED_PUBLIC_EXPORTS = (
    "ContextOperations",
    "ContextRequest",
    "Entity",
    "EntityCreate",
    "EntityRef",
    "Event",
    "EventCreate",
    "EventIngestionInput",
    "EventOperations",
    "Evidence",
    "EvidenceCreate",
    "EvidenceSourceType",
    "FeatureAggregator",
    "FeatureExtractor",
    "FeatureExtractorRegistry",
    "FeatureObservationDraft",
    "FeatureOperations",
    "FeatureProcessingResult",
    "FeatureState",
    "JsonValue",
    "MemoryOperations",
    "MemoryCreateInput",
    "MemoryKind",
    "Namespace",
    "PersonalizationEngine",
    "Polarity",
    "PreferenceTarget",
    "PUBLIC_API_VERSION",
    "ProcessingRun",
    "ProfileOperations",
    "SubjectId",
    "SubjectOperations",
    "SubjectRef",
    "TenantId",
    "UtcDatetime",
    "from_components",
)


def test_public_export_snapshot_and_version_are_frozen() -> None:
    assert tuple(public.__all__) == EXPECTED_PUBLIC_EXPORTS
    assert public.PUBLIC_API_EXPORTS == EXPECTED_PUBLIC_EXPORTS
    assert public.PUBLIC_API_VERSION == EXPECTED_PUBLIC_API_VERSION


def test_public_does_not_export_internal_module_names() -> None:
    assert all(not name.startswith("_") for name in public.__all__)
    assert "EventService" not in public.__all__
    assert "Base" not in public.__all__


def test_feature_extractor_protocol_signature_is_frozen() -> None:
    method = public.FeatureExtractor.extract
    assert str(inspect.signature(method)) == (
        "(self, event: 'Event', entity: 'Entity | None') -> "
        "'Sequence[FeatureObservationDraft]'"
    )
    hints = get_type_hints(method)
    assert tuple(hints) == ("event", "entity", "return")
    assert hints["return"] == Sequence[public.FeatureObservationDraft]


def test_feature_aggregator_protocol_signature_is_frozen() -> None:
    method = public.FeatureAggregator.aggregate
    assert str(inspect.signature(method)) == (
        "(self, observations: 'Sequence[FeatureObservation]', now: 'datetime') -> "
        "'FeatureStateDraft'"
    )
    hints = get_type_hints(method)
    assert tuple(hints) == ("observations", "now", "return")
    assert hints["now"] is datetime
