from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import TypeVar
from uuid import UUID, uuid4

from pydantic import TypeAdapter

from personalization_core.domain.enums import (
    MemoryAuthority,
    MemoryKind,
    MemoryScope,
    MemoryState,
    Polarity,
    ProfileStatus,
    ResolutionType,
)
from personalization_core.domain.errors import InvalidArgumentError
from personalization_core.domain.events import Event
from personalization_core.domain.features import FeatureState
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.jobs import ProcessingRun, ProcessingStatus
from personalization_core.domain.memory import MemoryRecord, is_memory_effective
from personalization_core.domain.profile import (
    ProfileCoverage,
    ProfileDiff,
    ProfileSnapshot,
    ResolvedPreference,
    diff_profile_snapshots,
    feature_state_key,
    polarity_for_score,
    profile_content_digest,
    resolve_preference_pair,
)
from personalization_core.domain.types import UtcDatetime
from personalization_core.ports.clock import Clock
from personalization_core.ports.repositories import (
    EventFilter,
    FeatureStateFilter,
    MemoryFilter,
    Page,
)
from personalization_core.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

from .dto import ProfileRefreshOptions
from .subject_service import SubjectService

PROFILE_ALGORITHM_VERSION = "profile-resolver-1.0"
T = TypeVar("T")
_PAGE_SIZE = 200
_AUTHORITY_ORDER = {
    MemoryAuthority.CONFIRMED: 1,
    MemoryAuthority.EXPLICIT: 2,
}
_SCOPE_ORDER = {
    MemoryScope.GLOBAL: 0,
    MemoryScope.USE_CASE: 1,
    MemoryScope.TOPIC: 2,
    MemoryScope.ENTITY: 3,
}
_EXPLICIT_SCORE = {
    Polarity.POSITIVE: 1.0,
    Polarity.NEGATIVE: -1.0,
    Polarity.NEUTRAL: 0.0,
    Polarity.UNKNOWN: 0.0,
}


class ProfileService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        subject_service: SubjectService | None = None,
        algorithm_version: str = PROFILE_ALGORITHM_VERSION,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._subject_service = subject_service or SubjectService(uow_factory, clock)
        self._algorithm_version = algorithm_version

    async def refresh_profile(
        self,
        subject: SubjectRef,
        options: ProfileRefreshOptions | None = None,
    ) -> ProfileSnapshot:
        options = options or ProfileRefreshOptions()
        as_of: UtcDatetime = TypeAdapter[datetime](UtcDatetime).validate_python(
            options.as_of if options.as_of is not None else self._clock.now()
        )

        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            memories = await self._list_memories(uow, subject)
            events = await self._list_events(uow, subject)
            runs = await self._list_processing_runs(uow, subject)
            states = list(await uow.features.list_states(subject, FeatureStateFilter()))
            latest = await uow.profiles.get_latest(subject)

            snapshot = await self._build_snapshot(
                uow=uow,
                subject=subject,
                options=options,
                as_of=as_of,
                memories=memories,
                states=states,
                events=events,
                runs=runs,
                version=1 if latest is None else latest.version + 1,
            )
            if (
                latest is not None
                and not options.force_new_snapshot
                and profile_content_digest(snapshot) == profile_content_digest(latest)
            ):
                return latest

            await uow.profiles.add(subject, snapshot)
            await uow.commit()
            return snapshot

    async def get_latest_profile(self, subject: SubjectRef) -> ProfileSnapshot | None:
        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            snapshot = await uow.profiles.get_latest(subject)
            await uow.commit()
            return snapshot

    async def get_profile_version(
        self, subject: SubjectRef, version: int
    ) -> ProfileSnapshot | None:
        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            snapshot = await uow.profiles.get_version(subject, version)
            await uow.commit()
            return snapshot

    async def compare_profiles(
        self, subject: SubjectRef, left: int, right: int
    ) -> ProfileDiff:
        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            left_snapshot = await uow.profiles.get_version(subject, left)
            right_snapshot = await uow.profiles.get_version(subject, right)
            await uow.commit()

        if left_snapshot is None or right_snapshot is None:
            raise InvalidArgumentError("profile version not found")
        return diff_profile_snapshots(left_snapshot, right_snapshot)

    async def _build_snapshot(
        self,
        *,
        uow: UnitOfWork,
        subject: SubjectRef,
        options: ProfileRefreshOptions,
        as_of: UtcDatetime,
        memories: Sequence[MemoryRecord],
        states: Sequence[FeatureState],
        events: Sequence[Event],
        runs: Sequence[ProcessingRun],
        version: int,
    ) -> ProfileSnapshot:
        warnings: set[str] = set()
        memory_candidates: dict[
            tuple[str, str], list[tuple[MemoryRecord, list[UUID], int]]
        ] = defaultdict(list)

        for memory in memories:
            if not is_memory_effective(memory, at=as_of):
                continue
            if memory.kind not in {MemoryKind.PREFERENCE, MemoryKind.CONSTRAINT}:
                continue
            if memory.target is None:
                continue
            scope_order = self._matching_scope(memory, options)
            if scope_order is None:
                continue
            evidence_ids = sorted(
                set(await uow.memories.list_evidence_ids(subject, memory.id)),
                key=str,
            )
            if not evidence_ids:
                warnings.add(f"memory_missing_evidence:{memory.id}")
                continue
            if memory.authority not in _AUTHORITY_ORDER:
                continue
            memory_key = (memory.target.dimension, memory.target.value_key)
            memory_candidates[memory_key].append((memory, evidence_ids, scope_order))

        selected_memories: dict[
            tuple[str, str], tuple[MemoryRecord, list[UUID], list[UUID]]
        ] = {}
        for key, candidates in memory_candidates.items():
            candidates.sort(
                key=lambda item: (
                    -item[2],
                    -_AUTHORITY_ORDER[item[0].authority],
                    -item[0].updated_at.timestamp(),
                    str(item[0].id),
                )
            )
            selected, _, _ = candidates[0]
            memory_ids = sorted((item[0].id for item in candidates), key=str)
            evidence_ids = sorted(
                {evidence_id for _, ids, _ in candidates for evidence_id in ids},
                key=str,
            )
            selected_memories[key] = (selected, memory_ids, evidence_ids)

        selected_states = self._select_feature_states(states)
        preferences: list[ResolvedPreference] = []
        for key in sorted(set(selected_memories) | set(selected_states)):
            memory_data = selected_memories.get(key)
            state = selected_states.get(key)
            if memory_data is not None and state is not None:
                preference = self._resolve_pair(
                    memory_data=memory_data,
                    feature=state,
                    as_of=as_of,
                )
            elif memory_data is not None:
                preference = self._resolve_memory_only(memory_data)
            else:
                assert state is not None
                preference = self._resolve_behavior_only(state)
            preferences.append(preference)

        total_events = len(events)
        processed_events, failed_events = self._coverage_from_runs(runs, total_events)
        coverage = ProfileCoverage(
            total_events=total_events,
            processed_events=processed_events,
            failed_events=failed_events,
        )
        if processed_events != total_events:
            warnings.add("coverage_incomplete")

        source_watermark = max(
            (event.occurred_at for event in events),
            default=None,
        )
        has_effective_memory = bool(selected_memories)
        has_feature_state = bool(selected_states)
        status = (
            ProfileStatus.EMPTY
            if not events and not has_effective_memory and not has_feature_state
            else ProfileStatus.COMPLETE
            if processed_events == total_events
            else ProfileStatus.PARTIAL
        )
        return ProfileSnapshot(
            id=uuid4(),
            subject=subject,
            version=version,
            status=status,
            generated_at=self._clock.now(),
            algorithm_version=self._algorithm_version,
            source_watermark=source_watermark,
            coverage=coverage,
            preferences=preferences,
            warnings=sorted(warnings),
        )

    @staticmethod
    def _matching_scope(
        memory: MemoryRecord, options: ProfileRefreshOptions
    ) -> int | None:
        if memory.scope == MemoryScope.GLOBAL:
            return _SCOPE_ORDER[memory.scope]
        values = {
            MemoryScope.USE_CASE: options.use_case,
            MemoryScope.TOPIC: options.topic,
            MemoryScope.ENTITY: options.entity,
        }
        selected = values[memory.scope]
        return (
            _SCOPE_ORDER[memory.scope]
            if selected is not None and memory.scope_value == selected
            else None
        )

    @staticmethod
    def _select_feature_states(
        states: Sequence[FeatureState],
    ) -> dict[tuple[str, str], FeatureState]:
        grouped: dict[tuple[str, str], list[FeatureState]] = defaultdict(list)
        for state in states:
            grouped[(state.dimension, state.value_key)].append(state)
        return {
            key: sorted(
                values,
                key=lambda state: (
                    -state.confidence,
                    -abs(state.long_term_score),
                    -abs(state.short_term_score),
                    state.aggregator_name,
                    state.algorithm_version,
                ),
            )[0]
            for key, values in grouped.items()
        }

    @staticmethod
    def _resolve_pair(
        *,
        memory_data: tuple[MemoryRecord, list[UUID], list[UUID]],
        feature: FeatureState,
        as_of: UtcDatetime,
    ) -> ResolvedPreference:
        memory, memory_ids, evidence_ids = memory_data
        result = resolve_preference_pair(
            memory=memory,
            feature=feature,
            memory_evidence_ids=evidence_ids,
            at=as_of,
        )
        refs = sorted(
            {f"evidence:{item}" for item in [*evidence_ids, *feature.evidence_ids]}
        )
        conflicts = [
            conflict.model_copy(
                update={"memory_ids": memory_ids, "evidence_refs": refs}
            )
            for conflict in result.conflicts
        ]
        return result.model_copy(
            update={
                "explicit_memory_ids": memory_ids,
                "conflicts": conflicts,
                "evidence_refs": refs,
            }
        )

    @staticmethod
    def _resolve_memory_only(
        memory_data: tuple[MemoryRecord, list[UUID], list[UUID]],
    ) -> ResolvedPreference:
        memory, memory_ids, evidence_ids = memory_data
        assert memory.target is not None
        refs = sorted(f"evidence:{item}" for item in evidence_ids)
        return ResolvedPreference(
            dimension=memory.target.dimension,
            value_key=memory.target.value_key,
            explicit_memory_ids=memory_ids,
            effective_polarity=memory.polarity,
            effective_score=_EXPLICIT_SCORE[memory.polarity],
            confidence=memory.confidence,
            resolution=ResolutionType.EXPLICIT_ONLY,
            evidence_refs=refs,
        )

    @staticmethod
    def _resolve_behavior_only(state: FeatureState) -> ResolvedPreference:
        score = state.long_term_score
        return ResolvedPreference(
            dimension=state.dimension,
            value_key=state.value_key,
            feature_state_key=feature_state_key(state),
            effective_polarity=polarity_for_score(score),
            effective_score=score,
            confidence=state.confidence,
            resolution=ResolutionType.BEHAVIOR_ONLY,
            evidence_refs=sorted(f"evidence:{item}" for item in state.evidence_ids),
        )

    @staticmethod
    def _coverage_from_runs(
        runs: Sequence[ProcessingRun], total_events: int
    ) -> tuple[int, int]:
        processed = 0
        failed = 0
        for run in runs:
            if run.operation == "feature.process_event":
                if run.status == ProcessingStatus.SUCCEEDED:
                    processed += 1
                elif run.status == ProcessingStatus.FAILED:
                    failed += 1
            elif run.operation == "feature.process_pending":
                processed += run.processed_count
                failed += run.failed_count
        processed = min(processed, total_events)
        failed = min(failed, max(0, total_events - processed))
        return processed, failed

    @staticmethod
    async def _list_memories(
        uow: UnitOfWork, subject: SubjectRef
    ) -> list[MemoryRecord]:
        return list(
            await ProfileService._list_paged(
                lambda page: uow.memories.list(
                    subject,
                    MemoryFilter(states=frozenset({MemoryState.ACTIVE})),
                    page,
                )
            )
        )

    @staticmethod
    async def _list_events(uow: UnitOfWork, subject: SubjectRef) -> list[Event]:
        return list(
            await ProfileService._list_paged(
                lambda page: uow.events.list(subject, EventFilter(), page)
            )
        )

    @staticmethod
    async def _list_processing_runs(
        uow: UnitOfWork, subject: SubjectRef
    ) -> list[ProcessingRun]:
        return list(
            await ProfileService._list_paged(
                lambda page: uow.processing_runs.list(subject, page)
            )
        )

    @staticmethod
    async def _list_paged(
        fetch: Callable[[Page], Awaitable[Sequence[T]]],
    ) -> list[T]:
        # The repository protocols return Sequence rather than a Page wrapper;
        # keeping the pagination loop here makes refresh independent of adapter
        # storage and protects coverage from the first page only.
        result: list[T] = []
        offset = 0
        while True:
            page = await fetch(Page(limit=_PAGE_SIZE, offset=offset))
            result.extend(page)
            if len(page) < _PAGE_SIZE:
                return result
            offset += len(page)
