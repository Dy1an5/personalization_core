from __future__ import annotations

# pyright: reportPrivateUsage=false
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from personalization_core.application.context_service import ContextService
from personalization_core.application.dto import (
    BatchIngestionResult,
    BatchMode,
    EventIngestionInput,
    EventIngestionResult,
    EventPage,
    MemoryCreateInput,
    MemoryExtractionResult,
    MemoryPage,
    MemoryPatchInput,
    ProfileRefreshOptions,
)
from personalization_core.application.event_service import EventService
from personalization_core.application.memory_service import MemoryService
from personalization_core.application.profile_service import ProfileService
from personalization_core.application.subject_service import SubjectService
from personalization_core.domain.context import ContextBundle, ContextRequest
from personalization_core.domain.entities import Entity, EntityCreate
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.memory import MemoryRecord
from personalization_core.domain.profile import ProfileDiff, ProfileSnapshot
from personalization_core.infrastructure.persistence.database import (
    create_session_factory,
    create_sqlite_engine,
)
from personalization_core.infrastructure.persistence.sqlalchemy_models import Base
from personalization_core.infrastructure.persistence.sqlalchemy_uow import (
    create_uow_factory,
)
from personalization_core.ports.audit_sink import AuditSink
from personalization_core.ports.clock import Clock
from personalization_core.ports.embedder import Embedder
from personalization_core.ports.full_text_search import FullTextIndex
from personalization_core.ports.memory_extractor import (
    ConversationMessage,
    MemoryExtractor,
)
from personalization_core.ports.repositories import EventFilter, MemoryFilter, Page
from personalization_core.ports.reranker import Reranker
from personalization_core.ports.unit_of_work import UnitOfWorkFactory
from personalization_core.ports.vector_index import VectorIndex


class SystemClock:
    """UTC wall clock used by the embedded SDK when no clock is injected."""

    def now(self) -> datetime:
        return datetime.now(UTC)


_SchemaInitializer = Callable[[], Awaitable[None]]


class EventOperations:
    def __init__(self, engine: PersonalizationEngine, service: EventService) -> None:
        self._engine = engine
        self._service = service

    async def ingest_batch(
        self,
        subject: SubjectRef,
        events: Sequence[EventIngestionInput],
        *,
        mode: BatchMode = BatchMode.ATOMIC,
    ) -> BatchIngestionResult:
        self._engine._ensure_open()
        return await self._service.ingest_batch(subject, events, mode=mode)

    async def ingest_event(
        self, subject: SubjectRef, event: EventIngestionInput
    ) -> EventIngestionResult:
        self._engine._ensure_open()
        return await self._service.ingest_event(subject, event)

    async def upsert_entity(self, subject: SubjectRef, entity: EntityCreate) -> Entity:
        self._engine._ensure_open()
        return await self._service.upsert_entity(subject, entity)

    async def list_events(
        self,
        subject: SubjectRef,
        filters: EventFilter | None = None,
        page: Page | None = None,
    ) -> EventPage:
        self._engine._ensure_open()
        return await self._service.list_events(subject, filters, page)

    async def list(
        self,
        subject: SubjectRef,
        filters: EventFilter | None = None,
        page: Page | None = None,
    ) -> EventPage:
        return await self.list_events(subject, filters, page)


class MemoryOperations:
    def __init__(self, engine: PersonalizationEngine, service: MemoryService) -> None:
        self._engine = engine
        self._service = service

    async def add(self, subject: SubjectRef, input: MemoryCreateInput) -> MemoryRecord:
        self._engine._ensure_open()
        return await self._service.add_memory(subject, input)

    async def list(
        self,
        subject: SubjectRef,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
    ) -> MemoryPage:
        self._engine._ensure_open()
        return await self._service.list_memories(subject, filters, page)

    async def patch(
        self, subject: SubjectRef, memory_id: UUID, patch: MemoryPatchInput
    ) -> MemoryRecord:
        self._engine._ensure_open()
        return await self._service.patch_memory(subject, memory_id, patch)

    async def confirm(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        self._engine._ensure_open()
        return await self._service.confirm_memory(
            subject, memory_id, expected_revision, actor, reason
        )

    async def delete(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        self._engine._ensure_open()
        return await self._service.delete_memory(
            subject, memory_id, expected_revision, actor, reason
        )

    async def restore(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        self._engine._ensure_open()
        return await self._service.restore_memory(
            subject, memory_id, expected_revision, actor, reason
        )

    async def extract(
        self, subject: SubjectRef, messages: Sequence[ConversationMessage]
    ) -> MemoryExtractionResult:
        self._engine._ensure_open()
        return await self._service.extract_memories(subject, messages)

    async def search(
        self,
        subject: SubjectRef,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
    ) -> MemoryPage:
        self._engine._ensure_open()
        return await self._service.search_memories(subject, filters, page)

    async def add_memory(
        self, subject: SubjectRef, input: MemoryCreateInput
    ) -> MemoryRecord:
        return await self.add(subject, input)

    async def list_memories(
        self,
        subject: SubjectRef,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
    ) -> MemoryPage:
        return await self.list(subject, filters, page)

    async def patch_memory(
        self, subject: SubjectRef, memory_id: UUID, patch: MemoryPatchInput
    ) -> MemoryRecord:
        return await self.patch(subject, memory_id, patch)

    async def confirm_memory(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        return await self.confirm(subject, memory_id, expected_revision, actor, reason)

    async def delete_memory(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        return await self.delete(subject, memory_id, expected_revision, actor, reason)

    async def restore_memory(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        return await self.restore(subject, memory_id, expected_revision, actor, reason)

    async def extract_memories(
        self, subject: SubjectRef, messages: Sequence[ConversationMessage]
    ) -> MemoryExtractionResult:
        return await self.extract(subject, messages)

    async def search_memories(
        self,
        subject: SubjectRef,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
    ) -> MemoryPage:
        return await self.search(subject, filters, page)


class ProfileOperations:
    def __init__(self, engine: PersonalizationEngine, service: ProfileService) -> None:
        self._engine = engine
        self._service = service

    async def refresh(
        self, subject: SubjectRef, options: ProfileRefreshOptions | None = None
    ) -> ProfileSnapshot:
        self._engine._ensure_open()
        return await self._service.refresh_profile(subject, options)

    async def get_latest(self, subject: SubjectRef) -> ProfileSnapshot | None:
        self._engine._ensure_open()
        return await self._service.get_latest_profile(subject)

    async def get_version(
        self, subject: SubjectRef, version: int
    ) -> ProfileSnapshot | None:
        self._engine._ensure_open()
        return await self._service.get_profile_version(subject, version)

    async def compare(self, subject: SubjectRef, left: int, right: int) -> ProfileDiff:
        self._engine._ensure_open()
        return await self._service.compare_profiles(subject, left, right)

    async def refresh_profile(
        self, subject: SubjectRef, options: ProfileRefreshOptions | None = None
    ) -> ProfileSnapshot:
        return await self.refresh(subject, options)

    async def get_latest_profile(self, subject: SubjectRef) -> ProfileSnapshot | None:
        return await self.get_latest(subject)

    async def get_profile_version(
        self, subject: SubjectRef, version: int
    ) -> ProfileSnapshot | None:
        return await self.get_version(subject, version)

    async def compare_profiles(
        self, subject: SubjectRef, left: int, right: int
    ) -> ProfileDiff:
        return await self.compare(subject, left, right)


class ContextOperations:
    def __init__(self, engine: PersonalizationEngine, service: ContextService) -> None:
        self._engine = engine
        self._service = service

    async def resolve(self, request: ContextRequest) -> ContextBundle:
        self._engine._ensure_open()
        return await self._service.resolve_context(request)

    async def resolve_context(self, request: ContextRequest) -> ContextBundle:
        return await self.resolve(request)


_T = TypeVar("_T")


class PersonalizationEngine:
    """Async embedded facade over the existing application services."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        subject_service: SubjectService,
        event_service: EventService,
        memory_service: MemoryService,
        profile_service: ProfileService,
        context_service: ContextService,
        engine: AsyncEngine | None = None,
        owns_engine: bool = False,
        schema_initializer: _SchemaInitializer | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._subject_service = subject_service
        self._engine = engine
        self._owns_engine = owns_engine
        self._schema_initializer = schema_initializer
        self._initialized = False
        self._closed = False
        self.events = EventOperations(self, event_service)
        self.memories = MemoryOperations(self, memory_service)
        self.profiles = ProfileOperations(self, profile_service)
        self.context = ContextOperations(self, context_service)

    @classmethod
    def from_components(
        cls,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock | None = None,
        engine: AsyncEngine | None = None,
        memory_extractor: MemoryExtractor | None = None,
        full_text_index: FullTextIndex | None = None,
        vector_index: VectorIndex | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        audit_sink: AuditSink | None = None,
    ) -> PersonalizationEngine:
        active_clock = clock or SystemClock()
        subject_service = SubjectService(uow_factory, active_clock)
        event_service = EventService(uow_factory, active_clock, subject_service)
        memory_service = MemoryService(
            uow_factory,
            active_clock,
            subject_service,
            extractor=memory_extractor,
        )
        profile_service = ProfileService(uow_factory, active_clock, subject_service)
        context_service = ContextService(
            uow_factory,
            active_clock,
            subject_service,
            full_text_index=full_text_index,
            vector_index=vector_index,
            embedder=embedder,
            reranker=reranker,
            audit_sink=audit_sink,
        )
        return cls(
            uow_factory=uow_factory,
            clock=active_clock,
            subject_service=subject_service,
            event_service=event_service,
            memory_service=memory_service,
            profile_service=profile_service,
            context_service=context_service,
            engine=engine,
        )

    @classmethod
    def from_sqlite(cls, path: str | Path = ":memory:") -> PersonalizationEngine:
        path_text = str(path)
        if path_text not in {":memory:", ""}:
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

        db_engine = create_sqlite_engine(path)
        session_factory = create_session_factory(db_engine)
        uow_factory = create_uow_factory(db_engine, session_factory=session_factory)

        async def initialize_schema() -> None:
            async with db_engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

        active_clock = SystemClock()
        sdk = cls.from_components(
            uow_factory=uow_factory,
            clock=active_clock,
            engine=db_engine,
        )
        sdk._owns_engine = True
        sdk._schema_initializer = initialize_schema
        return sdk

    @property
    def subject_service(self) -> SubjectService:
        return self._subject_service

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def uow_factory(self) -> UnitOfWorkFactory:
        return self._uow_factory

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def initialize(self) -> None:
        self._ensure_open()
        if self._initialized:
            return
        if self._schema_initializer is not None:
            await self._schema_initializer()
        self._initialized = True

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_engine and self._engine is not None:
            await self._engine.dispose()

    async def __aenter__(self) -> PersonalizationEngine:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("PersonalizationEngine is closed")


def from_components(
    *,
    uow_factory: UnitOfWorkFactory,
    clock: Clock | None = None,
    engine: AsyncEngine | None = None,
    memory_extractor: MemoryExtractor | None = None,
    full_text_index: FullTextIndex | None = None,
    vector_index: VectorIndex | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    audit_sink: AuditSink | None = None,
) -> PersonalizationEngine:
    return PersonalizationEngine.from_components(
        uow_factory=uow_factory,
        clock=clock,
        engine=engine,
        memory_extractor=memory_extractor,
        full_text_index=full_text_index,
        vector_index=vector_index,
        embedder=embedder,
        reranker=reranker,
        audit_sink=audit_sink,
    )
