"""Retain minimal purge audit records outside the subject foreign key graph."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine

revision = "0002_privacy_audit"
down_revision = "0001_initial"
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
        "purge_audit_log",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("scope_digest", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("metadata", _json(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_purge_audit_log"),
    )


def downgrade() -> None:
    op.drop_table("purge_audit_log")
