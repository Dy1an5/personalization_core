"""Stable imports for independently distributed domain adapters.

Adapters must depend on this module instead of Core implementation packages.  The
module intentionally contains only generic domain contracts and the embedded
facade; platform-specific concepts belong in the adapter package.
"""

from .application.dto import (
    EventIngestionInput,
    FeatureProcessingResult,
    MemoryCreateInput,
)
from .domain.context import ContextRequest
from .domain.entities import Entity, EntityCreate
from .domain.enums import EvidenceSourceType, MemoryKind, Polarity
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
from .domain.memory import PreferenceTarget
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

PUBLIC_API_VERSION = "0.1.0"

__all__ = [
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
]

# This tuple is intentionally derived once from the frozen ``__all__`` list.
# It gives release tooling a data-only export snapshot without making internal
# modules part of the adapter contract.
PUBLIC_API_EXPORTS = tuple(__all__)
