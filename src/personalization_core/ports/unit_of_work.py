from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, runtime_checkable

from .repositories import (
    EntityRepository,
    EventRepository,
    EvidenceRepository,
    FeatureRepository,
    MemoryRepository,
    MemoryRevisionRepository,
    ProcessingRunRepository,
    ProfileRepository,
    SubjectRepository,
)


@runtime_checkable
class UnitOfWork(Protocol):
    @property
    def subjects(self) -> SubjectRepository:
        raise NotImplementedError

    @property
    def entities(self) -> EntityRepository:
        raise NotImplementedError

    @property
    def events(self) -> EventRepository:
        raise NotImplementedError

    @property
    def evidence(self) -> EvidenceRepository:
        raise NotImplementedError

    @property
    def memories(self) -> MemoryRepository:
        raise NotImplementedError

    @property
    def memory_revisions(self) -> MemoryRevisionRepository:
        raise NotImplementedError

    @property
    def features(self) -> FeatureRepository:
        raise NotImplementedError

    @property
    def profiles(self) -> ProfileRepository:
        raise NotImplementedError

    @property
    def processing_runs(self) -> ProcessingRunRepository:
        raise NotImplementedError

    async def __aenter__(self) -> UnitOfWork:
        raise NotImplementedError

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        raise NotImplementedError

    async def commit(self) -> None:
        raise NotImplementedError

    async def rollback(self) -> None:
        raise NotImplementedError


UnitOfWorkFactory = Callable[[], UnitOfWork]
