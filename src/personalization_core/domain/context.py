from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from .base import StrictFrozenDomainModel
from .features import FeatureState
from .identifiers import SubjectRef
from .memory import MemoryRecord
from .profile import PreferenceConflict
from .types import NonEmptyString, UtcDatetime


class ContextSource(StrEnum):
    STRUCTURED = "structured"
    FULL_TEXT = "full_text"
    VECTOR = "vector"
    RERANKED = "reranked"


ContextQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=4_000),
]
ContextSelector = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class ContextRequest(StrictFrozenDomainModel):
    subject: SubjectRef
    query: ContextQuery | None = None
    use_case: ContextSelector | None = None
    topic: ContextSelector | None = None
    entity: ContextSelector | None = None
    as_of: UtcDatetime | None = None
    token_budget: int | None = Field(default=None, ge=1, le=1_000_000)
    recent_limit: int = Field(default=5, ge=1, le=200)
    long_term_limit: int = Field(default=10, ge=1, le=200)
    include_inferred: bool = False


class MemorySearchHit(StrictFrozenDomainModel):
    memory: MemoryRecord
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    sources: list[ContextSource] = Field(min_length=1)
    evidence_ids: list[UUID] = Field(default_factory=list[UUID])
    matched_terms: list[NonEmptyString] = Field(default_factory=list[NonEmptyString])

    @model_validator(mode="after")
    def normalize_references(self) -> MemorySearchHit:
        object.__setattr__(self, "sources", list(dict.fromkeys(self.sources)))
        object.__setattr__(self, "evidence_ids", list(dict.fromkeys(self.evidence_ids)))
        object.__setattr__(
            self, "matched_terms", list(dict.fromkeys(self.matched_terms))
        )
        return self


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContextBundle(StrictFrozenDomainModel):
    subject: SubjectRef
    query_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: UtcDatetime
    hard_constraints: list[MemoryRecord] = Field(default_factory=list[MemoryRecord])
    memories: list[MemorySearchHit] = Field(default_factory=list[MemorySearchHit])
    recent_interests: list[FeatureState] = Field(default_factory=list[FeatureState])
    long_term_interests: list[FeatureState] = Field(default_factory=list[FeatureState])
    conflicts: list[PreferenceConflict] = Field(
        default_factory=list[PreferenceConflict]
    )
    evidence_ids: list[UUID] = Field(default_factory=list[UUID])
    estimated_tokens: int = Field(default=0, ge=0)
    truncated: bool = False
    algorithm_version: NonEmptyString = "context-resolver-1.0"
    full_text_index_version: NonEmptyString = "none"
    vector_index_version: NonEmptyString = "none"

    @model_validator(mode="after")
    def validate_bundle(self) -> ContextBundle:
        if not _SHA256_RE.fullmatch(self.query_hash):
            raise ValueError("query_hash must be a lowercase SHA-256 digest")
        hard_ids = [memory.id for memory in self.hard_constraints]
        memory_ids = [hit.memory.id for hit in self.memories]
        if len(set(hard_ids)) != len(hard_ids):
            raise ValueError("hard_constraints must not contain duplicate memories")
        if len(set(memory_ids)) != len(memory_ids):
            raise ValueError("memories must not contain duplicate records")
        if set(hard_ids) & set(memory_ids):
            raise ValueError("hard_constraints and memories must not overlap")
        object.__setattr__(self, "evidence_ids", list(dict.fromkeys(self.evidence_ids)))
        return self
