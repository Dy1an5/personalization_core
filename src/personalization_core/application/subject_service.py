from __future__ import annotations

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
from personalization_core.ports.clock import Clock
from personalization_core.ports.repositories import (
    EventFilter,
    FeatureStateFilter,
    MemoryFilter,
    Page,
)
from personalization_core.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

from .dto import (
    ExportEntity,
    MemoryEvidenceBinding,
    PurgeResult,
    SubjectExport,
)


class SubjectService:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def create_or_get_subject(
        self,
        ref: SubjectRef,
        metadata: dict[str, JsonValue] | None = None,
    ) -> Subject:
        try:
            async with self._uow_factory() as uow:
                subject = await self.ensure_in_uow(uow, ref, metadata)
                await uow.commit()
                return subject
        except InvalidArgumentError as original_error:
            async with self._uow_factory() as uow:
                existing = await uow.subjects.get_by_ref(ref)
                if existing is None:
                    raise original_error from None
                if existing.deleted_at is not None:
                    raise SubjectDeletedError("subject is deleted") from original_error
                await uow.commit()
                return existing

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
            return SubjectExport(
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

    async def purge_subject(self, ref: SubjectRef, confirmation: str) -> PurgeResult:
        if confirmation != ref.subject_id.root:
            raise PurgeConfirmationRequiredError(
                "purge confirmation must match the subject identifier"
            )

        async with self._uow_factory() as uow:
            subject = await uow.subjects.get_by_ref(ref)
            if subject is None:
                raise SubjectNotFoundError("subject does not exist")
            await uow.purge_subject(ref)
            await uow.commit()
            return PurgeResult(subject=ref, purged=True)
