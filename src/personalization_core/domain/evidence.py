from datetime import datetime
from uuid import UUID

from pydantic import Field

from .base import DomainModel
from .enums import EvidenceSourceType
from .identifiers import SubjectRef
from .types import JsonValue

"""
证据, 为什么知道
"""


class EvidenceCreate(DomainModel):
    source_type: EvidenceSourceType
    source_ref: str
    event_id: UUID | None = None
    excerpt: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime


class Evidence(DomainModel):
    id: UUID
    subject: SubjectRef
    source_type: EvidenceSourceType
    source_ref: str
    event_id: UUID | None
    excerpt: str | None
    metadata: dict[str, JsonValue]
    occurred_at: datetime
    created_at: datetime
