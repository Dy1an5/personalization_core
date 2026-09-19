from __future__ import annotations

from types import TracebackType
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from personalization_core.domain.identifiers import SubjectRef
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
from .sqlalchemy_models import (
    AuditLogRow,
    EntityRow,
    EventRow,
    EvidenceRow,
    FeatureObservationRow,
    FeatureStateEvidenceRow,
    FeatureStateRow,
    MemoryEvidenceRow,
    MemoryRevisionRow,
    MemoryRow,
    ProcessingRunRow,
    ProfileSnapshotRow,
    SubjectRow,
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

    async def purge_subject(self, subject: SubjectRef) -> None:
        session = self._require_session()
        subject_pk = await session.scalar(
            select(SubjectRow.id).where(
                SubjectRow.tenant_id == subject.tenant_id.root,
                SubjectRow.namespace == subject.namespace.root,
                SubjectRow.external_subject_id == subject.subject_id.root,
            )
        )
        if subject_pk is None:
            return

        # Several child tables deliberately use NO ACTION constraints.  Delete
        # those rows explicitly in dependency order so purge is portable across
        # SQLite and PostgreSQL and remains one UoW transaction.
        await session.execute(
            delete(AuditLogRow).where(AuditLogRow.subject_pk == subject_pk)
        )
        await session.execute(
            delete(FeatureStateEvidenceRow).where(
                FeatureStateEvidenceRow.feature_state_id.in_(
                    select(FeatureStateRow.id).where(
                        FeatureStateRow.subject_pk == subject_pk
                    )
                )
            )
        )
        await session.execute(
            delete(MemoryEvidenceRow).where(
                MemoryEvidenceRow.memory_id.in_(
                    select(MemoryRow.id).where(MemoryRow.subject_pk == subject_pk)
                )
            )
        )
        await session.execute(
            delete(FeatureObservationRow).where(
                FeatureObservationRow.subject_pk == subject_pk
            )
        )
        await session.execute(
            delete(MemoryRevisionRow).where(MemoryRevisionRow.subject_pk == subject_pk)
        )
        await session.execute(
            delete(ProfileSnapshotRow).where(
                ProfileSnapshotRow.subject_pk == subject_pk
            )
        )
        await session.execute(
            delete(ProcessingRunRow).where(ProcessingRunRow.subject_pk == subject_pk)
        )
        await session.execute(
            delete(FeatureStateRow).where(FeatureStateRow.subject_pk == subject_pk)
        )
        await session.execute(
            delete(MemoryRow).where(MemoryRow.subject_pk == subject_pk)
        )
        await session.execute(
            delete(EvidenceRow).where(EvidenceRow.subject_pk == subject_pk)
        )
        await session.execute(delete(EventRow).where(EventRow.subject_pk == subject_pk))
        await session.execute(
            delete(EntityRow).where(EntityRow.subject_pk == subject_pk)
        )
        await session.execute(delete(SubjectRow).where(SubjectRow.id == subject_pk))


class SQLAlchemyUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    def __call__(self) -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(self.session_factory)


def create_uow_factory(
    engine: AsyncEngine,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> SQLAlchemyUnitOfWorkFactory:
    """Build a UnitOfWork factory directly from an async engine."""
    return SQLAlchemyUnitOfWorkFactory(
        session_factory
        or async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    )
