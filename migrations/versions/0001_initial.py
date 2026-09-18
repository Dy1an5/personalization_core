"""Create the initial persistence schema.

This migration is deliberately self-contained. Later ORM metadata changes must
be represented by a new migration rather than changing this historical schema.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _uuid() -> TypeEngine:
    return sa.String(length=36).with_variant(
        postgresql.UUID(as_uuid=True), "postgresql"
    )


def _json() -> TypeEngine:
    return sa.Text().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("external_subject_id", sa.String(200), nullable=False),
        sa.Column("metadata", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_subjects"),
        sa.UniqueConstraint(
            "tenant_id",
            "namespace",
            "external_subject_id",
            name="uq_subjects_tenant_id",
        ),
    )
    op.create_table(
        "entities",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("attributes", _json(), nullable=False),
        sa.Column("content_text", sa.Text()),
        sa.Column("content_hash", sa.String(200)),
        sa.Column("schema_version", sa.String(100), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_entities"),
        sa.UniqueConstraint(
            "subject_pk", "entity_type", "external_id", name="uq_entities_subject_pk"
        ),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_entities_subject_pk_subjects",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "events",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100)),
        sa.Column("entity_external_id", sa.String(200)),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("polarity", sa.String(20), nullable=False),
        sa.Column("properties", _json(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.UniqueConstraint(
            "subject_pk", "source", "idempotency_key", name="uq_events_subject_pk"
        ),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_events_subject_pk_subjects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_pk", "entity_type", "entity_external_id"],
            ["entities.subject_pk", "entities.entity_type", "entities.external_id"],
            name="fk_events_subject_pk_entities",
            ondelete="NO ACTION",
        ),
        sa.CheckConstraint(
            "(entity_type IS NULL AND entity_external_id IS NULL) OR "
            "(entity_type IS NOT NULL AND entity_external_id IS NOT NULL)",
            name="ck_events_event_entity_pair",
        ),
    )
    op.create_table(
        "evidence",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_ref", sa.String(200), nullable=False),
        sa.Column("event_id", _uuid()),
        sa.Column("excerpt", sa.String(2000)),
        sa.Column("metadata", _json(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
        sa.UniqueConstraint(
            "subject_pk", "source_type", "source_ref", name="uq_evidence_subject_pk"
        ),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_evidence_subject_pk_subjects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name="fk_evidence_event_id_events",
            ondelete="NO ACTION",
        ),
    )
    op.create_table(
        "memories",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_value", _json()),
        sa.Column("target_dimension", sa.String(100)),
        sa.Column("target_value_key", sa.String(200)),
        sa.Column("authority", sa.String(30), nullable=False),
        sa.Column("polarity", sa.String(20), nullable=False),
        sa.Column("scope", sa.String(30), nullable=False),
        sa.Column("scope_value", sa.String(200)),
        sa.Column("scope_key", sa.String(200), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_memories"),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_memories_subject_pk_subjects",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_memories_memory_confidence"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_memories_memory_revision"),
        sa.CheckConstraint(
            "scope_key IS NOT NULL", name="ck_memories_memory_scope_key"
        ),
    )
    op.create_table(
        "memory_evidence",
        sa.Column("memory_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.PrimaryKeyConstraint("memory_id", "evidence_id", name="pk_memory_evidence"),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memories.id"],
            name="fk_memory_evidence_memory_id_memories",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            name="fk_memory_evidence_evidence_id_evidence",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "memory_revisions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("memory_id", _uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", _json(), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("transition", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_memory_revisions"),
        sa.UniqueConstraint(
            "memory_id", "revision", name="uq_memory_revisions_memory_id"
        ),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_memory_revisions_subject_pk_subjects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memories.id"],
            name="fk_memory_revisions_memory_id_memories",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "feature_observations",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("value_key", sa.String(200), nullable=False),
        sa.Column("value", _json(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("polarity", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_event_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("extractor_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_feature_observations"),
        sa.UniqueConstraint(
            "source_event_id",
            "dimension",
            "value_key",
            "extractor_name",
            "extractor_version",
            name="uq_feature_observations_source_event_id",
        ),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_feature_observations_subject_pk_subjects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_event_id"],
            ["events.id"],
            name="fk_feature_observations_source_event_id_events",
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            name="fk_feature_observations_evidence_id_evidence",
            ondelete="NO ACTION",
        ),
    )
    op.create_table(
        "feature_states",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("value_key", sa.String(200), nullable=False),
        sa.Column("value", _json(), nullable=False),
        sa.Column("long_term_score", sa.Float(), nullable=False),
        sa.Column("short_term_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("positive_evidence_count", sa.Integer(), nullable=False),
        sa.Column("negative_evidence_count", sa.Integer(), nullable=False),
        sa.Column("neutral_evidence_count", sa.Integer(), nullable=False),
        sa.Column("first_evidence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aggregator_name", sa.String(100), nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_feature_states"),
        sa.UniqueConstraint(
            "subject_pk",
            "dimension",
            "value_key",
            "aggregator_name",
            name="uq_feature_states_subject_pk",
        ),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_feature_states_subject_pk_subjects",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "feature_state_evidence",
        sa.Column("feature_state_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.PrimaryKeyConstraint(
            "feature_state_id", "evidence_id", name="pk_feature_state_evidence"
        ),
        sa.ForeignKeyConstraint(
            ["feature_state_id"],
            ["feature_states.id"],
            name="fk_feature_state_evidence_feature_state_id_feature_states",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            name="fk_feature_state_evidence_evidence_id_evidence",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "profile_snapshots",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("source_watermark", sa.DateTime(timezone=True)),
        sa.Column("coverage", _json(), nullable=False),
        sa.Column("preferences", _json(), nullable=False),
        sa.Column("warnings", _json(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profile_snapshots"),
        sa.UniqueConstraint(
            "subject_pk", "version", name="uq_profile_snapshots_subject_pk"
        ),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_profile_snapshots_subject_pk_subjects",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "processing_runs",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.PrimaryKeyConstraint("id", name="pk_processing_runs"),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_processing_runs_subject_pk_subjects",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("subject_pk", _uuid(), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", _json(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.ForeignKeyConstraint(
            ["subject_pk"],
            ["subjects.id"],
            name="fk_audit_log_subject_pk_subjects",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_events_subject_occurred",
        "events",
        ["subject_pk", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_events_subject_type_occurred",
        "events",
        ["subject_pk", "event_type", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_memories_subject_state_updated",
        "memories",
        ["subject_pk", "state", sa.text("updated_at DESC")],
    )
    op.create_index(
        "ix_memories_subject_scope_state",
        "memories",
        ["subject_pk", "scope", "scope_value", "state"],
    )
    op.create_index(
        "uq_memories_active_slot",
        "memories",
        ["subject_pk", "key", "scope", "scope_key"],
        unique=True,
        sqlite_where=sa.text("state = 'active'"),
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_index(
        "ix_observations_subject_dimension_occurred",
        "feature_observations",
        ["subject_pk", "dimension", "value_key", sa.text("occurred_at ASC")],
    )
    op.create_index(
        "ix_states_subject_dimension_long",
        "feature_states",
        ["subject_pk", "dimension", sa.text("long_term_score DESC")],
    )
    op.create_index(
        "ix_states_subject_dimension_short",
        "feature_states",
        ["subject_pk", "dimension", sa.text("short_term_score DESC")],
    )
    op.create_index(
        "ix_snapshots_subject_version",
        "profile_snapshots",
        ["subject_pk", sa.text("version DESC")],
    )
    op.create_index(
        "ix_runs_subject_started",
        "processing_runs",
        ["subject_pk", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    for name, table in (
        ("ix_runs_subject_started", "processing_runs"),
        ("ix_snapshots_subject_version", "profile_snapshots"),
        ("ix_states_subject_dimension_short", "feature_states"),
        ("ix_states_subject_dimension_long", "feature_states"),
        ("ix_observations_subject_dimension_occurred", "feature_observations"),
        ("uq_memories_active_slot", "memories"),
        ("ix_memories_subject_scope_state", "memories"),
        ("ix_memories_subject_state_updated", "memories"),
        ("ix_events_subject_type_occurred", "events"),
        ("ix_events_subject_occurred", "events"),
    ):
        op.drop_index(name, table_name=table)
    for table in (
        "audit_log",
        "processing_runs",
        "profile_snapshots",
        "feature_state_evidence",
        "feature_states",
        "feature_observations",
        "memory_revisions",
        "memory_evidence",
        "memories",
        "evidence",
        "events",
        "entities",
        "subjects",
    ):
        op.drop_table(table)
