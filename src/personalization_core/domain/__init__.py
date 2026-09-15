"""阶段 1 冻结的领域层公共类型。

本模块的 ``__all__`` 是公共命名契约：任何新增、删除或重命名都必须
同步更新 ``test/unit/domain/test_public_api.py`` 中的冻结快照。
"""

from .base import DomainModel, FrozenDomainModel
from .enums import Polarity
from .errors import (
    DomainError,
    EntityNotFoundError,
    ErrorCode,
    IdempotencyConflictError,
    InvalidArgumentError,
    MemoryNotFoundError,
    ProcessingFailedError,
    ProviderInvalidResponseError,
    ProviderNetworkError,
    ProviderTimeoutError,
    PurgeConfirmationRequiredError,
    RevisionConflictError,
    SubjectDeletedError,
    SubjectNotFoundError,
    TenantScopeViolationError,
)
from .identifiers import EntityRef, Namespace, SubjectId, SubjectRef, TenantId
from .types import JsonValue, UtcDatetime

__all__ = [
    "DomainError",
    "DomainModel",
    "EntityNotFoundError",
    "EntityRef",
    "ErrorCode",
    "FrozenDomainModel",
    "IdempotencyConflictError",
    "InvalidArgumentError",
    "JsonValue",
    "MemoryNotFoundError",
    "Namespace",
    "Polarity",
    "ProcessingFailedError",
    "ProviderInvalidResponseError",
    "ProviderNetworkError",
    "ProviderTimeoutError",
    "PurgeConfirmationRequiredError",
    "RevisionConflictError",
    "SubjectDeletedError",
    "SubjectId",
    "SubjectNotFoundError",
    "SubjectRef",
    "TenantId",
    "TenantScopeViolationError",
    "UtcDatetime",
]
