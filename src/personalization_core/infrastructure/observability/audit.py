from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from personalization_core.ports.audit_sink import (
    AuditEvent,
    AuditSink,
    sanitize_log_fields,
    subject_digest,
)

from ..persistence.sqlalchemy_models import (
    AuditLogRow,
    PurgeAuditLogRow,
    SubjectRow,
)


class SQLAlchemyAuditSink(AuditSink):
    """Persist sanitized audit events without coupling them to application UoWs."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def emit(self, event: AuditEvent) -> None:
        metadata = sanitize_log_fields(event.metadata)
        async with self._session_factory() as session:
            subject_pk = await session.scalar(
                select(SubjectRow.id).where(
                    SubjectRow.tenant_id == event.subject.tenant_id.root,
                    SubjectRow.namespace == event.subject.namespace.root,
                    SubjectRow.external_subject_id == event.subject.subject_id.root,
                )
            )
            if subject_pk is None and event.action == "purge":
                session.add(
                    PurgeAuditLogRow(
                        id=uuid4(),
                        scope_digest=subject_digest(event.subject),
                        occurred_at=event.occurred_at,
                        action=event.action,
                        metadata_json=metadata,
                    )
                )
            elif subject_pk is not None:
                session.add(
                    AuditLogRow(
                        id=uuid4(),
                        subject_pk=subject_pk,
                        action=event.action,
                        occurred_at=event.occurred_at,
                        metadata_json=metadata,
                    )
                )
            else:
                return
            await session.commit()
