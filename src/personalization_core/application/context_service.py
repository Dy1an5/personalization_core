from __future__ import annotations

import hashlib
import math
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from uuid import UUID

from pydantic import TypeAdapter

from personalization_core.domain.context import (
    ContextBundle,
    ContextRequest,
    ContextSource,
    MemorySearchHit,
)
from personalization_core.domain.enums import (
    MemoryAuthority,
    MemoryKind,
    MemoryScope,
    MemoryState,
)
from personalization_core.domain.errors import (
    ProviderInvalidResponseError,
    ProviderNetworkError,
    ProviderTimeoutError,
    SubjectDeletedError,
    SubjectNotFoundError,
)
from personalization_core.domain.features import FeatureState
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.memory import MemoryRecord, is_memory_effective
from personalization_core.domain.profile import PreferenceConflict
from personalization_core.domain.types import UtcDatetime
from personalization_core.ports.audit_sink import AuditEvent, AuditSink
from personalization_core.ports.clock import Clock
from personalization_core.ports.embedder import Embedder
from personalization_core.ports.full_text_search import FullTextIndex, TextDocument
from personalization_core.ports.repositories import (
    FeatureStateFilter,
    MemoryFilter,
    Page,
)
from personalization_core.ports.reranker import RerankCandidate, Reranker
from personalization_core.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from personalization_core.ports.vector_index import VectorIndex

from .subject_service import SubjectService

CONTEXT_ALGORITHM_VERSION = "context-resolver-1.0"
_PAGE_SIZE = 200
_AUTHORITY_ORDER = {
    MemoryAuthority.INFERRED: 1,
    MemoryAuthority.CONFIRMED: 2,
    MemoryAuthority.EXPLICIT: 3,
}
_SCOPE_ORDER = {
    MemoryScope.GLOBAL: 0,
    MemoryScope.USE_CASE: 1,
    MemoryScope.TOPIC: 2,
    MemoryScope.ENTITY: 3,
}


class ContextService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        subject_service: SubjectService,
        full_text_index: FullTextIndex | None = None,
        vector_index: VectorIndex | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._subject_service = subject_service
        self._full_text_index = full_text_index
        self._vector_index = vector_index
        self._embedder = embedder
        self._reranker = reranker
        self._audit_sink = audit_sink

    async def resolve_context(self, request: ContextRequest) -> ContextBundle:
        as_of: UtcDatetime = TypeAdapter[datetime](UtcDatetime).validate_python(
            request.as_of if request.as_of is not None else self._clock.now()
        )
        query = request.query or ""
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()

        async with self._uow_factory() as uow:
            await self._require_subject(uow, request.subject)
            memories = [
                memory
                for memory in await self._list_memories(uow, request.subject)
                if is_memory_effective(memory, at=as_of)
                and self._matches_scope(memory, request)
                and (
                    request.include_inferred
                    or memory.authority != MemoryAuthority.INFERRED
                )
            ]
            memory_by_id = {memory.id: memory for memory in memories}

            documents = [
                TextDocument(
                    id=memory.id,
                    subject=memory.subject,
                    text=memory.content,
                    metadata={
                        "updated_at": memory.updated_at.isoformat(),
                        "scope": memory.scope.value,
                    },
                )
                for memory in memories
            ]
            if self._full_text_index is not None:
                await self._full_text_index.upsert(documents)

            candidates: dict[UUID, _Candidate] = {
                memory.id: _Candidate(
                    score=self._structured_score(memory),
                    sources={ContextSource.STRUCTURED},
                )
                for memory in memories
            }

            if self._full_text_index is not None and query:
                text_hits = await self._full_text_index.search(
                    request.subject,
                    query,
                    max(request.recent_limit, request.long_term_limit, 200),
                )
                for hit in text_hits:
                    candidate = candidates.get(hit.id)
                    if candidate is None:
                        continue
                    candidate.score = max(candidate.score, hit.score)
                    candidate.sources.add(ContextSource.FULL_TEXT)
                    candidate.matched_terms.update(hit.matched_terms)

            if self._embedder is not None and self._vector_index is not None and query:
                query_vector = await self._embed_query(query)
                try:
                    vector_hits = await self._vector_index.search(
                        request.subject,
                        query_vector,
                        max(request.recent_limit, request.long_term_limit, 200),
                    )
                except (ProviderTimeoutError, ProviderNetworkError):
                    raise
                except Exception as exc:
                    raise ProviderInvalidResponseError(
                        "VectorIndex returned an invalid response"
                    ) from exc
                for hit in vector_hits:
                    candidate = candidates.get(hit.id)
                    if candidate is None:
                        continue
                    candidate.score = max(candidate.score, (hit.score + 1.0) / 2.0)
                    candidate.sources.add(ContextSource.VECTOR)

            # With an active text/vector retrieval path, an ordinary structured
            # candidate must also be relevant to the query.  Hard constraints
            # remain eligible regardless of query terms and are selected first.
            has_query_retrieval = bool(
                query
                and (
                    self._full_text_index is not None
                    or (self._embedder is not None and self._vector_index is not None)
                )
            )
            if has_query_retrieval:
                candidates = {
                    memory_id: candidate
                    for memory_id, candidate in candidates.items()
                    if self._is_hard_constraint(memory_by_id[memory_id])
                    or bool(
                        candidate.sources
                        & {ContextSource.FULL_TEXT, ContextSource.VECTOR}
                    )
                }

                memory_by_id = {
                    memory_id: memory_by_id[memory_id] for memory_id in candidates
                }

            # Re-load every indexed hit through the authoritative, subject-scoped
            # repository.  This also protects against stale index entries.
            for memory_id in list(candidates):
                current = await uow.memories.get(request.subject, memory_id)
                if (
                    current is None
                    or not is_memory_effective(current, at=as_of)
                    or not self._matches_scope(current, request)
                    or (
                        not request.include_inferred
                        and current.authority == MemoryAuthority.INFERRED
                    )
                ):
                    del candidates[memory_id]
                else:
                    memory_by_id[memory_id] = current

            if self._reranker is not None and query and candidates:
                await self._apply_reranker(query, candidates, memory_by_id)

            states = list(
                await uow.features.list_states(request.subject, FeatureStateFilter())
            )
            recent = sorted(
                states,
                key=lambda state: (
                    -(abs(state.short_term_score) * state.confidence),
                    -state.updated_at.timestamp(),
                    state.dimension,
                    state.value_key,
                ),
            )[: request.recent_limit]
            long_term = sorted(
                states,
                key=lambda state: (
                    -(abs(state.long_term_score) * state.confidence),
                    -state.updated_at.timestamp(),
                    state.dimension,
                    state.value_key,
                ),
            )[: request.long_term_limit]

            profile = await uow.profiles.get_latest(request.subject)
            conflicts = self._relevant_conflicts(
                profile.preferences if profile is not None else [],
                set(memory_by_id),
            )
            evidence_by_memory: dict[UUID, list[UUID]] = {}
            for memory_id in memory_by_id:
                evidence_by_memory[memory_id] = sorted(
                    set(
                        await uow.memories.list_evidence_ids(request.subject, memory_id)
                    ),
                    key=str,
                )

            hard_memories = [
                memory_by_id[memory_id]
                for memory_id in sorted(
                    candidates,
                    key=lambda item: self._memory_sort_key(
                        memory_by_id[item], candidates[item].score
                    ),
                )
                if self._is_hard_constraint(memory_by_id[memory_id])
            ]
            hard_ids = {memory.id for memory in hard_memories}
            ordered_candidates = sorted(
                (
                    (memory_by_id[memory_id], candidate)
                    for memory_id, candidate in candidates.items()
                    if memory_id not in hard_ids
                ),
                key=lambda item: self._memory_sort_key(item[0], item[1].score),
            )
            selected_hits, truncated = self._select_with_budget(
                ordered_candidates,
                hard_memories,
                evidence_by_memory,
                request.token_budget,
            )
            evidence_ids = self._bundle_evidence_ids(
                hard_memories,
                selected_hits,
                recent,
                long_term,
                conflicts,
                evidence_by_memory,
            )
            estimated_tokens = self._estimate_bundle_tokens(
                hard_memories,
                selected_hits,
            )
            bundle = ContextBundle(
                subject=request.subject,
                query_hash=query_hash,
                generated_at=self._clock.now(),
                hard_constraints=hard_memories,
                memories=selected_hits,
                recent_interests=recent,
                long_term_interests=long_term,
                conflicts=conflicts,
                evidence_ids=evidence_ids,
                estimated_tokens=estimated_tokens,
                truncated=truncated,
                algorithm_version=CONTEXT_ALGORITHM_VERSION,
                full_text_index_version=(
                    self._full_text_index.index_version
                    if self._full_text_index is not None
                    else "none"
                ),
                vector_index_version=(
                    self._vector_index.index_version
                    if self._vector_index is not None
                    else "none"
                ),
            )
            await uow.commit()

        if self._audit_sink is not None:
            await self._audit_sink.emit(
                AuditEvent(
                    subject=request.subject,
                    action="context.resolve",
                    occurred_at=self._clock.now(),
                    metadata={
                        "query_hash": query_hash,
                        "query_length": len(query),
                        "use_case": request.use_case,
                        "candidate_count": len(candidates),
                        "memory_count": len(bundle.memories),
                        "hard_constraint_count": len(bundle.hard_constraints),
                        "truncated": bundle.truncated,
                        "token_budget": request.token_budget,
                        "estimated_tokens": bundle.estimated_tokens,
                        "algorithm_version": bundle.algorithm_version,
                        "full_text_index_version": bundle.full_text_index_version,
                        "vector_index_version": bundle.vector_index_version,
                    },
                )
            )
        return bundle

    async def _require_subject(self, uow: UnitOfWork, subject: SubjectRef) -> None:
        existing = await uow.subjects.get_by_ref(subject)
        if existing is None:
            raise SubjectNotFoundError("subject does not exist")
        if existing.deleted_at is not None:
            raise SubjectDeletedError("subject is deleted")

    async def _list_memories(
        self, uow: UnitOfWork, subject: SubjectRef
    ) -> list[MemoryRecord]:
        return await self._list_paged(
            lambda page: uow.memories.list(
                subject,
                MemoryFilter(states=frozenset({MemoryState.ACTIVE})),
                page,
            )
        )

    @staticmethod
    async def _list_paged(
        fetch: Callable[[Page], Awaitable[Sequence[MemoryRecord]]],
    ) -> list[MemoryRecord]:
        # The concrete repository implementations return a Sequence, while this
        # loop keeps the application independent of their pagination strategy.
        result: list[MemoryRecord] = []
        offset = 0
        while True:
            page = await fetch(Page(limit=_PAGE_SIZE, offset=offset))
            result.extend(page)
            if len(page) < _PAGE_SIZE:
                return result
            offset += len(page)

    @staticmethod
    def _matches_scope(memory: MemoryRecord, request: ContextRequest) -> bool:
        if memory.scope == MemoryScope.GLOBAL:
            return True
        requested = {
            MemoryScope.USE_CASE: request.use_case,
            MemoryScope.TOPIC: request.topic,
            MemoryScope.ENTITY: request.entity,
        }[memory.scope]
        return requested is not None and memory.scope_value == requested

    @staticmethod
    def _structured_score(memory: MemoryRecord) -> float:
        return _AUTHORITY_ORDER[memory.authority] / max(_AUTHORITY_ORDER.values())

    @staticmethod
    def _is_hard_constraint(memory: MemoryRecord) -> bool:
        return memory.kind in {MemoryKind.CONSTRAINT, MemoryKind.INSTRUCTION} and (
            memory.authority in {MemoryAuthority.EXPLICIT, MemoryAuthority.CONFIRMED}
        )

    @staticmethod
    def _memory_sort_key(
        memory: MemoryRecord, score: float
    ) -> tuple[float, int, int, float, str]:
        return (
            -score,
            -_SCOPE_ORDER[memory.scope],
            -_AUTHORITY_ORDER[memory.authority],
            -memory.updated_at.timestamp(),
            str(memory.id),
        )

    async def _embed_query(self, query: str) -> list[float]:
        assert self._embedder is not None
        try:
            vector = await self._embedder.embed_query(query)
        except TimeoutError as exc:
            raise ProviderTimeoutError("Embedder timed out") from exc
        except OSError as exc:
            raise ProviderNetworkError("Embedder network failure") from exc
        except (ProviderTimeoutError, ProviderNetworkError):
            raise
        except Exception as exc:
            raise ProviderInvalidResponseError(
                "Embedder returned an invalid response"
            ) from exc
        try:
            values = list(vector)
            if not values:
                raise ValueError("empty vector")
            result = [float(value) for value in values]
            if not all(math.isfinite(value) for value in result):
                raise ValueError("non-finite vector")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ProviderInvalidResponseError(
                "Embedder returned an invalid vector"
            ) from exc
        return result

    async def _apply_reranker(
        self,
        query: str,
        candidates: dict[UUID, _Candidate],
        memories: dict[UUID, MemoryRecord],
    ) -> None:
        assert self._reranker is not None
        try:
            results = await self._reranker.rerank(
                query,
                [
                    RerankCandidate(id=memory_id, text=memories[memory_id].content)
                    for memory_id in candidates
                ],
                len(candidates),
            )
        except Exception:
            # A failed optional reranker must not remove already scope-checked
            # candidates or turn a useful structured/full-text result into an error.
            return
        seen: set[UUID] = set()
        for result in results:
            if result.id in seen or result.id not in candidates:
                continue
            seen.add(result.id)
            candidates[result.id].score = result.score
            candidates[result.id].sources.add(ContextSource.RERANKED)

    @staticmethod
    def _relevant_conflicts(
        preferences: Sequence[object], memory_ids: set[UUID]
    ) -> list[PreferenceConflict]:
        result: list[PreferenceConflict] = []
        for preference in preferences:
            conflicts = getattr(preference, "conflicts", [])
            for conflict in conflicts:
                if set(conflict.memory_ids) & memory_ids:
                    result.append(conflict)
        return result

    @staticmethod
    def _select_with_budget(
        ordered: Sequence[tuple[MemoryRecord, _Candidate]],
        hard: Sequence[MemoryRecord],
        evidence_by_memory: dict[UUID, list[UUID]],
        budget: int | None,
    ) -> tuple[list[MemorySearchHit], bool]:
        used = sum(ContextService._estimate_memory_tokens(memory) for memory in hard)
        selected: list[MemorySearchHit] = []
        truncated = False
        for memory, candidate in ordered:
            hit = MemorySearchHit(
                memory=memory,
                score=max(0.0, min(1.0, candidate.score)),
                sources=list(
                    sorted(candidate.sources, key=lambda source: source.value)
                ),
                evidence_ids=evidence_by_memory.get(memory.id, []),
                matched_terms=sorted(candidate.matched_terms),
            )
            cost = ContextService._estimate_memory_tokens(memory)
            if budget is not None and used + cost > budget:
                truncated = True
                continue
            selected.append(hit)
            used += cost
        return selected, truncated

    @staticmethod
    def _estimate_memory_tokens(memory: MemoryRecord) -> int:
        return max(1, math.ceil(len(memory.content) / 4) + 4)

    @staticmethod
    def _estimate_bundle_tokens(
        hard: Sequence[MemoryRecord], memories: Sequence[MemorySearchHit]
    ) -> int:
        return sum(
            ContextService._estimate_memory_tokens(memory) for memory in hard
        ) + sum(ContextService._estimate_memory_tokens(hit.memory) for hit in memories)

    @staticmethod
    def _bundle_evidence_ids(
        hard: Sequence[MemoryRecord],
        memories: Sequence[MemorySearchHit],
        recent: Sequence[FeatureState],
        long_term: Sequence[FeatureState],
        conflicts: Sequence[PreferenceConflict],
        evidence_by_memory: dict[UUID, list[UUID]],
    ) -> list[UUID]:
        evidence: set[UUID] = set()
        for memory in hard:
            evidence.update(evidence_by_memory.get(memory.id, []))
        for hit in memories:
            evidence.update(hit.evidence_ids)
        for state in [*recent, *long_term]:
            evidence.update(state.evidence_ids)
        for conflict in conflicts:
            for reference in conflict.evidence_refs:
                evidence.add(UUID(str(reference).split(":", 1)[1]))
        return sorted(evidence, key=str)


class _Candidate:
    def __init__(self, *, score: float, sources: set[ContextSource]) -> None:
        self.score = score
        self.sources = set(sources)
        self.matched_terms: set[str] = set()
