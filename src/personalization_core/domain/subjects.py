from datetime import datetime
from uuid import UUID

from pydantic import Field

from .base import DomainModel
from .identifiers import SubjectRef
from .types import JsonValue

"""
Subject 可以理解为：
Personalization Core 正在为谁建立记忆、行为和画像。
"""


class SubjectCreate(DomainModel):
    ref: SubjectRef
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class Subject(DomainModel):
    id: UUID
    ref: SubjectRef
    metadata: dict[str, JsonValue]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
