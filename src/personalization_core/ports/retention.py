from __future__ import annotations

from typing import Protocol, runtime_checkable

from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.types import UtcDatetime


@runtime_checkable
class RetentionHook(Protocol):
    async def on_memory_write(
        self, subject: SubjectRef, occurred_at: UtcDatetime
    ) -> None:
        raise NotImplementedError

    async def on_event_write(
        self, subject: SubjectRef, occurred_at: UtcDatetime
    ) -> None:
        raise NotImplementedError

    async def on_subject_purge(self, subject: SubjectRef) -> None:
        raise NotImplementedError


class NoopRetentionHook:
    async def on_memory_write(
        self, subject: SubjectRef, occurred_at: UtcDatetime
    ) -> None:
        del subject, occurred_at

    async def on_event_write(
        self, subject: SubjectRef, occurred_at: UtcDatetime
    ) -> None:
        del subject, occurred_at

    async def on_subject_purge(self, subject: SubjectRef) -> None:
        del subject
