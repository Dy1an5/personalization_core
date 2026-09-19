from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4

from personalization_core.domain.entities import (
    Entity,
    EntityCreate,
    build_entity,
    merge_entity,
)
from personalization_core.domain.enums import EvidenceSourceType
from personalization_core.domain.errors import (
    DomainError,
    EntityNotFoundError,
    IdempotencyConflictError,
    InvalidArgumentError,
    SubjectDeletedError,
    SubjectNotFoundError,
    TenantScopeViolationError,
)
from personalization_core.domain.events import (
    Event,
    classify_idempotency,
)
from personalization_core.domain.evidence import Evidence, EvidenceCreate
from personalization_core.domain.identifiers import EntityRef, SubjectRef
from personalization_core.domain.types import JsonValue
from personalization_core.ports.audit_sink import AuditEvent, AuditSink, subject_digest
from personalization_core.ports.clock import Clock
from personalization_core.ports.repositories import EventFilter, Page
from personalization_core.ports.retention import RetentionHook
from personalization_core.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

from .dto import (
    BatchIngestionResult,
    BatchItemResult,
    BatchMode,
    EventIngestionInput,
    EventIngestionResult,
    EventIngestionStatus,
    EventPage,
)
from .subject_service import SubjectService


class EventService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        subject_service: SubjectService,
        audit_sink: AuditSink | None = None,
        retention_hook: RetentionHook | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._subject_service = subject_service
        self._audit_sink = audit_sink
        self._retention_hook = retention_hook

    async def _emit(
        self, subject: SubjectRef, action: str, **metadata: JsonValue
    ) -> None:
        if self._audit_sink is not None:
            await self._audit_sink.emit(
                AuditEvent(
                    subject=subject,
                    action=action,
                    occurred_at=self._clock.now(),
                    metadata={"scope_digest": subject_digest(subject), **metadata},
                )
            )

    async def upsert_entity(
        self,
        subject: SubjectRef,
        entity_input: EntityCreate,
    ) -> Entity:
        created_subject = False
        async with self._uow_factory() as uow:
            created_subject = await uow.subjects.get_by_ref(subject) is None
            await self._subject_service.ensure_in_uow(uow, subject)
            ref = EntityRef(
                subject=subject,
                entity_type=entity_input.entity_type,
                external_id=entity_input.external_id,
            )
            existing = await uow.entities.get_by_ref(ref)
            now = self._clock.now()
            if existing is None:
                entity = build_entity(subject, entity_input, now)
                await uow.entities.add(subject, entity)
            else:
                if existing.deleted_at is not None:
                    raise InvalidArgumentError("entity is deleted")
                entity = merge_entity(existing, entity_input, now)
                await uow.entities.update(subject, entity)
            await uow.commit()
        if created_subject:
            await self._emit(subject, "create", resource="subject")
        await self._emit(
            subject,
            "create" if existing is None else "update",
            resource="entity",
            entity_type=entity.entity_type,
            external_id=entity.external_id,
        )
        return entity

    async def ingest_event(
        self,
        subject: SubjectRef,
        event_input: EventIngestionInput,
    ) -> EventIngestionResult:
        try:
            created_subject = False
            async with self._uow_factory() as uow:
                created_subject = await uow.subjects.get_by_ref(subject) is None
                await self._subject_service.ensure_in_uow(uow, subject)
                result = await self._ingest_one_in_uow(uow, subject, event_input)
                await uow.commit()
        except InvalidArgumentError as error:
            return await self._retry_idempotency_race(subject, event_input, error)
        if created_subject:
            await self._emit(subject, "create", resource="subject")
        if result.status is EventIngestionStatus.CREATED:
            await self._emit(
                subject,
                "create",
                resource="event",
                event_type=result.event.event_type,
                source=result.event.source,
            )
            if self._retention_hook is not None:
                await self._retention_hook.on_event_write(
                    subject, result.event.occurred_at
                )
        return result

    async def _retry_idempotency_race(
        self,
        subject: SubjectRef,
        event_input: EventIngestionInput,
        original_error: InvalidArgumentError,
    ) -> EventIngestionResult:
        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            incoming = event_input.event
            existing = await uow.events.get_by_idempotency_key(
                subject, incoming.source, incoming.idempotency_key
            )
            if existing is None:
                raise original_error
            result = await self._replay_or_conflict(uow, subject, event_input, existing)
            await uow.commit()
            return result

    async def _ingest_one_in_uow(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        event_input: EventIngestionInput,
    ) -> EventIngestionResult:
        incoming = event_input.event
        existing = await uow.events.get_by_idempotency_key(
            subject, incoming.source, incoming.idempotency_key
        )
        if existing is not None:
            return await self._replay_or_conflict(uow, subject, event_input, existing)

        if incoming.entity is not None:
            if incoming.entity.subject != subject:
                raise TenantScopeViolationError(
                    "event entity does not belong to subject"
                )
            entity = await uow.entities.get_by_ref(incoming.entity)
            if entity is None or entity.deleted_at is not None:
                raise EntityNotFoundError("event entity does not exist")

        event = Event(
            id=uuid4(),
            subject=subject,
            event_type=incoming.event_type,
            entity=incoming.entity,
            source=incoming.source,
            idempotency_key=incoming.idempotency_key,
            value=incoming.value,
            polarity=incoming.polarity,
            properties=dict(incoming.properties),
            occurred_at=incoming.occurred_at,
            observed_at=self._clock.now(),
            schema_version=incoming.schema_version,
        )
        await uow.events.add(subject, event)
        evidence = self._build_event_evidence(
            subject, event, event_input.evidence, self._clock.now()
        )
        await uow.evidence.add(subject, evidence)
        return EventIngestionResult(
            status=EventIngestionStatus.CREATED,
            event=event,
            evidence=evidence,
        )

    async def _replay_or_conflict(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        event_input: EventIngestionInput,
        existing: Event,
    ) -> EventIngestionResult:
        decision = classify_idempotency(existing, subject, event_input.event)
        if decision.value == "conflict":
            raise IdempotencyConflictError(
                "event idempotency key has different content"
            )
        if decision.value != "replay":
            raise InvalidArgumentError("event idempotency scope mismatch")

        evidence_items = list(await uow.evidence.list_for_event(subject, existing.id))
        evidence = evidence_items[0] if evidence_items else None
        if evidence is None:
            evidence = self._build_event_evidence(
                subject, existing, None, self._clock.now()
            )
            await uow.evidence.add(subject, evidence)
        return EventIngestionResult(
            status=EventIngestionStatus.REPLAYED,
            event=existing,
            evidence=evidence,
        )

    def _build_event_evidence(
        self,
        subject: SubjectRef,
        event: Event,
        evidence_input: EvidenceCreate | None,
        created_at: datetime,
    ) -> Evidence:
        if evidence_input is None:
            source_type = EvidenceSourceType.EVENT
            source_ref = f"event:{event.id}"
            excerpt = None
            metadata: dict[str, JsonValue] = {
                "event_source": str(event.source),
                "idempotency_key": str(event.idempotency_key),
            }
            occurred_at = event.occurred_at
        else:
            source_type = evidence_input.source_type
            source_ref = evidence_input.source_ref
            excerpt = evidence_input.excerpt
            metadata = dict(evidence_input.metadata)
            occurred_at = evidence_input.occurred_at
        return Evidence(
            id=uuid4(),
            subject=subject,
            source_type=source_type,
            source_ref=source_ref,
            event_id=event.id,
            excerpt=excerpt,
            metadata=metadata,
            occurred_at=occurred_at,
            created_at=created_at,
        )

    async def ingest_batch(
        self,
        subject: SubjectRef,
        events: Sequence[EventIngestionInput],
        *,
        mode: BatchMode = BatchMode.ATOMIC,
    ) -> BatchIngestionResult:
        if not events:
            return self._make_batch_result(mode, [])
        if mode is BatchMode.BEST_EFFORT:
            items: list[BatchItemResult] = []
            for index, item in enumerate(events):
                try:
                    result = await self.ingest_event(subject, item)
                    items.append(self._item_from_result(index, result))
                except DomainError as error:
                    items.append(self._failed_item(index, error))
            return self._make_batch_result(mode, items)

        async with self._uow_factory() as uow:
            created_subject = await uow.subjects.get_by_ref(subject) is None
            await self._subject_service.ensure_in_uow(uow, subject)
            items = []
            for index, item in enumerate(events):
                result = await self._ingest_one_in_uow(uow, subject, item)
                items.append(self._item_from_result(index, result))
            await uow.commit()
        if created_subject:
            await self._emit(subject, "create", resource="subject")
        for item in items:
            if item.status is EventIngestionStatus.CREATED and item.event is not None:
                await self._emit(
                    subject,
                    "create",
                    resource="event",
                    event_type=item.event.event_type,
                    source=item.event.source,
                )
                if self._retention_hook is not None:
                    await self._retention_hook.on_event_write(
                        subject, item.event.occurred_at
                    )
        return self._make_batch_result(mode, items)

    @staticmethod
    def _item_from_result(index: int, result: EventIngestionResult) -> BatchItemResult:
        return BatchItemResult(
            index=index,
            status=result.status,
            event=result.event,
            evidence=result.evidence,
        )

    @staticmethod
    def _failed_item(index: int, error: DomainError) -> BatchItemResult:
        return BatchItemResult(
            index=index,
            status=EventIngestionStatus.FAILED,
            error_code=error.code,
            error_message=error.message,
        )

    @staticmethod
    def _make_batch_result(
        mode: BatchMode, items: Sequence[BatchItemResult]
    ) -> BatchIngestionResult:
        item_list = list(items)
        return BatchIngestionResult(
            mode=mode,
            items=item_list,
            created_count=sum(
                item.status is EventIngestionStatus.CREATED for item in item_list
            ),
            replayed_count=sum(
                item.status is EventIngestionStatus.REPLAYED for item in item_list
            ),
            failed_count=sum(
                item.status is EventIngestionStatus.FAILED for item in item_list
            ),
        )

    async def list_events(
        self,
        subject: SubjectRef,
        filters: EventFilter | None = None,
        page: Page | None = None,
    ) -> EventPage:
        active_filters = filters or EventFilter()
        active_page = page or Page()
        async with self._uow_factory() as uow:
            stored_subject = await uow.subjects.get_by_ref(subject)
            if stored_subject is None:
                raise SubjectNotFoundError("subject does not exist")
            if stored_subject.deleted_at is not None:
                raise SubjectDeletedError("subject is deleted")
            items = list(await uow.events.list(subject, active_filters, active_page))
            probe = await uow.events.list(
                subject,
                active_filters,
                Page(limit=1, offset=active_page.offset + active_page.limit),
            )
            has_more = bool(probe)
            result = EventPage(
                items=items,
                limit=active_page.limit,
                offset=active_page.offset,
                has_more=has_more,
                next_offset=(active_page.offset + len(items)) if has_more else None,
            )
            await uow.commit()
        await self._emit(
            subject,
            "search",
            resource="event",
            result_count=len(result.items),
            limit=result.limit,
            offset=result.offset,
        )
        return result
