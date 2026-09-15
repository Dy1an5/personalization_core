from datetime import datetime
from uuid import UUID

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
