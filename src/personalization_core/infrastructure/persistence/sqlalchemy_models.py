from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)


class UUIDType(TypeDecorator[UUID]):
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(
        self, value: UUID | str | None, dialect: Any
    ) -> str | UUID | None:
        if value is None:
            return None
        parsed = value if isinstance(value, UUID) else UUID(str(value))
        return parsed if dialect.name == "postgresql" else str(parsed)

    def process_result_value(
        self, value: UUID | str | None, dialect: Any
    ) -> UUID | None:
        if value is None:
            return None
        return value if isinstance(value, UUID) else UUID(str(value))


class JSONType(TypeDecorator[dict[str, Any] | list[Any] | None]):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None or dialect.name == "postgresql":
            return value
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None or dialect.name == "postgresql":
            return value
        return json.loads(value) if isinstance(value, str) else value


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        value = value.astimezone(UTC)
        return value if dialect.name == "postgresql" else value.replace(tzinfo=None)

    def process_result_value(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class SubjectRow(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "namespace", "external_subject_id"),
    )

    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    external_subject_id: Mapped[str] = mapped_column(String(200), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType(), nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class EntityRow(Base):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("subject_pk", "entity_type", "external_id"),
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
    )

    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONType(), nullable=False, default=dict
    )
    content_text: Mapped[str | None] = mapped_column(Text())
    content_hash: Mapped[str | None] = mapped_column(String(200))
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("subject_pk", "source", "idempotency_key"),
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["subject_pk", "entity_type", "entity_external_id"],
            ["entities.subject_pk", "entities.entity_type", "entities.external_id"],
            ondelete="NO ACTION",
        ),
        CheckConstraint(
            "(entity_type IS NULL AND entity_external_id IS NULL) OR "
            "(entity_type IS NOT NULL AND entity_external_id IS NOT NULL)",
            name="event_entity_pair",
        ),
    )

    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_external_id: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[float | None] = mapped_column(Float())
    polarity: Mapped[str] = mapped_column(String(20), nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(
        JSONType(), nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("subject_pk", "source_type", "source_ref"),
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="NO ACTION"),
    )

    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    event_id: Mapped[UUID | None] = mapped_column(UUIDType())
    excerpt: Mapped[str | None] = mapped_column(String(2000))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType(), nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class MemoryRow(Base):
    __tablename__ = "memories"
    __table_args__ = (
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="memory_confidence"
        ),
        CheckConstraint("revision >= 1", name="memory_revision"),
        CheckConstraint("scope_key IS NOT NULL", name="memory_scope_key"),
    )

    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    structured_value: Mapped[dict[str, Any] | None] = mapped_column(JSONType())
    target_dimension: Mapped[str | None] = mapped_column(String(100))
    target_value_key: Mapped[str | None] = mapped_column(String(200))
    authority: Mapped[str] = mapped_column(String(30), nullable=False)
    polarity: Mapped[str] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_value: Mapped[str | None] = mapped_column(String(200))
    scope_key: Mapped[str] = mapped_column(String(200), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime())
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    evidence_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    revision: Mapped[int] = mapped_column(Integer(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class MemoryEvidenceRow(Base):
    __tablename__ = "memory_evidence"
    __table_args__ = (
        ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"),
    )
    memory_id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)


class MemoryRevisionRow(Base):
    __tablename__ = "memory_revisions"
    __table_args__ = (
        UniqueConstraint("memory_id", "revision"),
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
    )
    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    memory_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    revision: Mapped[int] = mapped_column(Integer(), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType(), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    transition: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class FeatureObservationRow(Base):
    __tablename__ = "feature_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_event_id",
            "dimension",
            "value_key",
            "extractor_name",
            "extractor_version",
        ),
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["source_event_id"], ["events.id"], ondelete="NO ACTION"),
        ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="NO ACTION"),
    )
    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    value_key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONType(), nullable=False, default=dict
    )
    score: Mapped[float] = mapped_column(Float(), nullable=False)
    polarity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    source_event_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class FeatureStateRow(Base):
    __tablename__ = "feature_states"
    __table_args__ = (
        UniqueConstraint("subject_pk", "dimension", "value_key", "aggregator_name"),
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
    )
    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    value_key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONType(), nullable=False, default=dict
    )
    long_term_score: Mapped[float] = mapped_column(Float(), nullable=False)
    short_term_score: Mapped[float] = mapped_column(Float(), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(), nullable=False)
    positive_evidence_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    negative_evidence_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    neutral_evidence_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    first_evidence_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_evidence_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    aggregator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class FeatureStateEvidenceRow(Base):
    __tablename__ = "feature_state_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["feature_state_id"], ["feature_states.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"),
    )
    feature_state_id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)


class ProfileSnapshotRow(Base):
    __tablename__ = "profile_snapshots"
    __table_args__ = (
        UniqueConstraint("subject_pk", "version"),
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
    )
    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    version: Mapped[int] = mapped_column(Integer(), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    source_watermark: Mapped[datetime | None] = mapped_column(UTCDateTime())
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONType(), nullable=False)
    preferences: Mapped[list[Any]] = mapped_column(JSONType(), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONType(), nullable=False)


class ProcessingRunRow(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
    )
    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    processed_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        ForeignKeyConstraint(["subject_pk"], ["subjects.id"], ondelete="CASCADE"),
    )
    id: Mapped[UUID] = mapped_column(UUIDType(), primary_key=True)
    subject_pk: Mapped[UUID] = mapped_column(UUIDType(), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType(), nullable=False, default=dict
    )


Index("ix_events_subject_occurred", EventRow.subject_pk, EventRow.occurred_at.desc())
Index(
    "ix_events_subject_type_occurred",
    EventRow.subject_pk,
    EventRow.event_type,
    EventRow.occurred_at.desc(),
)
Index(
    "ix_memories_subject_state_updated",
    MemoryRow.subject_pk,
    MemoryRow.state,
    MemoryRow.updated_at.desc(),
)
Index(
    "ix_memories_subject_scope_state",
    MemoryRow.subject_pk,
    MemoryRow.scope,
    MemoryRow.scope_value,
    MemoryRow.state,
)
Index(
    "uq_memories_active_slot",
    MemoryRow.subject_pk,
    MemoryRow.key,
    MemoryRow.scope,
    MemoryRow.scope_key,
    unique=True,
    sqlite_where=MemoryRow.state == "active",
    postgresql_where=MemoryRow.state == "active",
)
Index(
    "ix_observations_subject_dimension_occurred",
    FeatureObservationRow.subject_pk,
    FeatureObservationRow.dimension,
    FeatureObservationRow.value_key,
    FeatureObservationRow.occurred_at.desc(),
)
Index(
    "ix_states_subject_dimension_long",
    FeatureStateRow.subject_pk,
    FeatureStateRow.dimension,
    FeatureStateRow.long_term_score.desc(),
)
Index(
    "ix_states_subject_dimension_short",
    FeatureStateRow.subject_pk,
    FeatureStateRow.dimension,
    FeatureStateRow.short_term_score.desc(),
)
Index(
    "ix_snapshots_subject_version",
    ProfileSnapshotRow.subject_pk,
    ProfileSnapshotRow.version.desc(),
)
Index(
    "ix_runs_subject_started",
    ProcessingRunRow.subject_pk,
    ProcessingRunRow.started_at.desc(),
)
