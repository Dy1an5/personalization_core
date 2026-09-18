from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from personalization_core.domain.entities import Entity
from personalization_core.domain.enums import (
    EvidenceSourceType,
    MemoryAuthority,
    MemoryKind,
    MemoryScope,
    MemoryState,
    Polarity,
    ProfileStatus,
)
from personalization_core.domain.errors import (
    InvalidArgumentError,
    RevisionConflictError,
    TenantScopeViolationError,
)
from personalization_core.domain.events import Event
from personalization_core.domain.evidence import Evidence
from personalization_core.domain.features import FeatureObservation, FeatureState
from personalization_core.domain.identifiers import EntityRef, SubjectRef
from personalization_core.domain.jobs import ProcessingRun, ProcessingStatus
from personalization_core.domain.memory import MemoryRecord, PreferenceTarget
from personalization_core.domain.profile import ProfileSnapshot
from personalization_core.domain.subjects import Subject
from personalization_core.ports.repositories import (
    EntityRepository,
    EventFilter,
    EventRepository,
    EvidenceRepository,
    FeatureRepository,
    FeatureStateFilter,
    MemoryFilter,
    MemoryRepository,
    Page,
    ProcessingRunRepository,
    ProfileRepository,
    SubjectRepository,
)

from .sqlalchemy_models import (
    EntityRow,
    EventRow,
    EvidenceRow,
    FeatureObservationRow,
    FeatureStateEvidenceRow,
    FeatureStateRow,
    MemoryEvidenceRow,
    MemoryRow,
    ProcessingRunRow,
    ProfileSnapshotRow,
    SubjectRow,
)


def _ensure_scope(expected: SubjectRef, actual: SubjectRef) -> None:
    if expected != actual:
        raise TenantScopeViolationError("object does not belong to requested subject")


def _scope_key(memory: MemoryRecord) -> str:
    return (
        "" if memory.scope == MemoryScope.GLOBAL else (memory.scope_value or "").strip()
    )


def _ref(row: SubjectRow) -> SubjectRef:
    from personalization_core.domain.identifiers import Namespace, SubjectId, TenantId

    return SubjectRef(
        tenant_id=TenantId(row.tenant_id),
        namespace=Namespace(row.namespace),
        subject_id=SubjectId(row.external_subject_id),
    )


def _subject(row: SubjectRow) -> Subject:
    return Subject(
        id=row.id,
        ref=_ref(row),
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _entity(row: EntityRow, subject: SubjectRef) -> Entity:
    item = Entity()
    item.id = row.id
    item.subject = subject
    item.entity_type = row.entity_type
    item.external_id = row.external_id
    item.attributes = dict(row.attributes or {})
    item.content_text = row.content_text
    item.content_hash = row.content_hash
    item.schema_version = row.schema_version
    item.first_seen_at = row.first_seen_at
    item.last_seen_at = row.last_seen_at
    item.deleted_at = row.deleted_at
    return item


def _event(row: EventRow, subject: SubjectRef) -> Event:
    entity = None
    if row.entity_type is not None:
        entity = EntityRef(
            subject=subject,
            entity_type=row.entity_type,
            external_id=row.entity_external_id or "",
        )
    return Event(
        id=row.id,
        subject=subject,
        event_type=row.event_type,
        entity=entity,
        source=row.source,
        idempotency_key=row.idempotency_key,
        value=row.value,
        polarity=Polarity(row.polarity),
        properties=dict(row.properties or {}),
        occurred_at=row.occurred_at,
        observed_at=row.observed_at,
        schema_version=row.schema_version,
    )


def _evidence(row: EvidenceRow, subject: SubjectRef) -> Evidence:
    return Evidence(
        id=row.id,
        subject=subject,
        source_type=EvidenceSourceType(row.source_type),
        source_ref=row.source_ref,
        event_id=row.event_id,
        excerpt=row.excerpt,
        metadata=dict(row.metadata_json or {}),
        occurred_at=row.occurred_at,
        created_at=row.created_at,
    )


def _memory(row: MemoryRow, subject: SubjectRef) -> MemoryRecord:
    target = None
    if row.target_dimension is not None:
        target = PreferenceTarget(
            dimension=row.target_dimension, value_key=row.target_value_key or ""
        )
    return MemoryRecord(
        id=row.id,
        subject=subject,
        key=row.key,
        kind=MemoryKind(row.kind),
        content=row.content,
        structured_value=row.structured_value,
        target=target,
        authority=MemoryAuthority(row.authority),
        polarity=Polarity(row.polarity),
        scope=MemoryScope(row.scope),
        scope_value=row.scope_value,
        confidence=row.confidence,
        state=MemoryState(row.state),
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        evidence_count=row.evidence_count,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _observation(row: FeatureObservationRow, subject: SubjectRef) -> FeatureObservation:
    return FeatureObservation(
        id=row.id,
        subject=subject,
        dimension=row.dimension,
        value_key=row.value_key,
        value=dict(row.value or {}),
        score=row.score,
        polarity=Polarity(row.polarity),
        confidence=row.confidence,
        occurred_at=row.occurred_at,
        source_event_id=row.source_event_id,
        evidence_id=row.evidence_id,
        extractor_name=row.extractor_name,
        extractor_version=row.extractor_version,
        created_at=row.created_at,
    )


def _run(row: ProcessingRunRow, subject: SubjectRef) -> ProcessingRun:
    return ProcessingRun(
        id=row.id,
        subject=subject,
        operation=row.operation,
        status=ProcessingStatus(row.status),
        algorithm_version=row.algorithm_version,
        started_at=row.started_at,
        finished_at=row.finished_at,
        processed_count=row.processed_count,
        failed_count=row.failed_count,
        error_code=row.error_code,
    )


async def _subject_pk(session: AsyncSession, ref: SubjectRef) -> UUID | None:
    stmt = select(SubjectRow.id).where(
        SubjectRow.tenant_id == ref.tenant_id.root,
        SubjectRow.namespace == ref.namespace.root,
        SubjectRow.external_subject_id == ref.subject_id.root,
        SubjectRow.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise InvalidArgumentError("persistence constraint violation") from exc


class SQLAlchemySubjectRepository(SubjectRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_ref(self, ref: SubjectRef) -> Subject | None:
        row = await self.session.scalar(
            select(SubjectRow).where(
                SubjectRow.tenant_id == ref.tenant_id.root,
                SubjectRow.namespace == ref.namespace.root,
                SubjectRow.external_subject_id == ref.subject_id.root,
            )
        )
        return _subject(row) if row else None

    async def get(self, ref: SubjectRef, subject_id: UUID) -> Subject | None:
        row = await self.session.scalar(
            select(SubjectRow).where(SubjectRow.id == subject_id)
        )
        if row is None or _ref(row) != ref:
            return None
        return _subject(row)

    async def add(self, subject: Subject) -> None:
        self.session.add(
            SubjectRow(
                id=subject.id,
                tenant_id=subject.ref.tenant_id.root,
                namespace=subject.ref.namespace.root,
                external_subject_id=subject.ref.subject_id.root,
                metadata_json=subject.metadata,
                created_at=subject.created_at,
                updated_at=subject.updated_at,
                deleted_at=subject.deleted_at,
            )
        )
        await _flush(self.session)

    async def update(self, subject: Subject) -> None:
        row = await self.session.scalar(
            select(SubjectRow).where(SubjectRow.id == subject.id)
        )
        if row is None or _ref(row) != subject.ref:
            raise InvalidArgumentError("subject does not exist")
        row.metadata_json = subject.metadata
        row.updated_at = subject.updated_at
        row.deleted_at = subject.deleted_at
        await _flush(self.session)


class SQLAlchemyEntityRepository(EntityRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, subject: SubjectRef, entity_id: UUID) -> Entity | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(EntityRow).where(
                EntityRow.id == entity_id, EntityRow.subject_pk == pk
            )
        )
        return _entity(row, subject) if row else None

    async def get_by_ref(self, ref: EntityRef) -> Entity | None:
        pk = await _subject_pk(self.session, ref.subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(EntityRow).where(
                EntityRow.subject_pk == pk,
                EntityRow.entity_type == ref.entity_type,
                EntityRow.external_id == ref.external_id,
            )
        )
        return _entity(row, ref.subject) if row else None

    async def add(self, subject: SubjectRef, entity: Entity) -> None:
        _ensure_scope(subject, entity.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("subject does not exist")
        self.session.add(
            EntityRow(
                id=entity.id,
                subject_pk=pk,
                entity_type=entity.entity_type,
                external_id=entity.external_id,
                attributes=entity.attributes,
                content_text=entity.content_text,
                content_hash=entity.content_hash,
                schema_version=entity.schema_version,
                first_seen_at=entity.first_seen_at,
                last_seen_at=entity.last_seen_at,
                deleted_at=entity.deleted_at,
            )
        )
        await _flush(self.session)

    async def update(self, subject: SubjectRef, entity: Entity) -> None:
        _ensure_scope(subject, entity.subject)
        pk = await _subject_pk(self.session, subject)
        row = (
            await self.session.scalar(
                select(EntityRow).where(
                    EntityRow.id == entity.id, EntityRow.subject_pk == pk
                )
            )
            if pk
            else None
        )
        if row is None:
            raise InvalidArgumentError("entity does not exist")
        for key in (
            "entity_type",
            "external_id",
            "attributes",
            "content_text",
            "content_hash",
            "schema_version",
            "first_seen_at",
            "last_seen_at",
            "deleted_at",
        ):
            setattr(row, key, getattr(entity, key))
        await _flush(self.session)

    async def list(self, subject: SubjectRef, page: Page) -> Sequence[Entity]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        rows = (
            await self.session.scalars(
                select(EntityRow)
                .where(EntityRow.subject_pk == pk)
                .order_by(EntityRow.entity_type, EntityRow.external_id, EntityRow.id)
                .offset(page.offset)
                .limit(page.limit)
            )
        ).all()
        return [_entity(row, subject) for row in rows]


class SQLAlchemyEventRepository(EventRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, subject: SubjectRef, event_id: UUID) -> Event | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(EventRow).where(EventRow.id == event_id, EventRow.subject_pk == pk)
        )
        return _event(row, subject) if row else None

    async def get_by_idempotency_key(
        self, subject: SubjectRef, source: str, idempotency_key: str
    ) -> Event | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(EventRow).where(
                EventRow.subject_pk == pk,
                EventRow.source == source,
                EventRow.idempotency_key == idempotency_key,
            )
        )
        return _event(row, subject) if row else None

    async def add(self, subject: SubjectRef, event: Event) -> None:
        _ensure_scope(subject, event.subject)
        if event.entity is not None:
            _ensure_scope(subject, event.entity.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("subject does not exist")
        self.session.add(
            EventRow(
                id=event.id,
                subject_pk=pk,
                event_type=event.event_type,
                entity_type=event.entity.entity_type if event.entity else None,
                entity_external_id=event.entity.external_id if event.entity else None,
                source=event.source,
                idempotency_key=event.idempotency_key,
                value=event.value,
                polarity=event.polarity.value,
                properties=event.properties,
                occurred_at=event.occurred_at,
                observed_at=event.observed_at,
                schema_version=event.schema_version,
            )
        )
        await _flush(self.session)

    async def list(
        self, subject: SubjectRef, filters: EventFilter, page: Page
    ) -> Sequence[Event]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        stmt = select(EventRow).where(EventRow.subject_pk == pk)
        if filters.event_type is not None:
            stmt = stmt.where(EventRow.event_type == filters.event_type)
        rows = (
            await self.session.scalars(
                stmt.order_by(EventRow.occurred_at.desc(), EventRow.id.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        ).all()
        return [_event(row, subject) for row in rows]


class SQLAlchemyEvidenceRepository(EvidenceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, subject: SubjectRef, evidence_id: UUID) -> Evidence | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(EvidenceRow).where(
                EvidenceRow.id == evidence_id, EvidenceRow.subject_pk == pk
            )
        )
        return _evidence(row, subject) if row else None

    async def get_by_source(
        self, subject: SubjectRef, source_type: str, source_ref: str
    ) -> Evidence | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(EvidenceRow).where(
                EvidenceRow.subject_pk == pk,
                EvidenceRow.source_type == source_type,
                EvidenceRow.source_ref == source_ref,
            )
        )
        return _evidence(row, subject) if row else None

    async def add(self, subject: SubjectRef, evidence: Evidence) -> None:
        _ensure_scope(subject, evidence.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("subject does not exist")
        if (
            evidence.event_id is not None
            and await self.session.scalar(
                select(EventRow.id).where(
                    EventRow.id == evidence.event_id, EventRow.subject_pk == pk
                )
            )
            is None
        ):
            raise InvalidArgumentError("event does not belong to subject")
        self.session.add(
            EvidenceRow(
                id=evidence.id,
                subject_pk=pk,
                source_type=evidence.source_type.value,
                source_ref=evidence.source_ref,
                event_id=evidence.event_id,
                excerpt=evidence.excerpt,
                metadata_json=evidence.metadata,
                occurred_at=evidence.occurred_at,
                created_at=evidence.created_at,
            )
        )
        await _flush(self.session)

    async def list_for_event(
        self, subject: SubjectRef, event_id: UUID
    ) -> Sequence[Evidence]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        rows = (
            await self.session.scalars(
                select(EvidenceRow)
                .where(EvidenceRow.subject_pk == pk, EvidenceRow.event_id == event_id)
                .order_by(EvidenceRow.created_at, EvidenceRow.id)
            )
        ).all()
        return [_evidence(row, subject) for row in rows]


def _memory_values(memory: MemoryRecord) -> dict[str, Any]:
    return {
        "key": memory.key,
        "kind": memory.kind.value,
        "content": memory.content,
        "structured_value": memory.structured_value,
        "target_dimension": memory.target.dimension if memory.target else None,
        "target_value_key": memory.target.value_key if memory.target else None,
        "authority": memory.authority.value,
        "polarity": memory.polarity.value,
        "scope": memory.scope.value,
        "scope_value": memory.scope_value,
        "scope_key": _scope_key(memory),
        "confidence": memory.confidence,
        "state": memory.state.value,
        "valid_from": memory.valid_from,
        "valid_until": memory.valid_until,
        "evidence_count": memory.evidence_count,
        "revision": memory.revision,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
        "deleted_at": memory.deleted_at,
    }


class SQLAlchemyMemoryRepository(MemoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, subject: SubjectRef, memory_id: UUID) -> MemoryRecord | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(MemoryRow).where(
                MemoryRow.id == memory_id, MemoryRow.subject_pk == pk
            )
        )
        return _memory(row, subject) if row else None

    async def add(self, subject: SubjectRef, memory: MemoryRecord) -> None:
        _ensure_scope(subject, memory.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("subject does not exist")
        self.session.add(
            MemoryRow(id=memory.id, subject_pk=pk, **_memory_values(memory))
        )
        await _flush(self.session)

    async def update(
        self, subject: SubjectRef, memory: MemoryRecord, expected_revision: int
    ) -> None:
        _ensure_scope(subject, memory.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("memory does not exist")
        current_revision = await self.session.scalar(
            select(MemoryRow.revision).where(
                MemoryRow.id == memory.id, MemoryRow.subject_pk == pk
            )
        )
        if current_revision is None:
            raise InvalidArgumentError("memory does not exist")
        if current_revision != expected_revision:
            raise RevisionConflictError(
                expected_revision=expected_revision, actual_revision=current_revision
            )
        if memory.revision != expected_revision + 1:
            raise InvalidArgumentError("updated memory must increment revision once")
        result = await self.session.execute(
            update(MemoryRow)
            .where(
                MemoryRow.id == memory.id,
                MemoryRow.subject_pk == pk,
                MemoryRow.revision == expected_revision,
            )
            .values(**_memory_values(memory))
        )
        if getattr(result, "rowcount", 0) == 0:
            actual = await self.session.scalar(
                select(MemoryRow.revision).where(
                    MemoryRow.id == memory.id, MemoryRow.subject_pk == pk
                )
            )
            if actual is None:
                raise InvalidArgumentError("memory does not exist")
            raise RevisionConflictError(
                expected_revision=expected_revision, actual_revision=actual
            )
        await _flush(self.session)

    async def list(
        self, subject: SubjectRef, filters: MemoryFilter, page: Page
    ) -> Sequence[MemoryRecord]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        stmt = select(MemoryRow).where(MemoryRow.subject_pk == pk)
        if filters.states is not None:
            stmt = stmt.where(
                MemoryRow.state.in_([state.value for state in filters.states])
            )
        if filters.key is not None:
            stmt = stmt.where(MemoryRow.key == filters.key)
        rows = (
            await self.session.scalars(
                stmt.order_by(MemoryRow.updated_at.desc(), MemoryRow.id.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        ).all()
        return [_memory(row, subject) for row in rows]

    async def bind_evidence(
        self, subject: SubjectRef, memory_id: UUID, evidence_id: UUID
    ) -> None:
        pk = await _subject_pk(self.session, subject)
        if (
            pk is None
            or await self.session.scalar(
                select(MemoryRow.id).where(
                    MemoryRow.id == memory_id, MemoryRow.subject_pk == pk
                )
            )
            is None
        ):
            raise InvalidArgumentError("memory does not exist")
        if (
            await self.session.scalar(
                select(EvidenceRow.id).where(
                    EvidenceRow.id == evidence_id, EvidenceRow.subject_pk == pk
                )
            )
            is None
        ):
            raise InvalidArgumentError("evidence does not exist")
        exists = await self.session.scalar(
            select(MemoryEvidenceRow.memory_id).where(
                MemoryEvidenceRow.memory_id == memory_id,
                MemoryEvidenceRow.evidence_id == evidence_id,
            )
        )
        if exists is None:
            self.session.add(
                MemoryEvidenceRow(memory_id=memory_id, evidence_id=evidence_id)
            )
            await _flush(self.session)

    async def list_evidence_ids(
        self, subject: SubjectRef, memory_id: UUID
    ) -> Sequence[UUID]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        rows = (
            await self.session.scalars(
                select(MemoryEvidenceRow.evidence_id)
                .join(MemoryRow, MemoryRow.id == MemoryEvidenceRow.memory_id)
                .where(
                    MemoryEvidenceRow.memory_id == memory_id, MemoryRow.subject_pk == pk
                )
                .order_by(MemoryEvidenceRow.evidence_id)
            )
        ).all()
        return list(rows)


class SQLAlchemyFeatureRepository(FeatureRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_observation(
        self, subject: SubjectRef, observation_id: UUID
    ) -> FeatureObservation | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(FeatureObservationRow).where(
                FeatureObservationRow.id == observation_id,
                FeatureObservationRow.subject_pk == pk,
            )
        )
        return _observation(row, subject) if row else None

    async def add_observation(
        self, subject: SubjectRef, observation: FeatureObservation
    ) -> None:
        _ensure_scope(subject, observation.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("subject does not exist")
        if (
            await self.session.scalar(
                select(EventRow.id).where(
                    EventRow.id == observation.source_event_id,
                    EventRow.subject_pk == pk,
                )
            )
            is None
        ):
            raise InvalidArgumentError("source event does not exist")
        if (
            await self.session.scalar(
                select(EvidenceRow.id).where(
                    EvidenceRow.id == observation.evidence_id,
                    EvidenceRow.subject_pk == pk,
                )
            )
            is None
        ):
            raise InvalidArgumentError("evidence does not exist")
        self.session.add(
            FeatureObservationRow(
                id=observation.id,
                subject_pk=pk,
                dimension=observation.dimension,
                value_key=observation.value_key,
                value=observation.value,
                score=observation.score,
                polarity=observation.polarity.value,
                confidence=observation.confidence,
                occurred_at=observation.occurred_at,
                source_event_id=observation.source_event_id,
                evidence_id=observation.evidence_id,
                extractor_name=observation.extractor_name,
                extractor_version=observation.extractor_version,
                created_at=observation.created_at,
            )
        )
        await _flush(self.session)

    async def list_observations(
        self, subject: SubjectRef, dimension: str | None = None
    ) -> Sequence[FeatureObservation]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        stmt = select(FeatureObservationRow).where(
            FeatureObservationRow.subject_pk == pk
        )
        if dimension is not None:
            stmt = stmt.where(FeatureObservationRow.dimension == dimension)
        rows = (
            await self.session.scalars(
                stmt.order_by(
                    FeatureObservationRow.occurred_at, FeatureObservationRow.id
                )
            )
        ).all()
        return [_observation(row, subject) for row in rows]

    async def get_state(
        self, subject: SubjectRef, dimension: str, value_key: str, aggregator_name: str
    ) -> FeatureState | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(FeatureStateRow).where(
                FeatureStateRow.subject_pk == pk,
                FeatureStateRow.dimension == dimension,
                FeatureStateRow.value_key == value_key,
                FeatureStateRow.aggregator_name == aggregator_name,
            )
        )
        if row is None:
            return None
        evidence_ids = list(
            (
                await self.session.scalars(
                    select(FeatureStateEvidenceRow.evidence_id)
                    .where(FeatureStateEvidenceRow.feature_state_id == row.id)
                    .order_by(FeatureStateEvidenceRow.evidence_id)
                )
            ).all()
        )
        return FeatureState(
            subject=subject,
            dimension=row.dimension,
            value_key=row.value_key,
            value=dict(row.value or {}),
            long_term_score=row.long_term_score,
            short_term_score=row.short_term_score,
            confidence=row.confidence,
            positive_evidence_count=row.positive_evidence_count,
            negative_evidence_count=row.negative_evidence_count,
            neutral_evidence_count=row.neutral_evidence_count,
            first_evidence_at=row.first_evidence_at,
            last_evidence_at=row.last_evidence_at,
            evidence_ids=evidence_ids,
            aggregator_name=row.aggregator_name,
            algorithm_version=row.algorithm_version,
            updated_at=row.updated_at,
        )

    async def upsert_state(self, subject: SubjectRef, state: FeatureState) -> None:
        _ensure_scope(subject, state.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("subject does not exist")
        for evidence_id in state.evidence_ids:
            if (
                await self.session.scalar(
                    select(EvidenceRow.id).where(
                        EvidenceRow.id == evidence_id, EvidenceRow.subject_pk == pk
                    )
                )
                is None
            ):
                raise InvalidArgumentError("evidence does not exist")
        row = await self.session.scalar(
            select(FeatureStateRow).where(
                FeatureStateRow.subject_pk == pk,
                FeatureStateRow.dimension == state.dimension,
                FeatureStateRow.value_key == state.value_key,
                FeatureStateRow.aggregator_name == state.aggregator_name,
            )
        )
        values = dict(
            subject_pk=pk,
            dimension=state.dimension,
            value_key=state.value_key,
            value=state.value,
            long_term_score=state.long_term_score,
            short_term_score=state.short_term_score,
            confidence=state.confidence,
            positive_evidence_count=state.positive_evidence_count,
            negative_evidence_count=state.negative_evidence_count,
            neutral_evidence_count=state.neutral_evidence_count,
            first_evidence_at=state.first_evidence_at,
            last_evidence_at=state.last_evidence_at,
            aggregator_name=state.aggregator_name,
            algorithm_version=state.algorithm_version,
            updated_at=state.updated_at,
        )
        if row is None:
            row = FeatureStateRow(id=uuid4(), **values)
            self.session.add(row)
        else:
            for key, value in values.items():
                if key != "subject_pk":
                    setattr(row, key, value)
            await self.session.execute(
                delete(FeatureStateEvidenceRow).where(
                    FeatureStateEvidenceRow.feature_state_id == row.id
                )
            )
        await _flush(self.session)
        for evidence_id in state.evidence_ids:
            self.session.add(
                FeatureStateEvidenceRow(
                    feature_state_id=row.id, evidence_id=evidence_id
                )
            )
        await _flush(self.session)

    async def list_states(
        self, subject: SubjectRef, filters: FeatureStateFilter
    ) -> Sequence[FeatureState]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        stmt = select(FeatureStateRow).where(FeatureStateRow.subject_pk == pk)
        if filters.dimension is not None:
            stmt = stmt.where(FeatureStateRow.dimension == filters.dimension)
        rows = (
            await self.session.scalars(
                stmt.order_by(
                    FeatureStateRow.dimension,
                    FeatureStateRow.long_term_score.desc(),
                    FeatureStateRow.value_key,
                )
            )
        ).all()
        result: list[FeatureState] = []
        for row in rows:
            item = await self.get_state(
                subject, row.dimension, row.value_key, row.aggregator_name
            )
            if item is not None:
                result.append(item)
        return result


class SQLAlchemyProfileRepository(ProfileRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_domain(
        self, row: ProfileSnapshotRow, subject: SubjectRef
    ) -> ProfileSnapshot:
        return ProfileSnapshot.model_validate(
            {
                "id": row.id,
                "subject": subject,
                "version": row.version,
                "status": ProfileStatus(row.status),
                "generated_at": row.generated_at,
                "algorithm_version": row.algorithm_version,
                "source_watermark": row.source_watermark,
                "coverage": row.coverage,
                "preferences": row.preferences,
                "warnings": row.warnings,
            },
            strict=False,
        )

    async def add(self, subject: SubjectRef, snapshot: ProfileSnapshot) -> None:
        _ensure_scope(subject, snapshot.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("subject does not exist")
        latest = await self.session.scalar(
            select(ProfileSnapshotRow.version)
            .where(ProfileSnapshotRow.subject_pk == pk)
            .order_by(ProfileSnapshotRow.version.desc())
            .limit(1)
        )
        if latest is not None and snapshot.version <= latest:
            raise InvalidArgumentError("profile version must increase")
        self.session.add(
            ProfileSnapshotRow(
                id=snapshot.id,
                subject_pk=pk,
                version=snapshot.version,
                status=snapshot.status.value,
                generated_at=snapshot.generated_at,
                algorithm_version=snapshot.algorithm_version,
                source_watermark=snapshot.source_watermark,
                coverage=snapshot.coverage.model_dump(mode="json"),
                preferences=[
                    item.model_dump(mode="json") for item in snapshot.preferences
                ],
                warnings=list(snapshot.warnings),
            )
        )
        await _flush(self.session)

    async def get_version(
        self, subject: SubjectRef, version: int
    ) -> ProfileSnapshot | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(ProfileSnapshotRow).where(
                ProfileSnapshotRow.subject_pk == pk,
                ProfileSnapshotRow.version == version,
            )
        )
        return self._to_domain(row, subject) if row else None

    async def get_latest(self, subject: SubjectRef) -> ProfileSnapshot | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(ProfileSnapshotRow)
            .where(ProfileSnapshotRow.subject_pk == pk)
            .order_by(ProfileSnapshotRow.version.desc())
            .limit(1)
        )
        return self._to_domain(row, subject) if row else None

    async def list(self, subject: SubjectRef, page: Page) -> Sequence[ProfileSnapshot]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        rows = (
            await self.session.scalars(
                select(ProfileSnapshotRow)
                .where(ProfileSnapshotRow.subject_pk == pk)
                .order_by(ProfileSnapshotRow.version.desc(), ProfileSnapshotRow.id)
                .offset(page.offset)
                .limit(page.limit)
            )
        ).all()
        return [self._to_domain(row, subject) for row in rows]


class SQLAlchemyProcessingRunRepository(ProcessingRunRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, subject: SubjectRef, run_id: UUID) -> ProcessingRun | None:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return None
        row = await self.session.scalar(
            select(ProcessingRunRow).where(
                ProcessingRunRow.subject_pk == pk, ProcessingRunRow.id == run_id
            )
        )
        return _run(row, subject) if row else None

    async def add(self, subject: SubjectRef, run: ProcessingRun) -> None:
        _ensure_scope(subject, run.subject)
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            raise InvalidArgumentError("subject does not exist")
        self.session.add(
            ProcessingRunRow(
                id=run.id,
                subject_pk=pk,
                operation=run.operation,
                status=run.status.value,
                algorithm_version=run.algorithm_version,
                started_at=run.started_at,
                finished_at=run.finished_at,
                processed_count=run.processed_count,
                failed_count=run.failed_count,
                error_code=run.error_code,
            )
        )
        await _flush(self.session)

    async def update(self, subject: SubjectRef, run: ProcessingRun) -> None:
        _ensure_scope(subject, run.subject)
        pk = await _subject_pk(self.session, subject)
        row = (
            await self.session.scalar(
                select(ProcessingRunRow).where(
                    ProcessingRunRow.subject_pk == pk, ProcessingRunRow.id == run.id
                )
            )
            if pk
            else None
        )
        if row is None:
            raise InvalidArgumentError("processing run does not exist")
        for key in (
            "operation",
            "status",
            "algorithm_version",
            "started_at",
            "finished_at",
            "processed_count",
            "failed_count",
            "error_code",
        ):
            value = getattr(run, key)
            setattr(
                row, key, value.value if isinstance(value, ProcessingStatus) else value
            )
        await _flush(self.session)

    async def list(self, subject: SubjectRef, page: Page) -> Sequence[ProcessingRun]:
        pk = await _subject_pk(self.session, subject)
        if pk is None:
            return []
        rows = (
            await self.session.scalars(
                select(ProcessingRunRow)
                .where(ProcessingRunRow.subject_pk == pk)
                .order_by(
                    ProcessingRunRow.started_at.desc(), ProcessingRunRow.id.desc()
                )
                .offset(page.offset)
                .limit(page.limit)
            )
        ).all()
        return [_run(row, subject) for row in rows]
