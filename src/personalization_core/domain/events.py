import hashlib
import json
from uuid import UUID

from pydantic import Field

from .base import DomainModel, FrozenDomainModel
from .enums import IdempotencyDecision, Polarity
from .identifiers import EntityRef, SubjectRef
from .types import JsonValue, NonEmptyString, UtcDatetime

"""
Event 表示一个已经发生的行为事实
"""


class EventCreate(DomainModel):
    event_type: NonEmptyString
    entity: EntityRef | None = None
    source: NonEmptyString
    idempotency_key: NonEmptyString
    value: float | None = None
    polarity: Polarity = Polarity.UNKNOWN
    properties: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: UtcDatetime
    schema_version: NonEmptyString


class Event(FrozenDomainModel):
    """
    幂等身份：
    subject
    source
    idempotency_key


    Event 内容：
    event_type
    entity
    value
    polarity
    properties
    occurred_at
    schema_version
    """

    id: UUID
    subject: SubjectRef
    event_type: NonEmptyString
    entity: EntityRef | None
    source: NonEmptyString
    idempotency_key: NonEmptyString
    value: float | None
    polarity: Polarity
    properties: dict[str, JsonValue]
    occurred_at: UtcDatetime
    observed_at: UtcDatetime
    schema_version: NonEmptyString


def _normalize_entity_ref(entity: EntityRef | None) -> JsonValue:
    if entity is None:
        return None

    return entity.model_dump(mode="json")


def _normalize_datetime(value: UtcDatetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_event_content(event: EventCreate | Event) -> dict[str, JsonValue]:
    """
    把 Event 转换成一个标准的 JSON 内容
    """
    return {
        "event_type": event.event_type,
        "entity": _normalize_entity_ref(event.entity),
        "value": event.value,
        "polarity": event.polarity.value,
        "properties": event.properties,
        "occurred_at": _normalize_datetime(event.occurred_at),
        "schema_version": event.schema_version,
    }


def canonical_json_bytes(value: JsonValue) -> bytes:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    return serialized.encode("utf-8")


def event_content_digest(event: EventCreate | Event) -> str:
    normalized = normalize_event_content(event)
    canonical = canonical_json_bytes(normalized)

    return hashlib.sha256(canonical).hexdigest()


def has_same_idempotency_scope(
    existing: Event,
    incoming_subject: SubjectRef,
    incoming: EventCreate,
) -> bool:
    """
    相同幂等作用域
    """
    return (
        existing.subject == incoming_subject
        and existing.source == incoming.source
        and existing.idempotency_key == incoming.idempotency_key
    )


def has_same_event_content(
    existing: Event,
    incoming: EventCreate,
) -> bool:
    return event_content_digest(existing) == event_content_digest(incoming)


def classify_idempotency(
    existing: Event,
    incoming_subject: SubjectRef,
    incoming: EventCreate,
) -> IdempotencyDecision:
    if not has_same_idempotency_scope(existing, incoming_subject, incoming):
        return IdempotencyDecision.DIFFERENT_SCOPE

    if has_same_event_content(existing, incoming):
        return IdempotencyDecision.REPLAY

    return IdempotencyDecision.CONFLICT
