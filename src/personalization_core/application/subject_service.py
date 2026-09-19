from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from personalization_core.domain.entities import Entity
from personalization_core.domain.errors import (
    InvalidArgumentError,
    PurgeConfirmationRequiredError,
    SubjectDeletedError,
    SubjectNotFoundError,
)
from personalization_core.domain.events import Event
from personalization_core.domain.evidence import Evidence
from personalization_core.domain.features import FeatureObservation
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.jobs import ProcessingRun
from personalization_core.domain.memory import MemoryRecord, MemoryRevision
from personalization_core.domain.profile import ProfileSnapshot
from personalization_core.domain.subjects import Subject
from personalization_core.domain.types import JsonValue
from personalization_core.ports.audit_sink import AuditEvent, AuditSink, subject_digest
from personalization_core.ports.clock import Clock
from personalization_core.ports.full_text_search import FullTextIndex
from personalization_core.ports.purge_tokens import PurgeToken, PurgeTokenStore
from personalization_core.ports.repositories import (
    EventFilter,
    FeatureStateFilter,
    MemoryFilter,
    Page,
)
from personalization_core.ports.retention import RetentionHook
from personalization_core.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from personalization_core.ports.vector_index import VectorIndex

from .dto import (
    ExportEntity,
    MemoryEvidenceBinding,
    PurgeResult,
    SubjectExport,
)


class SubjectService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        token_store: PurgeTokenStore | None = None,
        full_text_index: FullTextIndex | None = None,
        vector_index: VectorIndex | None = None,
        audit_sink: AuditSink | None = None,
        retention_hook: RetentionHook | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._token_store = token_store
        self._full_text_index = full_text_index
        self._vector_index = vector_index
        self._audit_sink = audit_sink
        self._retention_hook = retention_hook

    async def _emit(self, ref: SubjectRef, action: str, **metadata: JsonValue) -> None:
        if self._audit_sink is not None:
            await self._audit_sink.emit(
                AuditEvent(
                    subject=ref,
                    action=action,
                    occurred_at=self._clock.now(),
                    metadata={"scope_digest": subject_digest(ref), **metadata},
                )
            )

    async def create_or_get_subject(
        self,
        ref: SubjectRef,
        metadata: dict[str, JsonValue] | None = None,
    ) -> Subject:
        created = False
        try:
            async with self._uow_factory() as uow:
                existing = await uow.subjects.get_by_ref(ref)
                subject = await self.ensure_in_uow(uow, ref, metadata)
                created = existing is None
                await uow.commit()
        except InvalidArgumentError as original_error:
            async with self._uow_factory() as uow:
                existing = await uow.subjects.get_by_ref(ref)
                if existing is None:
                    raise original_error from None
                if existing.deleted_at is not None:
                    raise SubjectDeletedError("subject is deleted") from original_error
                await uow.commit()
                return existing
        if created:
            await self._emit(ref, "create", resource="subject")
        return subject

    async def ensure_in_uow(
        self,
        uow: UnitOfWork,
        ref: SubjectRef,
        metadata: dict[str, JsonValue] | None = None,
    ) -> Subject:
        existing = await uow.subjects.get_by_ref(ref)
        if existing is not None:
            if existing.deleted_at is not None:
                raise SubjectDeletedError("subject is deleted")
            return existing

        now = self._clock.now()
        subject = Subject(
            id=uuid4(),
            ref=ref,
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        await uow.subjects.add(subject)
        return subject

    async def soft_delete_subject(self, ref: SubjectRef) -> Subject:
        changed = False
        async with self._uow_factory() as uow:
            subject = await uow.subjects.get_by_ref(ref)
            if subject is None:
                raise SubjectNotFoundError("subject does not exist")
            if subject.deleted_at is not None:
                return subject

            now = self._clock.now()
            deleted = subject.model_copy(update={"deleted_at": now, "updated_at": now})
            await uow.subjects.update(deleted)
            await uow.commit()
            changed = True
        if changed:
            await self._emit(ref, "delete", resource="subject")
        return deleted

    async def export_subject(self, ref: SubjectRef) -> SubjectExport:
        async with self._uow_factory() as uow:
            subject = await uow.subjects.get_by_ref(ref)
            if subject is None:
                raise SubjectNotFoundError("subject does not exist")
            if subject.deleted_at is not None:
                raise SubjectDeletedError("subject is deleted")

            entities: list[Entity] = []
            offset = 0
            while True:
                page = list(await uow.entities.list(ref, Page(200, offset)))
                entities.extend(page)
                if len(page) < 200:
                    break
                offset += 200

            events: list[Event] = []
            offset = 0
            while True:
                page = list(
                    await uow.events.list(ref, EventFilter(), Page(200, offset))
                )
                events.extend(page)
                if len(page) < 200:
                    break
                offset += 200

            memories: list[MemoryRecord] = []
            offset = 0
            while True:
                page = list(
                    await uow.memories.list(ref, MemoryFilter(), Page(200, offset))
                )
                memories.extend(page)
                if len(page) < 200:
                    break
                offset += 200

            profiles: list[ProfileSnapshot] = []
            offset = 0
            while True:
                page = list(await uow.profiles.list(ref, Page(200, offset)))
                profiles.extend(page)
                if len(page) < 200:
                    break
                offset += 200

            processing_runs: list[ProcessingRun] = []
            offset = 0
            while True:
                page = list(await uow.processing_runs.list(ref, Page(200, offset)))
                processing_runs.extend(page)
                if len(page) < 200:
                    break
                offset += 200

            memory_revisions: list[MemoryRevision] = []
            memory_evidence: list[MemoryEvidenceBinding] = []
            evidence_by_id: dict[UUID, Evidence] = {}
            for memory in memories:
                memory_revisions.extend(await uow.memory_revisions.list(ref, memory.id))
                for evidence_id in await uow.memories.list_evidence_ids(ref, memory.id):
                    memory_evidence.append(
                        MemoryEvidenceBinding(
                            memory_id=memory.id,
                            evidence_id=evidence_id,
                        )
                    )
                    evidence = await uow.evidence.get(ref, evidence_id)
                    if evidence is not None:
                        evidence_by_id[evidence.id] = evidence

            for event in events:
                for evidence in await uow.evidence.list_for_event(ref, event.id):
                    evidence_by_id[evidence.id] = evidence

            feature_observations: list[FeatureObservation] = list(
                await uow.features.list_observations(ref)
            )
            feature_states = list(
                await uow.features.list_states(ref, FeatureStateFilter())
            )
            for observation in feature_observations:
                evidence = await uow.evidence.get(ref, observation.evidence_id)
                if evidence is not None:
                    evidence_by_id[evidence.id] = evidence
            for state in feature_states:
                for evidence_id in state.evidence_ids:
                    evidence = await uow.evidence.get(ref, evidence_id)
                    if evidence is not None:
                        evidence_by_id[evidence.id] = evidence

            export_entities = [
                ExportEntity(
                    id=entity.id,
                    subject=entity.subject,
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
                for entity in entities
            ]
            result = SubjectExport(
                subject=subject,
                exported_at=self._clock.now(),
                entities=export_entities,
                events=events,
                evidence=sorted(evidence_by_id.values(), key=lambda item: str(item.id)),
                memories=memories,
                memory_revisions=memory_revisions,
                memory_evidence=sorted(
                    memory_evidence,
                    key=lambda item: (str(item.memory_id), str(item.evidence_id)),
                ),
                feature_observations=feature_observations,
                feature_states=feature_states,
                profiles=profiles,
                processing_runs=processing_runs,
            )
            await uow.commit()
        await self._emit(
            ref,
            "export",
            resource="subject",
            export_version=result.export_version,
            entity_count=len(result.entities),
            event_count=len(result.events),
            memory_count=len(result.memories),
        )
        return result

    async def issue_purge_token(
        self, ref: SubjectRef, ttl: timedelta = timedelta(minutes=5)
    ) -> PurgeToken:
        if self._token_store is None:
            raise PurgeConfirmationRequiredError("purge token store is not configured")
        async with self._uow_factory() as uow:
            subject = await uow.subjects.get_by_ref(ref)
            if subject is None:
                raise SubjectNotFoundError("subject does not exist")
            if subject.deleted_at is not None:
                raise SubjectDeletedError("subject is deleted")
            token = await self._token_store.issue(ref, self._clock.now(), ttl)
            await uow.commit()
        return token

    async def purge_subject(
        self,
        ref: SubjectRef,
        confirmation: str | None = None,
        *,
        token: str | None = None,
    ) -> PurgeResult:
        active_token = token or confirmation or ""
        if self._token_store is None:
            if active_token != ref.subject_id.root:
                raise PurgeConfirmationRequiredError(
                    "purge confirmation must match the subject identifier"
                )
        else:
            consumed = await self._token_store.consume(
                ref, active_token, self._clock.now()
            )
            if consumed is None:
                raise PurgeConfirmationRequiredError(
                    "purge token is invalid or expired"
                )
            async with self._uow_factory() as uow:
                subject = await uow.subjects.get_by_ref(ref)
                if subject is None:
                    raise SubjectNotFoundError("subject does not exist")
                await uow.commit()

        async with self._uow_factory() as uow:
            subject = await uow.subjects.get_by_ref(ref)
            if subject is None:
                raise SubjectNotFoundError("subject does not exist")
            await uow.purge_subject(ref)
            await uow.commit()

        full_text_deleted = await self._delete_index(self._full_text_index, ref)
        vector_deleted = await self._delete_index(self._vector_index, ref)
        if self._retention_hook is not None:
            await self._retention_hook.on_subject_purge(ref)
        await self._emit(
            ref,
            "purge",
            resource="subject",
            database_deleted=True,
            full_text_deleted=full_text_deleted,
            vector_deleted=vector_deleted,
        )
        return PurgeResult(
            subject=ref,
            purged=True,
            database_deleted=True,
            full_text_deleted=full_text_deleted,
            vector_deleted=vector_deleted,
        )

    @staticmethod
    async def _delete_index(
        index: FullTextIndex | VectorIndex | None, ref: SubjectRef
    ) -> bool:
        if index is None:
            return True
        await index.delete_subject(ref)
        return True
