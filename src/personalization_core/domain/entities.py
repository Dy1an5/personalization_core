import hashlib
import json
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field

from .base import DomainModel
from .identifiers import SubjectRef
from .types import JsonValue

"""
Entity 可以理解为：
用户接触了什么内容
"""


class EntityCreate(DomainModel):
    entity_type: str
    external_id: str
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    content_text: str | None = None
    schema_version: str


class EntityPatch(DomainModel):
    """
    相较于 Event, Entity 是可能被修改的
    """

    attributes: dict[str, JsonValue] | None = None
    content_text: str | None = None
    schema_version: str | None = None


class Entity:
    id: UUID
    subject: SubjectRef
    entity_type: str
    external_id: str
    attributes: dict[str, JsonValue]
    content_text: str | None
    content_hash: str | None
    schema_version: str
    first_seen_at: datetime
    last_seen_at: datetime
    deleted_at: datetime | None


def entity_content_digest(input: EntityCreate) -> str:
    payload = {
        "attributes": input.attributes,
        "content_text": input.content_text,
        "schema_version": input.schema_version,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_entity(
    subject: SubjectRef,
    input: EntityCreate,
    now: datetime,
    *,
    entity_id: UUID | None = None,
) -> Entity:
    entity = Entity()
    entity.id = entity_id or uuid4()
    entity.subject = subject
    entity.entity_type = input.entity_type
    entity.external_id = input.external_id
    entity.attributes = dict(input.attributes)
    entity.content_text = input.content_text
    entity.content_hash = entity_content_digest(input)
    entity.schema_version = input.schema_version
    entity.first_seen_at = now
    entity.last_seen_at = now
    entity.deleted_at = None
    return entity


def merge_entity(existing: Entity, input: EntityCreate, now: datetime) -> Entity:
    entity = Entity()
    entity.id = existing.id
    entity.subject = existing.subject
    entity.entity_type = existing.entity_type
    entity.external_id = existing.external_id
    entity.attributes = dict(input.attributes)
    entity.content_text = input.content_text
    entity.content_hash = entity_content_digest(input)
    entity.schema_version = input.schema_version
    entity.first_seen_at = existing.first_seen_at
    entity.last_seen_at = now
    entity.deleted_at = existing.deleted_at
    return entity
