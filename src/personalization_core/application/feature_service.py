from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID, uuid4

from pydantic import ValidationError

from personalization_core.domain.entities import Entity
from personalization_core.domain.errors import (
    DomainError,
    ErrorCode,
    InvalidArgumentError,
)
from personalization_core.domain.features import (
    FeatureObservation,
    FeatureObservationDraft,
    FeatureState,
    FeatureStateDraft,
)
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.jobs import ProcessingRun, ProcessingStatus
from personalization_core.plugins.registry import FeatureExtractorRegistry
from personalization_core.ports.clock import Clock
from personalization_core.ports.metrics import MetricsSink
from personalization_core.ports.repositories import (
    EventFilter,
    FeatureStateFilter,
    Page,
)
from personalization_core.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

from .dto import FeatureProcessingResult
from .subject_service import SubjectService

ALGORITHM_VERSION = "feature-engine-1.0"


class FeatureService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        subject_service: SubjectService,
        registry: FeatureExtractorRegistry,
        metrics: MetricsSink | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._subject_service = subject_service
        self._registry = registry
        self._metrics = metrics

    async def process_event(
        self,
        subject: SubjectRef,
        event_id: UUID,
    ) -> FeatureProcessingResult:
        run = await self._start_run(subject, "feature.process_event")
        try:
            async with self._uow_factory() as uow:
                await self._subject_service.ensure_in_uow(uow, subject)
                created, replayed, updated = await self._process_event_in_uow(
                    uow, subject, event_id
                )
                completed = run.model_copy(
                    update={
                        "status": ProcessingStatus.SUCCEEDED,
                        "finished_at": self._clock.now(),
                        "processed_count": 1,
                    }
                )
                await uow.processing_runs.update(subject, completed)
                await uow.commit()
                return FeatureProcessingResult(
                    event_id=event_id,
                    created_observation_count=created,
                    replayed_observation_count=replayed,
                    updated_state_count=updated,
                    run=completed,
                )
        except Exception as error:
            await self._mark_failed(subject, run, error)
            raise

    async def process_pending(
        self,
        subject: SubjectRef,
        limit: int = 50,
    ) -> ProcessingRun:
        if isinstance(limit, bool) or not 1 <= limit <= 200:
            raise InvalidArgumentError("limit must be between 1 and 200")

        run = await self._start_run(subject, "feature.process_pending")
        try:
            async with self._uow_factory() as uow:
                await self._subject_service.ensure_in_uow(uow, subject)
                events = await uow.events.list(
                    subject, EventFilter(), Page(limit=limit)
                )
                if self._metrics is not None:
                    self._metrics.set_processing_backlog(len(events))
                await uow.commit()
        except Exception as error:
            await self._mark_failed(subject, run, error)
            raise

        processed_count = 0
        failed_count = 0
        first_error: Exception | None = None
        for event in events:
            try:
                async with self._uow_factory() as uow:
                    await self._subject_service.ensure_in_uow(uow, subject)
                    await self._process_event_in_uow(uow, subject, event.id)
                    await uow.commit()
                processed_count += 1
            except Exception as error:
                failed_count += 1
                if first_error is None:
                    first_error = error
            if self._metrics is not None:
                self._metrics.set_processing_backlog(
                    max(len(events) - processed_count - failed_count, 0)
                )

        status = (
            ProcessingStatus.SUCCEEDED if failed_count == 0 else ProcessingStatus.FAILED
        )
        completed = run.model_copy(
            update={
                "status": status,
                "finished_at": self._clock.now(),
                "processed_count": processed_count,
                "failed_count": failed_count,
                "error_code": (
                    None if first_error is None else self._error_code(first_error)
                ),
            }
        )
        await self._update_run(subject, completed)
        if self._metrics is not None:
            self._metrics.set_processing_backlog(0)
        return completed

    async def rebuild_dimension(
        self,
        subject: SubjectRef,
        dimension: str,
    ) -> ProcessingRun:
        dimension = dimension.strip()
        if not dimension:
            raise InvalidArgumentError("dimension must not be blank")

        run = await self._start_run(subject, "feature.rebuild_dimension")
        try:
            async with self._uow_factory() as uow:
                await self._subject_service.ensure_in_uow(uow, subject)
                observations = list(
                    await uow.features.list_observations(subject, dimension)
                )
                await self._rebuild_dimension_in_uow(
                    uow, subject, dimension, observations
                )
                completed = run.model_copy(
                    update={
                        "status": ProcessingStatus.SUCCEEDED,
                        "finished_at": self._clock.now(),
                        "processed_count": len(observations),
                    }
                )
                await uow.processing_runs.update(subject, completed)
                await uow.commit()
                return completed
        except Exception as error:
            await self._mark_failed(subject, run, error)
            raise

    async def list_feature_states(
        self,
        subject: SubjectRef,
        filters: FeatureStateFilter | None = None,
    ) -> list[FeatureState]:
        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            states = list(
                await uow.features.list_states(subject, filters or FeatureStateFilter())
            )
            await uow.commit()
            return states

    async def _start_run(self, subject: SubjectRef, operation: str) -> ProcessingRun:
        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            run = ProcessingRun(
                id=uuid4(),
                subject=subject,
                operation=operation,
                status=ProcessingStatus.RUNNING,
                algorithm_version=ALGORITHM_VERSION,
                started_at=self._clock.now(),
            )
            await uow.processing_runs.add(subject, run)
            await uow.commit()
            return run

    async def _update_run(self, subject: SubjectRef, run: ProcessingRun) -> None:
        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            await uow.processing_runs.update(subject, run)
            await uow.commit()

    async def _mark_failed(
        self,
        subject: SubjectRef,
        run: ProcessingRun,
        error: Exception,
    ) -> ProcessingRun:
        failed = run.model_copy(
            update={
                "status": ProcessingStatus.FAILED,
                "finished_at": self._clock.now(),
                "error_code": self._error_code(error),
            }
        )
        await self._update_run(subject, failed)
        return failed

    @staticmethod
    def _error_code(error: Exception) -> str:
        if isinstance(error, DomainError):
            return error.code.value
        if isinstance(error, ValidationError):
            return ErrorCode.PROCESSING_FAILED.value
        return ErrorCode.PROCESSING_FAILED.value

    async def _process_event_in_uow(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        event_id: UUID,
    ) -> tuple[int, int, int]:
        event = await uow.events.get(subject, event_id)
        if event is None:
            raise InvalidArgumentError("event does not exist")

        entity: Entity | None = None
        if event.entity is not None:
            entity = await uow.entities.get_by_ref(event.entity)
        evidence = list(await uow.evidence.list_for_event(subject, event.id))
        if not evidence:
            raise InvalidArgumentError("event has no evidence")

        created_count = 0
        replayed_count = 0
        dimensions: set[str] = set()
        for extractor in self._registry.extractors_for(event.event_type):
            drafts = await extractor.extract(event, entity)
            for raw_draft in drafts:
                draft = FeatureObservationDraft.model_validate(raw_draft, strict=True)
                dimensions.add(draft.dimension)
                observation = FeatureObservation(
                    id=uuid4(),
                    subject=subject,
                    source_event_id=event.id,
                    evidence_id=evidence[0].id,
                    extractor_name=extractor.name,
                    extractor_version=extractor.version,
                    created_at=self._clock.now(),
                    **draft.model_dump(),
                )
                created = await self._save_observation_idempotently(
                    uow, subject, observation
                )
                if created:
                    created_count += 1
                else:
                    replayed_count += 1

        updated_count = 0
        for dimension in sorted(dimensions):
            observations = list(
                await uow.features.list_observations(subject, dimension)
            )
            updated_count += await self._rebuild_dimension_in_uow(
                uow, subject, dimension, observations
            )
        return created_count, replayed_count, updated_count

    async def _save_observation_idempotently(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        observation: FeatureObservation,
    ) -> bool:
        existing = await self._find_observation(
            uow, subject, observation.dimension, observation.identity_key
        )
        if existing is not None:
            return False
        try:
            await uow.features.add_observation(subject, observation)
            return True
        except InvalidArgumentError:
            existing = await self._find_observation(
                uow, subject, observation.dimension, observation.identity_key
            )
            if existing is not None:
                return False
            raise

    @staticmethod
    async def _find_observation(
        uow: UnitOfWork,
        subject: SubjectRef,
        dimension: str,
        identity_key: tuple[UUID, str, str, str, str],
    ) -> FeatureObservation | None:
        observations = await uow.features.list_observations(subject, dimension)
        return next(
            (item for item in observations if item.identity_key == identity_key),
            None,
        )

    async def _rebuild_dimension_in_uow(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        dimension: str,
        observations: Sequence[FeatureObservation],
    ) -> int:
        grouped: defaultdict[str, list[FeatureObservation]] = defaultdict(list)
        for observation in observations:
            grouped[observation.value_key].append(observation)

        updated_count = 0
        for value_key in sorted(grouped):
            for aggregator in self._registry.aggregators_for(dimension):
                draft = aggregator.aggregate(grouped[value_key], self._clock.now())
                state_draft = self._validate_state_draft(draft, dimension, value_key)
                state = FeatureState(
                    subject=subject,
                    aggregator_name=aggregator.name,
                    algorithm_version=aggregator.version,
                    updated_at=self._clock.now(),
                    **state_draft.model_dump(),
                )
                await uow.features.upsert_state(subject, state)
                updated_count += 1
        return updated_count

    @staticmethod
    def _validate_state_draft(
        draft: FeatureStateDraft,
        dimension: str,
        value_key: str,
    ) -> FeatureStateDraft:
        if draft.dimension != dimension or draft.value_key != value_key:
            raise InvalidArgumentError(
                "aggregator returned a state for a different dimension or value"
            )
        return draft
