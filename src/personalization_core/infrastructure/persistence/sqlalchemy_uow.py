from __future__ import annotations

from types import TracebackType
from typing import cast

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from personalization_core.ports.repositories import (
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
from personalization_core.ports.unit_of_work import UnitOfWork

from .repositories import (
    SQLAlchemyEntityRepository,
    SQLAlchemyEventRepository,
    SQLAlchemyEvidenceRepository,
    SQLAlchemyFeatureRepository,
    SQLAlchemyMemoryRepository,
    SQLAlchemyMemoryRevisionRepository,
    SQLAlchemyProcessingRunRepository,
    SQLAlchemyProfileRepository,
    SQLAlchemySubjectRepository,
)


class SQLAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False
        self._repositories: dict[str, object] = {}

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return self._session

    @property
    def subjects(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(SubjectRepository, self._repositories["subjects"])

    @property
    def entities(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(EntityRepository, self._repositories["entities"])

    @property
    def events(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(EventRepository, self._repositories["events"])

    @property
    def evidence(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(EvidenceRepository, self._repositories["evidence"])

    @property
    def memories(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(MemoryRepository, self._repositories["memories"])

    @property
    def memory_revisions(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(MemoryRevisionRepository, self._repositories["memory_revisions"])

    @property
    def features(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(FeatureRepository, self._repositories["features"])

    @property
    def profiles(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(ProfileRepository, self._repositories["profiles"])

    @property
    def processing_runs(self):
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return cast(ProcessingRunRepository, self._repositories["processing_runs"])

    async def __aenter__(self) -> SQLAlchemyUnitOfWork:
        if self._session is not None:
            raise RuntimeError("unit of work is already active")
        self._session = self._session_factory()
        self._committed = False
        self._repositories = {
            "subjects": SQLAlchemySubjectRepository(self._session),
            "entities": SQLAlchemyEntityRepository(self._session),
            "events": SQLAlchemyEventRepository(self._session),
            "evidence": SQLAlchemyEvidenceRepository(self._session),
            "memories": SQLAlchemyMemoryRepository(self._session),
            "memory_revisions": SQLAlchemyMemoryRevisionRepository(self._session),
            "features": SQLAlchemyFeatureRepository(self._session),
            "profiles": SQLAlchemyProfileRepository(self._session),
            "processing_runs": SQLAlchemyProcessingRunRepository(self._session),
        }
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._session
        try:
            if session is not None and (exc_type is not None or not self._committed):
                await session.rollback()
        finally:
            if session is not None:
                await session.close()
            self._session = None
            self._repositories = {}
            self._committed = False

    async def commit(self) -> None:
        session = self._require_session()
        await session.commit()
        self._committed = True

    async def rollback(self) -> None:
        session = self._require_session()
        await session.rollback()
        self._committed = False


class SQLAlchemyUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    def __call__(self) -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(self.session_factory)


def create_uow_factory(engine: AsyncEngine) -> SQLAlchemyUnitOfWorkFactory:
    """Build a UnitOfWork factory directly from an async engine."""
    return SQLAlchemyUnitOfWorkFactory(
        async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    )
