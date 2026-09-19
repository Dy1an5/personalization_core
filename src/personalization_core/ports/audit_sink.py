from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any, Protocol, cast, runtime_checkable

from pydantic import Field, model_validator

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.types import JsonValue, NonEmptyString, UtcDatetime

_SENSITIVE_FIELDS = frozenset(
    {
        "content",
        "query",
        "excerpt",
        "evidencequote",
        "authorization",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
        "bearer",
        "cookie",
        "privatekey",
        "apisecret",
        "password",
        "secret",
        "credential",
        "token",
    }
)


def _normalized_field_name(value: object) -> str:
    return "".join(
        character for character in str(value).casefold() if character.isalnum()
    )


def sanitize_log_fields(value: Any) -> Any:
    """Recursively remove fields that can contain user text or credentials."""
    if isinstance(value, Mapping):
        mapping = cast(Mapping[Any, Any], value)
        return {
            str(key): sanitize_log_fields(item)
            for key, item in mapping.items()
            if _normalized_field_name(key) not in _SENSITIVE_FIELDS
        }
    if isinstance(value, list):
        items = cast(list[Any], value)
        return [sanitize_log_fields(item) for item in items]
    if isinstance(value, tuple):
        items = cast(tuple[Any, ...], value)
        return [sanitize_log_fields(item) for item in items]
    return value


def subject_digest(subject: SubjectRef) -> str:
    """Return a stable, non-reversible identifier for an audit scope."""
    scope = "\0".join(
        (subject.tenant_id.root, subject.namespace.root, subject.subject_id.root)
    )
    return sha256(scope.encode("utf-8")).hexdigest()


class AuditEvent(StrictFrozenDomainModel):
    subject: SubjectRef
    action: NonEmptyString
    occurred_at: UtcDatetime
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sanitize_metadata(self) -> AuditEvent:
        object.__setattr__(self, "metadata", sanitize_log_fields(self.metadata))
        return self


@runtime_checkable
class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None:
        raise NotImplementedError


class NullAuditSink:
    """Safe default sink for applications that do not configure persistence."""

    async def emit(self, event: AuditEvent) -> None:
        del event


DefaultAuditSink = NullAuditSink
