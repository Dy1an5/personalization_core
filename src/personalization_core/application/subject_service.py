from __future__ import annotations

from uuid import uuid4

from personalization_core.domain.errors import InvalidArgumentError, SubjectDeletedError
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.subjects import Subject
from personalization_core.domain.types import JsonValue
from personalization_core.ports.clock import Clock
from personalization_core.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory


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
