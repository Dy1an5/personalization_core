"""Stable imports for independently distributed domain adapters.

Adapters must depend on this module instead of Core implementation packages.  The
module intentionally contains only generic domain contracts and the embedded
facade; platform-specific concepts belong in the adapter package.
"""

from .application.dto import (
    EventIngestionInput,
    FeatureProcessingResult,
)
from .domain.entities import Entity, EntityCreate
from .domain.enums import EvidenceSourceType, Polarity
from .domain.events import Event, EventCreate
from .domain.evidence import Evidence, EvidenceCreate
from .domain.features import FeatureObservationDraft, FeatureState
from .domain.identifiers import (
    EntityRef,
    Namespace,
    SubjectId,
    SubjectRef,
    TenantId,
)
from .domain.jobs import ProcessingRun
from .domain.types import JsonValue, UtcDatetime
from .plugins.contracts import FeatureAggregator, FeatureExtractor
from .plugins.registry import FeatureExtractorRegistry
from .sdk.async_client import (
    ContextOperations,
    EventOperations,
    FeatureOperations,
    MemoryOperations,
    PersonalizationEngine,
    ProfileOperations,
    SubjectOperations,
    from_components,
)

__all__ = [
    "ContextOperations",
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
    "Namespace",
    "PersonalizationEngine",
    "Polarity",
    "ProcessingRun",
    "ProfileOperations",
    "SubjectId",
    "SubjectOperations",
    "SubjectRef",
    "TenantId",
    "UtcDatetime",
    "from_components",
]
