from __future__ import annotations

import json
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, TypeAdapter, model_validator

from .base import StrictFrozenDomainModel
from .enums import MemoryAuthority, MemoryKind, Polarity, ProfileStatus, ResolutionType
from .features import Confidence, EvidenceCount, FeatureState, Score
from .identifiers import SubjectRef
from .memory import MemoryRecord, is_memory_effective
from .types import NonEmptyString, UtcDatetime

EvidenceReference = Annotated[
    str,
    StringConstraints(
        pattern=r"^evidence:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    ),
]


class PreferenceConflict(StrictFrozenDomainModel):
    dimension: NonEmptyString
    value_key: NonEmptyString
    memory_ids: list[UUID] = Field(min_length=1)
    feature_state_key: NonEmptyString
    memory_polarity: Polarity
    behavior_polarity: Polarity
    behavior_score: Score
    reason: NonEmptyString
    evidence_refs: list[EvidenceReference] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_conflict(self) -> PreferenceConflict:
        if len(set(self.memory_ids)) != len(self.memory_ids):
            raise ValueError("memory_ids must be unique")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("conflict evidence_refs must be unique")
        if (
            self.memory_polarity == self.behavior_polarity
            and self.memory_polarity != Polarity.UNKNOWN
        ):
            raise ValueError("equal known polarities are not a conflict")
        if self.behavior_polarity != polarity_for_score(self.behavior_score):
            raise ValueError("behavior polarity must match behavior score")
        return self


class ResolvedPreference(StrictFrozenDomainModel):
    dimension: NonEmptyString
    value_key: NonEmptyString
    explicit_memory_ids: list[UUID] = Field(default_factory=list[UUID])
    feature_state_key: NonEmptyString | None = None
    effective_polarity: Polarity
    effective_score: Score
    confidence: Confidence
    resolution: ResolutionType
    conflicts: list[PreferenceConflict] = Field(
        default_factory=list[PreferenceConflict]
    )
    evidence_refs: list[EvidenceReference] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_resolution(self) -> ResolvedPreference:
        has_memory = bool(self.explicit_memory_ids)
        has_behavior = self.feature_state_key is not None
        if len(set(self.explicit_memory_ids)) != len(self.explicit_memory_ids):
            raise ValueError("explicit_memory_ids must be unique")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        expected_sources = {
            ResolutionType.EXPLICIT_ONLY: (True, False),
            ResolutionType.BEHAVIOR_ONLY: (False, True),
            ResolutionType.ALIGNED: (True, True),
            ResolutionType.EXPLICIT_OVERRIDES_BEHAVIOR: (True, True),
            ResolutionType.UNRESOLVED_CONFLICT: (True, True),
        }
        if (has_memory, has_behavior) != expected_sources[self.resolution]:
            raise ValueError("resolution does not match its sources")
        requires_conflict = self.resolution in {
            ResolutionType.EXPLICIT_OVERRIDES_BEHAVIOR,
            ResolutionType.UNRESOLVED_CONFLICT,
        }
        if bool(self.conflicts) != requires_conflict:
            raise ValueError("resolution does not match conflicts")
        if self.effective_polarity == Polarity.UNKNOWN:
            if self.effective_score != 0:
                raise ValueError("unknown polarity requires zero effective_score")
        elif self.effective_polarity != polarity_for_score(self.effective_score):
            raise ValueError("effective polarity must match effective_score")
        for conflict in self.conflicts:
            if (conflict.dimension, conflict.value_key) != (
                self.dimension,
                self.value_key,
            ):
                raise ValueError("conflict target must match preference target")
            if not set(conflict.memory_ids).issubset(self.explicit_memory_ids):
                raise ValueError("conflict memory IDs must be preference sources")
            if conflict.feature_state_key != self.feature_state_key:
                raise ValueError("conflict feature key must match preference source")
            if not set(conflict.evidence_refs).issubset(self.evidence_refs):
                raise ValueError("conflict evidence must be retained")
        return self


def polarity_for_score(score: float) -> Polarity:
    checked = TypeAdapter[float](Score).validate_python(score)
    if checked > 0:
        return Polarity.POSITIVE
    if checked < 0:
        return Polarity.NEGATIVE
    return Polarity.NEUTRAL


class AuthorityLevel(IntEnum):
    LOW_CONFIDENCE_BEHAVIOR = 0
    INFERRED_MEMORY = 1
    HIGH_CONFIDENCE_BEHAVIOR = 2
    CONFIRMED_MEMORY = 3
    EXPLICIT_MEMORY = 4
    REQUEST_INSTRUCTION = 5


def compare_authority(left: object, right: object) -> int:
    if not isinstance(left, AuthorityLevel) or not isinstance(right, AuthorityLevel):
        raise TypeError("authority comparison requires AuthorityLevel")
    return (left > right) - (left < right)


def feature_state_key(state: FeatureState) -> str:
    return json.dumps(
        [state.dimension, state.value_key, state.aggregator_name],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def resolve_preference_pair(
    *,
    memory: MemoryRecord,
    feature: FeatureState,
    memory_evidence_ids: list[UUID],
    at: UtcDatetime,
    horizon: Literal["long_term", "short_term"] = "long_term",
) -> ResolvedPreference:
    """Resolve one already-selected explicit/confirmed Memory and FeatureState."""
    at = TypeAdapter[datetime](UtcDatetime).validate_python(at)
    if horizon not in {"long_term", "short_term"}:
        raise ValueError("invalid horizon")
    if memory.subject != feature.subject:
        raise ValueError("Memory and FeatureState must belong to the same subject")
    if not is_memory_effective(memory, at=at):
        raise ValueError("Memory must be active and valid at the requested time")
    if memory.kind not in {MemoryKind.PREFERENCE, MemoryKind.CONSTRAINT}:
        raise ValueError("only preferences and constraints can participate")
    if memory.target is None or (
        memory.target.dimension,
        memory.target.value_key,
    ) != (feature.dimension, feature.value_key):
        raise ValueError("Memory target must match FeatureState")
    levels = {
        MemoryAuthority.EXPLICIT: AuthorityLevel.EXPLICIT_MEMORY,
        MemoryAuthority.CONFIRMED: AuthorityLevel.CONFIRMED_MEMORY,
    }
    if memory.authority not in levels:
        raise ValueError("this pair rule requires explicit or confirmed Memory")
    ids = TypeAdapter(list[UUID]).validate_python(memory_evidence_ids, strict=True)
    if not ids:
        raise ValueError("Memory evidence IDs are required")
    refs = sorted({f"evidence:{item}" for item in [*ids, *feature.evidence_ids]})
    score = (
        feature.long_term_score if horizon == "long_term" else feature.short_term_score
    )
    behavior_polarity = polarity_for_score(score)
    behavior_level = (
        AuthorityLevel.HIGH_CONFIDENCE_BEHAVIOR
        if feature.confidence >= 0.7
        else AuthorityLevel.LOW_CONFIDENCE_BEHAVIOR
    )
    if compare_authority(levels[memory.authority], behavior_level) <= 0:
        raise ValueError("Memory authority must outrank behavior")
    conflicts: list[PreferenceConflict] = []
    if memory.polarity == Polarity.UNKNOWN:
        resolution = ResolutionType.UNRESOLVED_CONFLICT
    elif memory.polarity == behavior_polarity:
        resolution = ResolutionType.ALIGNED
    else:
        resolution = ResolutionType.EXPLICIT_OVERRIDES_BEHAVIOR
    if resolution != ResolutionType.ALIGNED:
        conflicts.append(
            PreferenceConflict(
                dimension=feature.dimension,
                value_key=feature.value_key,
                memory_ids=[memory.id],
                feature_state_key=feature_state_key(feature),
                memory_polarity=memory.polarity,
                behavior_polarity=behavior_polarity,
                behavior_score=score,
                reason=(
                    "memory_polarity_unknown"
                    if memory.polarity == Polarity.UNKNOWN
                    else "explicit_or_confirmed_memory_overrides_behavior"
                ),
                evidence_refs=refs,
            )
        )
    explicit_scores = {
        Polarity.POSITIVE: 1.0,
        Polarity.NEGATIVE: -1.0,
        Polarity.NEUTRAL: 0.0,
        Polarity.UNKNOWN: 0.0,
    }
    return ResolvedPreference(
        dimension=feature.dimension,
        value_key=feature.value_key,
        explicit_memory_ids=[memory.id],
        feature_state_key=feature_state_key(feature),
        effective_polarity=memory.polarity,
        effective_score=explicit_scores[memory.polarity],
        confidence=memory.confidence,
        resolution=resolution,
        conflicts=conflicts,
        evidence_refs=refs,
    )


class ProfileCoverage(StrictFrozenDomainModel):
    total_events: EvidenceCount
    processed_events: EvidenceCount
    failed_events: EvidenceCount

    @model_validator(mode="after")
    def validate_counts(self) -> ProfileCoverage:
        if self.processed_events + self.failed_events > self.total_events:
            raise ValueError("processed plus failed cannot exceed total_events")
        return self

    @property
    def pending_events(self) -> int:
        return self.total_events - self.processed_events - self.failed_events

    @property
    def ratio(self) -> float:
        if self.total_events == 0:
            return 1.0
        return self.processed_events / self.total_events

    @property
    def complete(self) -> bool:
        return self.processed_events == self.total_events


class ProfileSnapshot(StrictFrozenDomainModel):
    id: UUID
    subject: SubjectRef
    version: int = Field(ge=1, strict=True)
    status: ProfileStatus
    generated_at: UtcDatetime
    algorithm_version: NonEmptyString
    source_watermark: UtcDatetime | None
    coverage: ProfileCoverage
    preferences: list[ResolvedPreference]
    warnings: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ProfileSnapshot:
        if self.status == ProfileStatus.COMPLETE and not self.coverage.complete:
            raise ValueError("complete status requires complete processing coverage")
        if self.status == ProfileStatus.EMPTY and self.preferences:
            raise ValueError("empty status cannot contain preferences")
        keys = [(item.dimension, item.value_key) for item in self.preferences]
        if len(set(keys)) != len(keys):
            raise ValueError("preference coordinates must be unique")
        return self


class PreferenceChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    STRENGTHENED = "strengthened"
    WEAKENED = "weakened"
    CHANGED = "changed"
    CONFLICT_CHANGED = "conflict_changed"


class PreferenceChange(StrictFrozenDomainModel):
    dimension: NonEmptyString
    value_key: NonEmptyString
    kind: PreferenceChangeKind
    before: ResolvedPreference | None
    after: ResolvedPreference | None

    @model_validator(mode="after")
    def validate_change(self) -> PreferenceChange:
        expected = {
            PreferenceChangeKind.ADDED: (False, True),
            PreferenceChangeKind.REMOVED: (True, False),
        }.get(self.kind, (True, True))
        if (self.before is not None, self.after is not None) != expected:
            raise ValueError("change kind does not match before/after")
        for preference in (self.before, self.after):
            if preference is not None and (
                preference.dimension,
                preference.value_key,
            ) != (self.dimension, self.value_key):
                raise ValueError("change coordinate must match before/after")
        if self.before is not None and self.after is not None:
            if self.before == self.after:
                raise ValueError("a change requires different values")
            if self.kind in {
                PreferenceChangeKind.STRENGTHENED,
                PreferenceChangeKind.WEAKENED,
            }:
                if self.before.effective_polarity != self.after.effective_polarity:
                    raise ValueError("polarity changes must use changed")
                delta = abs(self.after.effective_score) - abs(
                    self.before.effective_score
                )
                if self.kind == PreferenceChangeKind.STRENGTHENED and delta <= 0:
                    raise ValueError("strengthened requires a larger score magnitude")
                if self.kind == PreferenceChangeKind.WEAKENED and delta >= 0:
                    raise ValueError("weakened requires a smaller score magnitude")
            if (
                self.kind == PreferenceChangeKind.CONFLICT_CHANGED
                and self.before.conflicts == self.after.conflicts
            ):
                raise ValueError("conflict_changed requires different conflicts")
        return self


class ProfileDiff(StrictFrozenDomainModel):
    subject: SubjectRef
    left_version: int = Field(ge=1, strict=True)
    right_version: int = Field(ge=1, strict=True)
    changes: list[PreferenceChange] = Field(default_factory=list[PreferenceChange])

    @model_validator(mode="after")
    def validate_diff(self) -> ProfileDiff:
        if self.right_version < self.left_version:
            raise ValueError("right_version cannot precede left_version")
        if self.right_version == self.left_version and self.changes:
            raise ValueError("the same version cannot have changes")
        keys = [(item.dimension, item.value_key, item.kind) for item in self.changes]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate change entries")
        return self
