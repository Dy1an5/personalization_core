"""Strict, provider-independent contracts for deterministic evaluation."""

from __future__ import annotations

from typing import Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.enums import ResolutionType
from personalization_core.domain.types import NonEmptyString


class _EvaluationModel(StrictFrozenDomainModel):
    """Evaluation models accept field names as well as JSON field aliases."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )


def _require_unique(values: list[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values")


class MemoryExtractionCase(_EvaluationModel):
    case_id: NonEmptyString
    expected_keys: list[NonEmptyString] = Field(min_length=1)
    predicted_keys: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_keys(self) -> Self:
        _require_unique(self.expected_keys, "expected_keys")
        _require_unique(self.predicted_keys, "predicted_keys")
        return self


class RetrievalCase(_EvaluationModel):
    case_id: NonEmptyString
    relevant_ids: list[NonEmptyString] = Field(min_length=1)
    ranked_ids: list[NonEmptyString] = Field(min_length=1)
    k: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def validate_ids(self) -> Self:
        _require_unique(self.relevant_ids, "relevant_ids")
        _require_unique(self.ranked_ids, "ranked_ids")
        return self


class ConflictCase(_EvaluationModel):
    case_id: NonEmptyString
    expected_resolution: ResolutionType
    observed_resolution: ResolutionType

    @field_validator("expected_resolution", "observed_resolution", mode="before")
    @classmethod
    def parse_resolution(cls, value: object) -> ResolutionType:
        return ResolutionType(value)


class ConstraintRetentionCase(_EvaluationModel):
    case_id: NonEmptyString
    constraint_ids: list[NonEmptyString] = Field(min_length=1)
    retained_ids: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ids(self) -> Self:
        _require_unique(self.constraint_ids, "constraint_ids")
        _require_unique(self.retained_ids, "retained_ids")
        return self


class ProfilePreference(_EvaluationModel):
    dimension: NonEmptyString
    value_key: NonEmptyString
    state: NonEmptyString

    @property
    def coordinate(self) -> str:
        return f"{self.dimension}:{self.value_key}"


def _empty_profile_preferences() -> list[ProfilePreference]:
    return []


class ProfileCase(_EvaluationModel):
    case_id: NonEmptyString
    before: list[ProfilePreference] = Field(default_factory=_empty_profile_preferences)
    after: list[ProfilePreference] = Field(default_factory=_empty_profile_preferences)
    expected_changed: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        before_coordinates = [item.coordinate for item in self.before]
        after_coordinates = [item.coordinate for item in self.after]
        _require_unique(before_coordinates, "before coordinates")
        _require_unique(after_coordinates, "after coordinates")
        _require_unique(self.expected_changed, "expected_changed")
        coordinates = set(before_coordinates) | set(after_coordinates)
        if not coordinates:
            raise ValueError("a profile case must contain at least one coordinate")
        if not set(self.expected_changed).issubset(coordinates):
            raise ValueError("expected_changed must reference profile coordinates")
        return self


class TenantIsolationCase(_EvaluationModel):
    case_id: NonEmptyString
    allowed_ids: list[NonEmptyString] = Field(min_length=1)
    returned_ids: list[NonEmptyString] = Field(min_length=1)
    foreign_ids: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ids(self) -> Self:
        _require_unique(self.allowed_ids, "allowed_ids")
        _require_unique(self.returned_ids, "returned_ids")
        _require_unique(self.foreign_ids, "foreign_ids")
        if set(self.allowed_ids) & set(self.foreign_ids):
            raise ValueError("allowed_ids and foreign_ids must be disjoint")
        return self


class ProviderFailureCase(_EvaluationModel):
    case_id: NonEmptyString
    expected_error_code: NonEmptyString
    observed_error_code: NonEmptyString


class EvaluationDataset(_EvaluationModel):
    memory_extraction: list[MemoryExtractionCase] = Field(min_length=1)
    memory_retrieval: list[RetrievalCase] = Field(min_length=1)
    preference_conflicts: list[ConflictCase] = Field(min_length=1)
    constraint_retention: list[ConstraintRetentionCase] = Field(min_length=1)
    profiles: list[ProfileCase] = Field(min_length=1)
    tenant_isolation: list[TenantIsolationCase] = Field(min_length=1)
    provider_failures: list[ProviderFailureCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> Self:
        collections = {
            "memory_extraction": self.memory_extraction,
            "memory_retrieval": self.memory_retrieval,
            "preference_conflicts": self.preference_conflicts,
            "constraint_retention": self.constraint_retention,
            "profiles": self.profiles,
            "tenant_isolation": self.tenant_isolation,
            "provider_failures": self.provider_failures,
        }
        for name, cases in collections.items():
            _require_unique([case.case_id for case in cases], f"{name} case_id")
        return self


class MetricResult(_EvaluationModel):
    name: NonEmptyString
    value: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    numerator: float = Field(ge=0.0, allow_inf_nan=False)
    denominator: float = Field(gt=0.0, allow_inf_nan=False)
    target: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    passed: bool

    @model_validator(mode="after")
    def validate_ratio(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("numerator cannot exceed denominator")
        return self


class EvaluationReport(_EvaluationModel):
    dataset_name: NonEmptyString = "evaluation"
    metrics: list[MetricResult] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_metrics(self) -> Self:
        _require_unique([metric.name for metric in self.metrics], "metric names")
        return self

    @property
    def passed(self) -> bool:
        return all(metric.passed for metric in self.metrics)


__all__ = [
    "ConflictCase",
    "ConstraintRetentionCase",
    "EvaluationDataset",
    "EvaluationReport",
    "MemoryExtractionCase",
    "MetricResult",
    "ProfileCase",
    "ProfilePreference",
    "ProviderFailureCase",
    "RetrievalCase",
    "TenantIsolationCase",
]
