from __future__ import annotations

from collections.abc import Sequence
from typing import cast
from uuid import UUID, uuid4

from personalization_core.domain.enums import (
    EvidenceSourceType,
    MemoryAuthority,
    MemoryState,
    MemoryTransitionType,
)
from personalization_core.domain.errors import (
    MemoryNotFoundError,
    MemoryProtectionError,
    MemoryTransitionError,
    ProviderInvalidResponseError,
    ProviderNetworkError,
    ProviderTimeoutError,
    SubjectDeletedError,
    SubjectNotFoundError,
    TenantScopeViolationError,
)
from personalization_core.domain.evidence import Evidence, EvidenceCreate
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.memory import (
    MemoryRecord,
    MemoryRevision,
    MemoryTransitionResult,
    assert_revision,
    create_explicit_memory,
    create_inferred_memory,
    soft_delete_memory,
    supersede_memory,
    to_revision_snapshot,
)
from personalization_core.domain.memory import (
    confirm_memory as confirm_domain_memory,
)
from personalization_core.domain.memory import (
    restore_memory as restore_domain_memory,
)
from personalization_core.domain.types import JsonValue, UtcDatetime
from personalization_core.ports.clock import Clock
from personalization_core.ports.memory_extractor import (
    AllowAllMemoryContentFilter,
    ConversationMessage,
    EvidenceConfidenceConfirmationPolicy,
    ExactKeyMergeStrategy,
    MemoryConfirmationPolicy,
    MemoryContentFilter,
    MemoryExtraction,
    MemoryExtractor,
    MemoryMergeStrategy,
)
from personalization_core.ports.repositories import MemoryFilter, Page
from personalization_core.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

from .dto import (
    MemoryCreateInput,
    MemoryExtractionItem,
    MemoryExtractionResult,
    MemoryExtractionStatus,
    MemoryPage,
    MemoryPatchInput,
)
from .subject_service import SubjectService

_DEFAULT_STATES = frozenset(
    {
        MemoryState.CANDIDATE,
        MemoryState.ACTIVE,
        MemoryState.SUPERSEDED,
        MemoryState.EXPIRED,
    }
)
_PATCHABLE_FIELDS = (
    "content",
    "structured_value",
    "target",
    "polarity",
    "scope",
    "scope_value",
    "confidence",
    "valid_from",
    "valid_until",
)


class MemoryService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        subject_service: SubjectService,
        extractor: MemoryExtractor | None = None,
        content_filter: MemoryContentFilter | None = None,
        merge_strategy: MemoryMergeStrategy | None = None,
        confirmation_policy: MemoryConfirmationPolicy | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._subject_service = subject_service
        self._extractor = extractor
        self._content_filter = content_filter or AllowAllMemoryContentFilter()
        self._merge_strategy = merge_strategy or ExactKeyMergeStrategy()
        self._confirmation_policy = (
            confirmation_policy
            or EvidenceConfidenceConfirmationPolicy(
                min_evidence_count=1,
                min_confidence=0.5,
            )
        )

    async def add_memory(
        self, subject: SubjectRef, input: MemoryCreateInput
    ) -> MemoryRecord:
        async with self._uow_factory() as uow:
            await self._subject_service.ensure_in_uow(uow, subject)
            evidence = await self._get_or_create_evidence(
                uow, subject, input.evidence, self._clock.now()
            )
            existing = await self._find_exact_slot(
                uow,
                subject,
                key=input.key,
                scope=input.scope,
                scope_value=input.scope_value,
                states=frozenset({MemoryState.ACTIVE}),
            )
            if existing is not None and existing.content == input.content:
                memory = await self._bind_evidence_and_count(
                    uow,
                    subject,
                    existing,
                    evidence,
                    actor=input.actor,
                    reason=input.reason,
                )
                await uow.commit()
                return memory

            now = self._clock.now()
            memory = create_explicit_memory(
                subject=subject,
                key=input.key,
                kind=input.kind,
                content=input.content,
                structured_value=input.structured_value,
                target=input.target,
                polarity=input.polarity,
                scope=input.scope,
                scope_value=input.scope_value,
                confidence=input.confidence,
                valid_from=input.valid_from,
                valid_until=input.valid_until,
                evidence_count=1 if evidence is not None else 0,
                now=now,
            )
            if existing is not None:
                transition_result = supersede_memory(
                    existing,
                    replacement=memory,
                    expected_revision=existing.revision,
                    actor=input.actor,
                    reason=input.reason,
                    now=now,
                )
                await uow.memories.update(
                    subject, transition_result.memory, existing.revision
                )
                await self._record_revision(
                    uow,
                    transition_result.memory,
                    actor=input.actor,
                    reason=input.reason,
                    transition=transition_result.transition.transition,
                )
            await uow.memories.add(subject, memory)
            if evidence is not None:
                await uow.memories.bind_evidence(subject, memory.id, evidence.id)
            await self._record_revision(
                uow, memory, actor=input.actor, reason=input.reason
            )
            await uow.commit()
            return memory

    async def list_memories(
        self,
        subject: SubjectRef,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
    ) -> MemoryPage:
        requested_page = page or Page()
        async with self._uow_factory() as uow:
            await self._require_subject(uow, subject)
            effective_filters = filters or MemoryFilter()
            if effective_filters.states is None:
                effective_filters = MemoryFilter(
                    states=_DEFAULT_STATES,
                    key=effective_filters.key,
                    kind=effective_filters.kind,
                    authority=effective_filters.authority,
                    scope=effective_filters.scope,
                    scope_value=effective_filters.scope_value,
                    target_dimension=effective_filters.target_dimension,
                    target_value_key=effective_filters.target_value_key,
                )
            items = list(
                await uow.memories.list(
                    subject,
                    effective_filters,
                    Page(requested_page.limit, requested_page.offset),
                )
            )
            if requested_page.limit < 200:
                next_items = await uow.memories.list(
                    subject,
                    effective_filters,
                    Page(1, requested_page.offset + requested_page.limit),
                )
                has_more = bool(next_items)
            else:
                has_more = len(items) == requested_page.limit and bool(
                    await uow.memories.list(
                        subject,
                        effective_filters,
                        Page(1, requested_page.offset + requested_page.limit),
                    )
                )
            return MemoryPage(
                items=items,
                limit=requested_page.limit,
                offset=requested_page.offset,
                has_more=has_more,
                next_offset=(
                    requested_page.offset + requested_page.limit if has_more else None
                ),
            )

    async def search_memories(
        self,
        subject: SubjectRef,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
    ) -> MemoryPage:
        """Compatibility entry point for structured Memory retrieval.

        Full-text and vector retrieval intentionally remain in ContextService;
        this method preserves the existing default-state and pagination semantics.
        """

        return await self.list_memories(subject, filters=filters, page=page)

    async def patch_memory(
        self, subject: SubjectRef, memory_id: UUID, patch: MemoryPatchInput
    ) -> MemoryRecord:
        async with self._uow_factory() as uow:
            await self._require_subject(uow, subject)
            memory = await self._get_memory(uow, subject, memory_id)
            assert_revision(memory, patch.expected_revision)
            updates = {
                field: getattr(patch, field)
                for field in _PATCHABLE_FIELDS
                if field in patch.model_fields_set
            }
            if not updates:
                await uow.commit()
                return memory
            updated = MemoryRecord.model_validate(
                {**memory.model_dump(), **updates}
                | {
                    "revision": memory.revision + 1,
                    "updated_at": self._clock.now(),
                }
            )
            await uow.memories.update(subject, updated, patch.expected_revision)
            await self._record_revision(
                uow, updated, actor=patch.actor, reason=patch.reason
            )
            await uow.commit()
            return updated

    async def confirm_memory(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        async with self._uow_factory() as uow:
            await self._require_subject(uow, subject)
            memory = await self._get_memory(uow, subject, memory_id)
            if not self._confirmation_policy.can_confirm(memory):
                raise MemoryProtectionError("Memory does not meet confirmation policy")
            result = confirm_domain_memory(
                memory,
                expected_revision=expected_revision,
                actor=actor,
                reason=reason,
                now=self._clock.now(),
            )
            await self._save_transition(uow, subject, result, actor, reason)
            await uow.commit()
            return result.memory

    async def delete_memory(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        async with self._uow_factory() as uow:
            await self._require_subject(uow, subject)
            memory = await self._get_memory(uow, subject, memory_id)
            result = soft_delete_memory(
                memory,
                expected_revision=expected_revision,
                actor=actor,
                reason=reason,
                now=self._clock.now(),
            )
            await self._save_transition(uow, subject, result, actor, reason)
            await uow.commit()
            return result.memory

    async def restore_memory(
        self,
        subject: SubjectRef,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        async with self._uow_factory() as uow:
            await self._require_subject(uow, subject)
            memory = await self._get_memory(uow, subject, memory_id)
            previous = await uow.memory_revisions.get(
                subject, memory_id, memory.revision - 1
            )
            if previous is None:
                raise MemoryTransitionError(
                    "cannot restore Memory without a previous revision"
                )
            previous_memory = MemoryRecord.model_validate(
                previous.snapshot, strict=False
            )
            if previous_memory.subject != subject:
                raise TenantScopeViolationError(
                    "revision snapshot does not belong to subject"
                )
            result = restore_domain_memory(
                memory,
                restore_to=previous_memory.state,
                expected_revision=expected_revision,
                actor=actor,
                reason=reason,
                now=self._clock.now(),
            )
            await self._save_transition(uow, subject, result, actor, reason)
            await uow.commit()
            return result.memory

    async def extract_memories(
        self, subject: SubjectRef, messages: Sequence[ConversationMessage]
    ) -> MemoryExtractionResult:
        if self._extractor is None:
            raise ProviderInvalidResponseError("no MemoryExtractor configured")
        message_list = list(messages)
        try:
            extractions: object = await self._extractor.extract(message_list)
        except TimeoutError as exc:
            raise ProviderTimeoutError("MemoryExtractor timed out") from exc
        except OSError as exc:
            raise ProviderNetworkError("MemoryExtractor network failure") from exc
        except (ProviderTimeoutError, ProviderNetworkError):
            raise
        except Exception as exc:
            raise ProviderInvalidResponseError(
                "MemoryExtractor returned an invalid response"
            ) from exc

        validated = self._validate_extractions(message_list, extractions)
        extractor_name = self._provider_string("name")
        extractor_version = self._provider_string("version")

        # Exact-slot lookup is read-only.  The optional strategy is deliberately
        # evaluated after this read phase and before the write UoW is opened.
        exact_matches = await self._read_exact_matches(subject, validated)
        semantic_matches: list[MemoryRecord | None] = []
        for (extraction, _), exact in zip(validated, exact_matches, strict=True):
            if exact is not None:
                semantic_matches.append(None)
                continue
            try:
                semantic_matches.append(
                    self._merge_strategy.choose(None, extraction.candidate)
                )
            except Exception as exc:
                raise ProviderInvalidResponseError(
                    "Memory merge strategy failed"
                ) from exc

        async with self._uow_factory() as uow:
            await self._require_subject(uow, subject)
            items: list[MemoryExtractionItem] = []
            for index, (extraction, message) in enumerate(validated):
                existing = await self._find_exact_slot(
                    uow,
                    subject,
                    key=extraction.candidate.key,
                    scope=extraction.candidate.scope,
                    scope_value=extraction.candidate.scope_value,
                    states=frozenset({MemoryState.ACTIVE, MemoryState.CANDIDATE}),
                )
                if existing is None:
                    existing = semantic_matches[index]
                    if existing is not None:
                        if existing.subject != subject:
                            raise TenantScopeViolationError(
                                "merge strategy returned another subject"
                            )
                        persisted = await uow.memories.get(subject, existing.id)
                        if persisted is None:
                            raise ProviderInvalidResponseError(
                                "merge strategy returned an unknown Memory"
                            )
                        existing = persisted

                evidence = await self._get_or_create_evidence(
                    uow,
                    subject,
                    EvidenceCreate(
                        source_type=EvidenceSourceType.CONVERSATION,
                        source_ref=extraction.evidence_ref,
                        excerpt=extraction.evidence_quote,
                        metadata={"role": message.role},
                        occurred_at=message.occurred_at,
                    ),
                    self._clock.now(),
                )
                if evidence is None:
                    raise ProviderInvalidResponseError(
                        "conversation extraction did not create evidence"
                    )
                actor = extractor_name
                reason = "memory extraction"
                if existing is None:
                    memory = create_inferred_memory(
                        subject=subject,
                        candidate=extraction.candidate,
                        evidence_count=1,
                        now=self._clock.now(),
                    )
                    await uow.memories.add(subject, memory)
                    await uow.memories.bind_evidence(subject, memory.id, evidence.id)
                    await self._record_revision(uow, memory, actor=actor, reason=reason)
                    status = MemoryExtractionStatus.CREATED
                else:
                    memory = await self._merge_existing_extraction(
                        uow,
                        subject,
                        existing,
                        extraction,
                        evidence,
                        actor=actor,
                        reason=reason,
                    )
                    status = (
                        MemoryExtractionStatus.MERGED
                        if existing.authority == MemoryAuthority.INFERRED
                        and existing.state == MemoryState.CANDIDATE
                        else MemoryExtractionStatus.REUSED
                    )
                items.append(
                    MemoryExtractionItem(
                        status=status, memory=memory, evidence_id=evidence.id
                    )
                )
            await uow.commit()
            return MemoryExtractionResult(
                extractor_name=extractor_name,
                extractor_version=extractor_version,
                items=items,
            )

    async def _read_exact_matches(
        self,
        subject: SubjectRef,
        validated: Sequence[tuple[MemoryExtraction, ConversationMessage]],
    ) -> list[MemoryRecord | None]:
        async with self._uow_factory() as uow:
            await self._require_subject(uow, subject)
            return [
                await self._find_exact_slot(
                    uow,
                    subject,
                    key=extraction.candidate.key,
                    scope=extraction.candidate.scope,
                    scope_value=extraction.candidate.scope_value,
                    states=frozenset({MemoryState.ACTIVE, MemoryState.CANDIDATE}),
                )
                for extraction, _ in validated
            ]

    async def _require_subject(self, uow: UnitOfWork, subject: SubjectRef) -> None:
        existing = await uow.subjects.get_by_ref(subject)
        if existing is None:
            raise SubjectNotFoundError("subject does not exist")
        if existing.deleted_at is not None:
            raise SubjectDeletedError("subject is deleted")

    async def _get_memory(
        self, uow: UnitOfWork, subject: SubjectRef, memory_id: UUID
    ) -> MemoryRecord:
        memory = await uow.memories.get(subject, memory_id)
        if memory is None:
            raise MemoryNotFoundError("memory does not exist")
        return memory

    async def _find_exact_slot(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        *,
        key: str,
        scope: object,
        scope_value: str | None,
        states: frozenset[MemoryState],
    ) -> MemoryRecord | None:
        # scope is a MemoryScope at runtime; keeping this helper independent of
        # DTOs avoids making the ports layer depend on Application.
        values = await uow.memories.list(
            subject,
            MemoryFilter(
                states=states,
                key=key,
                scope=scope,  # type: ignore[arg-type]
                scope_value=scope_value,
            ),
            Page(200),
        )
        active = [item for item in values if item.state == MemoryState.ACTIVE]
        if active:
            return active[0]
        return values[0] if values else None

    async def _get_or_create_evidence(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        input: EvidenceCreate | None,
        created_at: UtcDatetime,
    ) -> Evidence | None:
        if input is None:
            return None
        existing = await uow.evidence.get_by_source(
            subject, input.source_type.value, input.source_ref
        )
        if existing is not None:
            return existing
        evidence = Evidence(
            id=uuid4(),
            subject=subject,
            source_type=input.source_type,
            source_ref=input.source_ref,
            event_id=input.event_id,
            excerpt=input.excerpt,
            metadata=dict(input.metadata),
            occurred_at=input.occurred_at,
            created_at=created_at,
        )
        await uow.evidence.add(subject, evidence)
        return evidence

    async def _bind_evidence_and_count(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        memory: MemoryRecord,
        evidence: Evidence | None,
        *,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        if evidence is None:
            return memory
        evidence_ids = set(await uow.memories.list_evidence_ids(subject, memory.id))
        if evidence.id in evidence_ids:
            return memory
        await uow.memories.bind_evidence(subject, memory.id, evidence.id)
        updated = memory.model_copy(
            update={
                "evidence_count": memory.evidence_count + 1,
                "revision": memory.revision + 1,
                "updated_at": self._clock.now(),
            }
        )
        updated = MemoryRecord.model_validate(updated.model_dump())
        await uow.memories.update(subject, updated, memory.revision)
        await self._record_revision(uow, updated, actor=actor, reason=reason)
        return updated

    async def _merge_existing_extraction(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        existing: MemoryRecord,
        extraction: MemoryExtraction,
        evidence: Evidence,
        *,
        actor: str,
        reason: str,
    ) -> MemoryRecord:
        evidence_ids = set(await uow.memories.list_evidence_ids(subject, existing.id))
        has_new_evidence = evidence.id not in evidence_ids
        updates: dict[str, JsonValue | int] = {}
        if (
            existing.authority == MemoryAuthority.INFERRED
            and existing.state == MemoryState.CANDIDATE
            and extraction.candidate.confidence > existing.confidence
        ):
            updates["confidence"] = extraction.candidate.confidence
        if not has_new_evidence and not updates:
            return existing
        await uow.memories.bind_evidence(subject, existing.id, evidence.id)
        updated = existing.model_copy(
            update={
                **updates,
                "evidence_count": existing.evidence_count + int(has_new_evidence),
                "revision": existing.revision + 1,
                "updated_at": self._clock.now(),
            }
        )
        updated = MemoryRecord.model_validate(updated.model_dump())
        await uow.memories.update(subject, updated, existing.revision)
        await self._record_revision(uow, updated, actor=actor, reason=reason)
        return updated

    async def _save_transition(
        self,
        uow: UnitOfWork,
        subject: SubjectRef,
        result: MemoryTransitionResult,
        actor: str,
        reason: str,
    ) -> None:
        await uow.memories.update(
            subject,
            result.memory,
            result.transition.previous_revision,
        )
        await self._record_revision(
            uow,
            result.memory,
            actor=actor,
            reason=reason,
            transition=result.transition.transition,
        )

    async def _record_revision(
        self,
        uow: UnitOfWork,
        memory: MemoryRecord,
        *,
        actor: str,
        reason: str,
        transition: MemoryTransitionType | None = None,
    ) -> None:
        await uow.memory_revisions.add(
            memory.subject,
            MemoryRevision(
                id=uuid4(),
                subject=memory.subject,
                memory_id=memory.id,
                revision=memory.revision,
                snapshot=to_revision_snapshot(memory),
                actor=actor,
                reason=reason,
                transition=transition,
                created_at=self._clock.now(),
            ),
        )

    def _validate_extractions(
        self,
        messages: Sequence[ConversationMessage],
        extractions: object,
    ) -> list[tuple[MemoryExtraction, ConversationMessage]]:
        if not isinstance(extractions, Sequence):
            raise ProviderInvalidResponseError("extractor response must be a sequence")
        by_ref: dict[str, ConversationMessage] = {}
        for message in messages:
            if message.evidence_ref in by_ref:
                raise ProviderInvalidResponseError("duplicate message evidence_ref")
            by_ref[message.evidence_ref] = message
        result: list[tuple[MemoryExtraction, ConversationMessage]] = []
        for raw_extraction in cast(Sequence[object], extractions):
            if not isinstance(raw_extraction, MemoryExtraction):
                raise ProviderInvalidResponseError(
                    "extractor output must contain MemoryExtraction objects"
                )
            extraction = raw_extraction
            message = by_ref.get(extraction.evidence_ref)
            if message is None:
                raise ProviderInvalidResponseError("unknown extraction evidence_ref")
            if extraction.evidence_quote not in message.content:
                raise ProviderInvalidResponseError(
                    "evidence_quote is not a substring of the message"
                )
            try:
                allowed = self._content_filter.allow(extraction.candidate, message)
            except Exception as exc:
                raise ProviderInvalidResponseError(
                    "MemoryContentFilter failed"
                ) from exc
            if type(allowed) is not bool:
                raise ProviderInvalidResponseError(
                    "MemoryContentFilter must return bool"
                )
            if allowed:
                result.append((extraction, message))
        return result

    def _provider_string(self, attribute: str) -> str:
        value = getattr(self._extractor, attribute, None)
        if not isinstance(value, str) or not value.strip():
            raise ProviderInvalidResponseError(
                f"extractor {attribute} must be a non-empty string"
            )
        return value
