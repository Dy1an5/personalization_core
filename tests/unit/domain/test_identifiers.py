"""阶段 1.8：标识符的空白、长度和大小写契约（plan.md §5）。

冻结的行为：
- 纯空白字符串非法；
- 只去除首尾空白，内部空白与大小写保留；
- tenant_id / namespace 最长 100，subject_id 最长 200。
"""

from typing import Final

import pytest
from pydantic import ValidationError

from personalization_core.domain.identifiers import (
    EntityRef,
    Namespace,
    SubjectId,
    SubjectRef,
    TenantId,
)

pytestmark = pytest.mark.unit

SMALLER_IDENTIFIERS: Final = [TenantId, Namespace]
BIGGER_IDENTIFIERS: Final = [SubjectId]
ALL_IDENTIFIERS: Final = [*SMALLER_IDENTIFIERS, *BIGGER_IDENTIFIERS]

ALL_IDENTIFIER_PARAMS: Final = [
    pytest.param(cls, id=cls.__name__) for cls in ALL_IDENTIFIERS
]
SMALLER_IDENTIFIER_PARAMS: Final = [
    pytest.param(cls, id=cls.__name__) for cls in SMALLER_IDENTIFIERS
]
BIGGER_IDENTIFIER_PARAMS: Final = [
    pytest.param(cls, id=cls.__name__) for cls in BIGGER_IDENTIFIERS
]

BLANK_VALUES: Final = [
    pytest.param("", id="empty"),
    pytest.param(" ", id="ascii-space"),
    pytest.param("\t\n", id="tab-newline"),
    pytest.param("  \t  ", id="mixed-ascii"),
    pytest.param("\u00a0", id="no-break-space"),
    pytest.param("\u3000", id="ideographic-space"),
]

STRIPPING_CASES: Final = [
    pytest.param("  tenant-1  ", "tenant-1", id="ascii-space"),
    pytest.param("\ttenant-1\n", "tenant-1", id="tab-newline"),
    pytest.param("\u3000tenant-1\u3000", "tenant-1", id="ideographic-space"),
]

SUBJECT_PAYLOAD: Final = {
    "tenant_id": "tenant-1",
    "namespace": "default",
    "subject_id": "user-1",
}


def _error_types(exc_info: pytest.ExceptionInfo[ValidationError]) -> list[str]:
    return [str(error["type"]) for error in exc_info.value.errors()]


def _subject_payload(**overrides: str) -> dict[str, str]:
    return {**SUBJECT_PAYLOAD, **overrides}


def _entity_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "subject": dict(SUBJECT_PAYLOAD),
        "entity_type": "video",
        "external_id": "external-1",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("identifier_cls", ALL_IDENTIFIER_PARAMS)
@pytest.mark.parametrize("value", BLANK_VALUES)
def test_blank_identifier_is_rejected(
    identifier_cls: type[TenantId], value: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        identifier_cls(value)

    assert _error_types(exc_info) == ["string_too_short"]


@pytest.mark.parametrize("identifier_cls", ALL_IDENTIFIER_PARAMS)
def test_single_character_identifier_is_valid(identifier_cls: type[TenantId]) -> None:
    assert identifier_cls("a").root == "a"


@pytest.mark.parametrize("identifier_cls", ALL_IDENTIFIER_PARAMS)
@pytest.mark.parametrize(("raw", "expected"), STRIPPING_CASES)
def test_surrounding_whitespace_is_stripped(
    identifier_cls: type[TenantId], raw: str, expected: str
) -> None:
    assert identifier_cls(raw).root == expected


@pytest.mark.parametrize("identifier_cls", ALL_IDENTIFIER_PARAMS)
def test_case_is_preserved(identifier_cls: type[TenantId]) -> None:
    upper = identifier_cls("User-1")
    lower = identifier_cls("user-1")

    assert upper.root == "User-1"
    assert lower.root == "user-1"
    assert upper != lower


@pytest.mark.parametrize("identifier_cls", ALL_IDENTIFIER_PARAMS)
def test_only_surrounding_whitespace_is_normalized(
    identifier_cls: type[TenantId],
) -> None:
    # 当前契约只做首尾去空白，内部空白属于调用方自定义内容。
    assert identifier_cls("tenant 1").root == "tenant 1"


@pytest.mark.parametrize("identifier_cls", ALL_IDENTIFIER_PARAMS)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param("\u7528\u6237-1", id="chinese"),
        pytest.param("U\u0308n\u00efcode", id="latin-diacritics"),
        pytest.param("\U0001f600-user", id="emoji"),
    ],
)
def test_non_ascii_identifier_is_preserved(
    identifier_cls: type[TenantId], value: str
) -> None:
    assert identifier_cls(value).root == value


@pytest.mark.parametrize("identifier_cls", ALL_IDENTIFIER_PARAMS)
def test_non_string_input_is_rejected(identifier_cls: type[TenantId]) -> None:
    for value in (123, 1.5, None, ["tenant-1"], {"tenant_id": "tenant-1"}):
        with pytest.raises(ValidationError) as exc_info:
            identifier_cls.model_validate(value)

        assert _error_types(exc_info) == ["string_type"]


@pytest.mark.parametrize("identifier_cls", SMALLER_IDENTIFIER_PARAMS)
def test_smaller_identifier_length_limit(identifier_cls: type[TenantId]) -> None:
    assert identifier_cls("a" * 100).root == "a" * 100

    with pytest.raises(ValidationError) as exc_info:
        identifier_cls("a" * 101)

    assert _error_types(exc_info) == ["string_too_long"]


@pytest.mark.parametrize("identifier_cls", BIGGER_IDENTIFIER_PARAMS)
def test_bigger_identifier_length_limit(identifier_cls: type[TenantId]) -> None:
    assert identifier_cls("a" * 200).root == "a" * 200

    with pytest.raises(ValidationError) as exc_info:
        identifier_cls("a" * 201)

    assert _error_types(exc_info) == ["string_too_long"]


@pytest.mark.parametrize("identifier_cls", SMALLER_IDENTIFIER_PARAMS)
def test_padding_does_not_count_towards_length_limit(
    identifier_cls: type[TenantId],
) -> None:
    assert identifier_cls(" " + "a" * 100 + " ").root == "a" * 100

    with pytest.raises(ValidationError) as exc_info:
        identifier_cls(" " + "a" * 101 + " ")

    assert _error_types(exc_info) == ["string_too_long"]


@pytest.mark.parametrize("identifier_cls", [*ALL_IDENTIFIERS])
def test_identifier_types_are_not_interchangeable(
    identifier_cls: type[TenantId],
) -> None:
    other_cls = next(cls for cls in ALL_IDENTIFIERS if cls is not identifier_cls)

    assert identifier_cls("user-1") != other_cls("user-1")


def test_subject_ref_validates_plain_string_payload() -> None:
    ref = SubjectRef.model_validate(SUBJECT_PAYLOAD)

    assert isinstance(ref.tenant_id, TenantId)
    assert ref.tenant_id.root == "tenant-1"
    assert ref.namespace.root == "default"
    assert ref.subject_id.root == "user-1"


def test_subject_ref_normalizes_nested_identifiers() -> None:
    padded = SubjectRef.model_validate(
        _subject_payload(
            tenant_id=" tenant-1 ",
            namespace=" default ",
            subject_id=" user-1 ",
        )
    )

    assert padded == SubjectRef.model_validate(SUBJECT_PAYLOAD)


@pytest.mark.parametrize("missing_field", ["tenant_id", "namespace", "subject_id"])
def test_subject_ref_requires_every_scope_field(missing_field: str) -> None:
    payload = _subject_payload()
    del payload[missing_field]

    with pytest.raises(ValidationError) as exc_info:
        SubjectRef.model_validate(payload)

    error = exc_info.value.errors()[0]
    assert error["type"] == "missing"
    assert error["loc"] == (missing_field,)


def test_subject_ref_rejects_blank_nested_identifier() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SubjectRef.model_validate(_subject_payload(subject_id="   "))

    errors = exc_info.value.errors()
    assert [str(error["type"]) for error in errors] == ["string_too_short"]
    assert errors[0]["loc"] == ("subject_id",)


def test_subject_ref_rejects_misplaced_identifier_type() -> None:
    # 走 model_validate 而不是构造函数：这里要验证的是运行时的类型拒绝，
    # 而不是让静态类型检查去阻止这个（非法的）调用。
    with pytest.raises(ValidationError) as exc_info:
        SubjectRef.model_validate(
            {
                "tenant_id": Namespace("tenant-1"),
                "namespace": Namespace("default"),
                "subject_id": SubjectId("user-1"),
            }
        )

    error = exc_info.value.errors()[0]
    assert error["type"] == "string_type"
    assert error["loc"] == ("tenant_id",)


def test_entity_ref_validates_nested_subject_ref() -> None:
    ref = EntityRef.model_validate(_entity_payload())

    assert isinstance(ref.subject, SubjectRef)
    assert ref.subject == SubjectRef.model_validate(SUBJECT_PAYLOAD)
    assert ref.entity_type == "video"
    assert ref.external_id == "external-1"


@pytest.mark.parametrize("missing_field", ["subject", "entity_type", "external_id"])
def test_entity_ref_requires_subject_and_local_identity(missing_field: str) -> None:
    payload = _entity_payload()
    del payload[missing_field]

    with pytest.raises(ValidationError) as exc_info:
        EntityRef.model_validate(payload)

    error = exc_info.value.errors()[0]
    assert error["type"] == "missing"
    assert error["loc"] == (missing_field,)


def test_entity_ref_length_limits() -> None:
    entity_type = EntityRef.model_validate(_entity_payload(entity_type="a" * 100))
    external_id = EntityRef.model_validate(_entity_payload(external_id="b" * 200))

    assert entity_type.entity_type == "a" * 100
    assert external_id.external_id == "b" * 200

    for field, too_long in (("entity_type", "a" * 101), ("external_id", "b" * 201)):
        with pytest.raises(ValidationError) as exc_info:
            EntityRef.model_validate(_entity_payload(**{field: too_long}))

        error = exc_info.value.errors()[0]
        assert error["type"] == "string_too_long"
        assert error["loc"] == (field,)


def test_entity_ref_normalizes_local_identity_whitespace() -> None:
    ref = EntityRef.model_validate(
        _entity_payload(entity_type=" video ", external_id=" external-1 ")
    )

    assert ref.entity_type == "video"
    assert ref.external_id == "external-1"
