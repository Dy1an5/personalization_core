from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field, model_validator

from .base import StrictFrozenDomainModel
from .enums import Polarity
from .identifiers import SubjectRef
from .types import JsonValue, NonEmptyString, UtcDatetime

Score = Annotated[
    float,
    Field(
        ge=-1.0,
        le=1.0,
        allow_inf_nan=False,
    ),
]

Confidence = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]

EvidenceCount = Annotated[
    int,
    Field(
        ge=0,
        strict=True,
    ),
]


class FeatureObservationDraft(StrictFrozenDomainModel):
    dimension: NonEmptyString
    value_key: NonEmptyString
    value: dict[str, JsonValue] = Field(default_factory=dict)
    score: Score
    polarity: Polarity
    confidence: Confidence
    occurred_at: UtcDatetime


class FeatureObservation(FeatureObservationDraft):
    id: UUID
    subject: SubjectRef
    source_event_id: UUID
    evidence_id: UUID
    extractor_name: NonEmptyString
    extractor_version: NonEmptyString
    created_at: UtcDatetime

    @property
    def identity_key(self) -> tuple[UUID, str, str, str, str]:
        return (
            self.source_event_id,
            self.dimension,
            self.value_key,
            self.extractor_name,
            self.extractor_version,
        )


class FeatureStateDraft(StrictFrozenDomainModel):
    dimension: NonEmptyString
    value_key: NonEmptyString
    value: dict[str, JsonValue] = Field(default_factory=dict)
    long_term_score: Score
    short_term_score: Score
    confidence: Confidence
    positive_evidence_count: EvidenceCount
    negative_evidence_count: EvidenceCount
    neutral_evidence_count: EvidenceCount
    first_evidence_at: UtcDatetime
    last_evidence_at: UtcDatetime
    evidence_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> FeatureStateDraft:
        if self.first_evidence_at > self.last_evidence_at:
            raise ValueError("first_evidence_at must not exceed last_evidence_at")
        if self.evidence_count == 0:
            raise ValueError("FeatureState requires at least one counted observation")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique")
        return self

    @property
    def evidence_count(self) -> int:
        return (
            self.positive_evidence_count
            + self.negative_evidence_count
            + self.neutral_evidence_count
        )


class FeatureState(FeatureStateDraft):
    subject: SubjectRef
    aggregator_name: NonEmptyString
    algorithm_version: NonEmptyString
    updated_at: UtcDatetime
