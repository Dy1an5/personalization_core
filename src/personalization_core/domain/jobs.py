from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import StrictFrozenDomainModel
from .identifiers import SubjectRef
from .types import NonEmptyString, UtcDatetime


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProcessingRun(StrictFrozenDomainModel):
    id: UUID
    subject: SubjectRef
    operation: NonEmptyString
    status: ProcessingStatus
    algorithm_version: NonEmptyString
    started_at: UtcDatetime
    finished_at: UtcDatetime | None = None
    processed_count: int = Field(default=0, ge=0, strict=True)
    failed_count: int = Field(default=0, ge=0, strict=True)
    error_code: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ProcessingRun:
        terminal = self.status in {
            ProcessingStatus.SUCCEEDED,
            ProcessingStatus.FAILED,
        }
        if terminal != (self.finished_at is not None):
            raise ValueError("terminal status and finished_at must be set together")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")
        if self.status == ProcessingStatus.FAILED and self.error_code is None:
            raise ValueError("failed run requires error_code")
        if self.status != ProcessingStatus.FAILED and self.error_code is not None:
            raise ValueError("only failed run can have error_code")
        return self
