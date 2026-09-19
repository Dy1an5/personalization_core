from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

import httpx

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
from .remote_client import AsyncPersonalizationClient

# pyright: reportPrivateUsage=false

_T = TypeVar("_T")
_CoroutineFactory = Callable[[], Coroutine[Any, Any, _T]]


class _SyncRemoteGroup:
    """Small synchronous facade for one remote async operation group."""

    def __init__(self, client: PersonalizationClient, group: Any) -> None:
        self._client = client
        self._group = group

    def __getattr__(self, name: str) -> Any:
        async_method = getattr(self._group, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            return self._client._run(lambda: async_method(*args, **kwargs))

        return call


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

    def __init__(
        self,
        engine: PersonalizationEngine | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        tenant_id: str | None = None,
        namespace: str = "default",
        timeout: float | httpx.Timeout = 10.0,
        max_retries: int = 2,
        retry_backoff: float | Callable[[int], float] = 0.1,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if engine is not None and any(
            value is not None for value in (base_url, api_key, tenant_id)
        ):
            raise ValueError("engine and remote connection settings are exclusive")
        if engine is None:
            if not base_url or api_key is None or tenant_id is None:
                raise ValueError(
                    "base_url, api_key, and tenant_id are required for remote mode"
                )
            remote = AsyncPersonalizationClient(
                base_url=base_url,
                api_key=api_key,
                tenant_id=tenant_id,
                namespace=namespace,
                timeout=timeout,
                max_retries=max_retries,
                retry_backoff=retry_backoff,
                http_client=http_client,
                transport=transport,
            )
            self.engine: Any = remote
            self.events = _SyncRemoteGroup(self, remote.events)
            self.memories = _SyncRemoteGroup(self, remote.memories)
            self.profiles = _SyncRemoteGroup(self, remote.profiles)
            self.context = _SyncRemoteGroup(self, remote.context)
            self.health = _SyncRemoteGroup(self, remote.health)
            self.preferences = _SyncRemoteGroup(self, remote.preferences)
            self.subjects = _SyncRemoteGroup(self, remote.subjects)
            return

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
            "use AsyncPersonalizationClient instead"
        )


SyncPersonalizationClient = PersonalizationClient
