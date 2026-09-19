from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

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
from personalization_core.domain.context import ContextBundle, ContextRequest
from personalization_core.domain.entities import Entity, EntityCreate
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.memory import MemoryRecord
from personalization_core.domain.profile import ProfileDiff, ProfileSnapshot
from personalization_core.ports.memory_extractor import ConversationMessage
from personalization_core.ports.repositories import EventFilter, MemoryFilter, Page

from .async_client import PersonalizationEngine
from .errors import SyncClientInAsyncContextError

# pyright: reportPrivateUsage=false

_T = TypeVar("_T")
_CoroutineFactory = Callable[[], Coroutine[Any, Any, _T]]


class SyncEventOperations:
    def __init__(self, client: PersonalizationClient) -> None:
        self._client = client

    def ingest_batch(
        self,
        subject: SubjectRef,
        events: Sequence[EventIngestionInput],
        *,
        mode: BatchMode = BatchMode.ATOMIC,
    ) -> BatchIngestionResult:
        return self._client._run(
            lambda: self._client.engine.events.ingest_batch(subject, events, mode=mode)
        )

    def ingest_event(
        self, subject: SubjectRef, event: EventIngestionInput
    ) -> EventIngestionResult:
        return self._client._run(
            lambda: self._client.engine.events.ingest_event(subject, event)
        )

    def upsert_entity(self, subject: SubjectRef, entity: EntityCreate) -> Entity:
        return self._client._run(
            lambda: self._client.engine.events.upsert_entity(subject, entity)
        )

    def list_events(
        self,
        subject: SubjectRef,
        filters: EventFilter | None = None,
        page: Page | None = None,
    ) -> EventPage:
        return self._client._run(
            lambda: self._client.engine.events.list_events(subject, filters, page)
        )

    def list(
        self,
        subject: SubjectRef,
        filters: EventFilter | None = None,
        page: Page | None = None,
    ) -> EventPage:
        return self.list_events(subject, filters, page)


class SyncMemoryOperations:
    def __init__(self, client: PersonalizationClient) -> None:
        self._client = client

    def add(self, subject: SubjectRef, input: MemoryCreateInput) -> MemoryRecord:
        return self._client._run(
            lambda: self._client.engine.memories.add(subject, input)
        )

    def list(
        self,
        subject: SubjectRef,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
    ) -> MemoryPage:
        return self._client._run(
            lambda: self._client.engine.memories.list(subject, filters, page)
        )

    def patch(
        self, subject: SubjectRef, memory_id: UUID, patch: MemoryPatchInput
    ) -> MemoryRecord:
        return self._client._run(
            lambda: self._client.engine.memories.patch(subject, memory_id, patch)
        )

    def confirm(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        return self._client._run(
            lambda: self._client.engine.memories.confirm(
                subject, memory_id, expected_revision, actor, reason
            )
        )

    def delete(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        return self._client._run(
            lambda: self._client.engine.memories.delete(
                subject, memory_id, expected_revision, actor, reason
            )
        )

    def restore(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        return self._client._run(
            lambda: self._client.engine.memories.restore(
                subject, memory_id, expected_revision, actor, reason
            )
        )

    def extract(
        self, subject: SubjectRef, messages: Sequence[ConversationMessage]
    ) -> MemoryExtractionResult:
        return self._client._run(
            lambda: self._client.engine.memories.extract(subject, messages)
        )

    def search(
        self,
        subject: SubjectRef,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
    ) -> MemoryPage:
        return self._client._run(
            lambda: self._client.engine.memories.search(subject, filters, page)
        )


class SyncProfileOperations:
    def __init__(self, client: PersonalizationClient) -> None:
        self._client = client

    def refresh(
        self, subject: SubjectRef, options: ProfileRefreshOptions | None = None
    ) -> ProfileSnapshot:
        return self._client._run(
            lambda: self._client.engine.profiles.refresh(subject, options)
        )

    def get_latest(self, subject: SubjectRef) -> ProfileSnapshot | None:
        return self._client._run(
            lambda: self._client.engine.profiles.get_latest(subject)
        )

    def get_version(self, subject: SubjectRef, version: int) -> ProfileSnapshot | None:
        return self._client._run(
            lambda: self._client.engine.profiles.get_version(subject, version)
        )

    def compare(self, subject: SubjectRef, left: int, right: int) -> ProfileDiff:
        return self._client._run(
            lambda: self._client.engine.profiles.compare(subject, left, right)
        )


class SyncContextOperations:
    def __init__(self, client: PersonalizationClient) -> None:
        self._client = client

    def resolve(self, request: ContextRequest) -> ContextBundle:
        return self._client._run(lambda: self._client.engine.context.resolve(request))


class PersonalizationClient:
    """Synchronous SDK wrapper for applications without an active event loop."""

    def __init__(self, engine: PersonalizationEngine) -> None:
        self.engine = engine
        self.events = SyncEventOperations(self)
        self.memories = SyncMemoryOperations(self)
        self.profiles = SyncProfileOperations(self)
        self.context = SyncContextOperations(self)

    @classmethod
    def from_sqlite(cls, path: str | Path = ":memory:") -> PersonalizationClient:
        client = cls(PersonalizationEngine.from_sqlite(path))
        try:
            client.initialize()
        except BaseException:
            client.close()
            raise
        return client

    def initialize(self) -> None:
        self._run(self.engine.initialize)

    def close(self) -> None:
        self._run(self.engine.close)

    def _run(self, operation: _CoroutineFactory[_T]) -> _T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(operation())
        raise SyncClientInAsyncContextError(
            "PersonalizationClient cannot be used inside a running event loop; "
            "use PersonalizationEngine instead"
        )
