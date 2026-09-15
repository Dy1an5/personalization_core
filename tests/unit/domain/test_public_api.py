"""阶段 1.11：公共类型导出与命名冻结（plan.md §4 / 阶段 1 验收）。

``personalization_core.domain.__all__`` 是公共契约快照。任何新增、删除或
重命名都会让本文件失败，必须显式修改 ``EXPECTED_PUBLIC_API`` 才能通过，
以此迫使公共命名变更被 review。
"""

import ast
import sys
from pathlib import Path
from typing import Final

import pytest

from personalization_core import domain
from personalization_core.domain import ErrorCode, Polarity
from personalization_core.domain.errors import DomainError

pytestmark = pytest.mark.unit

EXPECTED_PUBLIC_API: Final = frozenset(
    {
        # base
        "DomainModel",
        "FrozenDomainModel",
        # types
        "JsonValue",
        "UtcDatetime",
        # identifiers
        "EntityRef",
        "Namespace",
        "SubjectId",
        "SubjectRef",
        "TenantId",
        # enums
        "Polarity",
        # errors
        "DomainError",
        "ErrorCode",
        "EntityNotFoundError",
        "IdempotencyConflictError",
        "InvalidArgumentError",
        "MemoryNotFoundError",
        "ProcessingFailedError",
        "ProviderInvalidResponseError",
        "ProviderNetworkError",
        "ProviderTimeoutError",
        "PurgeConfirmationRequiredError",
        "RevisionConflictError",
        "SubjectDeletedError",
        "SubjectNotFoundError",
        "TenantScopeViolationError",
    }
)

EXPECTED_ERROR_CODES: Final = frozenset(
    {
        "INVALID_ARGUMENT",
        "SUBJECT_NOT_FOUND",
        "SUBJECT_DELETED",
        "ENTITY_NOT_FOUND",
        "MEMORY_NOT_FOUND",
        "REVISION_CONFLICT",
        "IDEMPOTENCY_CONFLICT",
        "TENANT_SCOPE_VIOLATION",
        "PROVIDER_TIMEOUT",
        "PROVIDER_NETWORK_ERROR",
        "PROVIDER_INVALID_RESPONSE",
        "PROCESSING_FAILED",
        "PURGE_CONFIRMATION_REQUIRED",
    }
)

EXPECTED_POLARITIES: Final = frozenset({"positive", "neutral", "negative", "unknown"})

ALLOWED_THIRD_PARTY_IMPORTS: Final = frozenset({"pydantic", "typing_extensions"})
DOMAIN_PACKAGE_DIR: Final = Path(str(domain.__file__)).parent


def _all_error_classes() -> list[type[DomainError]]:
    classes: list[type[DomainError]] = []
    pending: list[type[DomainError]] = list(DomainError.__subclasses__())
    while pending:
        cls = pending.pop()
        classes.append(cls)
        pending.extend(cls.__subclasses__())

    return sorted(classes, key=lambda cls: cls.__name__)


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])

    return modules


def test_domain_public_api_is_frozen() -> None:
    actual = set(domain.__all__)

    assert actual == set(EXPECTED_PUBLIC_API), (
        f"新增={sorted(actual - EXPECTED_PUBLIC_API)}，"
        f"删除={sorted(EXPECTED_PUBLIC_API - actual)}"
    )


def test_domain_all_is_unique_and_sorted() -> None:
    exported = list(domain.__all__)

    assert len(exported) == len(set(exported))
    assert exported == sorted(exported)


def test_every_exported_name_is_public_and_importable() -> None:
    for name in domain.__all__:
        assert not name.startswith("_")
        assert hasattr(domain, name)
        assert not isinstance(getattr(domain, name), type(sys))


def test_star_import_exposes_exactly_all() -> None:
    namespace: dict[str, object] = {}
    exec("from personalization_core.domain import *", namespace)  # noqa: S102

    assert {name for name in namespace if not name.startswith("__")} == set(
        domain.__all__
    )


def test_polarity_values_are_frozen() -> None:
    assert {member.value for member in Polarity} == set(EXPECTED_POLARITIES)


def test_error_code_values_are_frozen() -> None:
    assert {member.value for member in ErrorCode} == set(EXPECTED_ERROR_CODES)


def test_domain_error_base_declares_no_code() -> None:
    # 基类只是声明 code，具体值必须由子类提供。
    assert getattr(DomainError, "code", None) is None


def test_every_error_code_has_exactly_one_error_class() -> None:
    classes = _all_error_classes()

    missing_code = [
        cls.__name__ for cls in classes if getattr(cls, "code", None) is None
    ]
    assert missing_code == []

    codes = [str(cls.code) for cls in classes]
    assert len(codes) == len(set(codes)), f"重复的 error code：{codes}"
    assert set(codes) == {str(member) for member in ErrorCode}


def test_every_error_class_is_exported() -> None:
    exported = set(domain.__all__)

    for cls in _all_error_classes():
        assert cls.__name__ in exported


def test_domain_only_depends_on_stdlib_and_pydantic() -> None:
    violations: dict[str, list[str]] = {}
    for path in sorted(DOMAIN_PACKAGE_DIR.rglob("*.py")):
        outsiders = sorted(
            module
            for module in _imported_top_level_modules(path)
            if module not in sys.stdlib_module_names
            and module not in ALLOWED_THIRD_PARTY_IMPORTS
        )
        if outsiders:
            violations[path.name] = outsiders

    assert violations == {}, f"domain 只能依赖标准库与 Pydantic：{violations}"
