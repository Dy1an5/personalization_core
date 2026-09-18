"""Asynchronous persistence contracts for the application layer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from personalization_core.domain.entities import Entity
from personalization_core.domain.enums import MemoryState
from personalization_core.domain.events import Event
from personalization_core.domain.evidence import Evidence
from personalization_core.domain.features import FeatureObservation, FeatureState
from personalization_core.domain.identifiers import EntityRef, SubjectRef
from personalization_core.domain.jobs import ProcessingRun
from personalization_core.domain.memory import MemoryRecord
from personalization_core.domain.profile import ProfileSnapshot
from personalization_core.domain.subjects import Subject


@dataclass(frozen=True, slots=True)
class Page:
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if self.offset < 0:
            raise ValueError("offset must be non-negative")


@dataclass(frozen=True, slots=True)
class EventFilter:
    event_type: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryFilter:
    states: frozenset[MemoryState] | None = None
    key: str | None = None


@dataclass(frozen=True, slots=True)
class FeatureStateFilter:
    dimension: str | None = None


@runtime_checkable
class SubjectRepository(Protocol):
    async def get_by_ref(self, ref: SubjectRef) -> Subject | None:
        raise NotImplementedError

    async def get(self, ref: SubjectRef, subject_id: UUID) -> Subject | None:
        raise NotImplementedError

    async def add(self, subject: Subject) -> None:
        raise NotImplementedError

    async def update(self, subject: Subject) -> None:
        raise NotImplementedError


@runtime_checkable
class EntityRepository(Protocol):
    async def get(self, subject: SubjectRef, entity_id: UUID) -> Entity | None:
        raise NotImplementedError

    async def get_by_ref(self, ref: EntityRef) -> Entity | None:
        raise NotImplementedError

    async def add(self, subject: SubjectRef, entity: Entity) -> None:
        raise NotImplementedError

    async def update(self, subject: SubjectRef, entity: Entity) -> None:
        raise NotImplementedError

    async def list(self, subject: SubjectRef, page: Page) -> Sequence[Entity]:
        raise NotImplementedError


@runtime_checkable
class EventRepository(Protocol):
    async def get(self, subject: SubjectRef, event_id: UUID) -> Event | None:
        raise NotImplementedError

    async def get_by_idempotency_key(
        self, subject: SubjectRef, source: str, idempotency_key: str
    ) -> Event | None:
        raise NotImplementedError

    async def add(self, subject: SubjectRef, event: Event) -> None:
        raise NotImplementedError

    async def list(
        self, subject: SubjectRef, filters: EventFilter, page: Page
    ) -> Sequence[Event]:
        raise NotImplementedError


@runtime_checkable
class EvidenceRepository(Protocol):
    async def get(self, subject: SubjectRef, evidence_id: UUID) -> Evidence | None:
        raise NotImplementedError

    async def get_by_source(
        self, subject: SubjectRef, source_type: str, source_ref: str
    ) -> Evidence | None:
        raise NotImplementedError

    async def add(self, subject: SubjectRef, evidence: Evidence) -> None:
        raise NotImplementedError

    async def list_for_event(
        self, subject: SubjectRef, event_id: UUID
    ) -> Sequence[Evidence]:
        raise NotImplementedError


@runtime_checkable
class MemoryRepository(Protocol):
    async def get(self, subject: SubjectRef, memory_id: UUID) -> MemoryRecord | None:
        raise NotImplementedError

    async def add(self, subject: SubjectRef, memory: MemoryRecord) -> None:
        raise NotImplementedError

    async def update(
        self, subject: SubjectRef, memory: MemoryRecord, expected_revision: int
    ) -> None:
        raise NotImplementedError

    async def list(
        self, subject: SubjectRef, filters: MemoryFilter, page: Page
    ) -> Sequence[MemoryRecord]:
        raise NotImplementedError

    async def bind_evidence(
        self, subject: SubjectRef, memory_id: UUID, evidence_id: UUID
    ) -> None:
        raise NotImplementedError

    async def list_evidence_ids(
        self, subject: SubjectRef, memory_id: UUID
    ) -> Sequence[UUID]:
        raise NotImplementedError


@runtime_checkable
class FeatureRepository(Protocol):
    async def get_observation(
        self, subject: SubjectRef, observation_id: UUID
    ) -> FeatureObservation | None:
        raise NotImplementedError

    async def add_observation(
        self, subject: SubjectRef, observation: FeatureObservation
    ) -> None:
        raise NotImplementedError

    async def list_observations(
        self, subject: SubjectRef, dimension: str | None = None
    ) -> Sequence[FeatureObservation]:
        raise NotImplementedError

    async def get_state(
        self, subject: SubjectRef, dimension: str, value_key: str, aggregator_name: str
    ) -> FeatureState | None:
        raise NotImplementedError

    async def upsert_state(self, subject: SubjectRef, state: FeatureState) -> None:
        raise NotImplementedError

    async def list_states(
        self, subject: SubjectRef, filters: FeatureStateFilter
    ) -> Sequence[FeatureState]:
        raise NotImplementedError


@runtime_checkable
class ProfileRepository(Protocol):
    async def add(self, subject: SubjectRef, snapshot: ProfileSnapshot) -> None:
        raise NotImplementedError

    async def get_version(
        self, subject: SubjectRef, version: int
    ) -> ProfileSnapshot | None:
        raise NotImplementedError

    async def get_latest(self, subject: SubjectRef) -> ProfileSnapshot | None:
        raise NotImplementedError

    async def list(self, subject: SubjectRef, page: Page) -> Sequence[ProfileSnapshot]:
        raise NotImplementedError


@runtime_checkable
class ProcessingRunRepository(Protocol):
    async def get(self, subject: SubjectRef, run_id: UUID) -> ProcessingRun | None:
        raise NotImplementedError

    async def add(self, subject: SubjectRef, run: ProcessingRun) -> None:
        raise NotImplementedError

    async def update(self, subject: SubjectRef, run: ProcessingRun) -> None:
        raise NotImplementedError

    async def list(self, subject: SubjectRef, page: Page) -> Sequence[ProcessingRun]:
        raise NotImplementedError
