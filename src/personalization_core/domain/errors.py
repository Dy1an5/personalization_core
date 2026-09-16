from enum import StrEnum
from typing import ClassVar

from .types import JsonValue


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SUBJECT_NOT_FOUND = "SUBJECT_NOT_FOUND"
    SUBJECT_DELETED = "SUBJECT_DELETED"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    MEMORY_NOT_FOUND = "MEMORY_NOT_FOUND"
    MEMORY_ERROR = "MEMORY_ERROR"
    MEMORY_PROTECTION_ERROR = "MEMORY_PROTECTION_ERROR"
    MEMORY_TRANSITION_ERROR = "MEMORY_TRANSITION_ERROR"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    TENANT_SCOPE_VIOLATION = "TENANT_SCOPE_VIOLATION"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_NETWORK_ERROR = "PROVIDER_NETWORK_ERROR"
    PROVIDER_INVALID_RESPONSE = "PROVIDER_INVALID_RESPONSE"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    PURGE_CONFIRMATION_REQUIRED = "PURGE_CONFIRMATION_REQUIRED"


class DomainError(Exception):
    code: ClassVar[ErrorCode]

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidArgumentError(DomainError):
    code = ErrorCode.INVALID_ARGUMENT


class SubjectNotFoundError(DomainError):
    code = ErrorCode.SUBJECT_NOT_FOUND


class SubjectDeletedError(DomainError):
    code = ErrorCode.SUBJECT_DELETED


class EntityNotFoundError(DomainError):
    code = ErrorCode.ENTITY_NOT_FOUND


class MemoryNotFoundError(DomainError):
    code = ErrorCode.MEMORY_NOT_FOUND


class MemoryError(DomainError):
    code = ErrorCode.MEMORY_ERROR


class MemoryTransitionError(DomainError):
    code = ErrorCode.MEMORY_TRANSITION_ERROR


class MemoryProtectionError(DomainError):
    code = ErrorCode.MEMORY_PROTECTION_ERROR


class RevisionConflictError(DomainError):
    code = ErrorCode.REVISION_CONFLICT

    def __init__(
        self,
        *,
        expected_revision: int,
        actual_revision: int,
    ) -> None:
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision

        super().__init__(
            "memory revision conflict: "
            f"expected={expected_revision}, actual={actual_revision}"
        )


class IdempotencyConflictError(DomainError):
    code = ErrorCode.IDEMPOTENCY_CONFLICT


class TenantScopeViolationError(DomainError):
    code = ErrorCode.TENANT_SCOPE_VIOLATION


class ProviderTimeoutError(DomainError):
    code = ErrorCode.PROVIDER_TIMEOUT


class ProviderNetworkError(DomainError):
    code = ErrorCode.PROVIDER_NETWORK_ERROR


class ProviderInvalidResponseError(DomainError):
    code = ErrorCode.PROVIDER_INVALID_RESPONSE


class ProcessingFailedError(DomainError):
    code = ErrorCode.PROCESSING_FAILED


class PurgeConfirmationRequiredError(DomainError):
    code = ErrorCode.PURGE_CONFIRMATION_REQUIRED
