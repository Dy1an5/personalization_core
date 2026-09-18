from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.types import JsonValue, NonEmptyString, UtcDatetime


class AuditEvent(StrictFrozenDomainModel):
    subject: SubjectRef
    action: NonEmptyString
    occurred_at: UtcDatetime
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


@runtime_checkable
class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None:
        raise NotImplementedError
