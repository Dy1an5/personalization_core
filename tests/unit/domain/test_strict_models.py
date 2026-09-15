"""阶段 1.10：所有公共模型禁止未知字段（plan.md §0 / §2.3）。

模型输出一律视为不可信输入，未知字段必须报错而不是被静默忽略。

注意：Pydantic 明确禁止在 ``RootModel`` 上设置 ``model_config['extra']``
（https://errors.pydantic.dev/2.13/u/root-model-extra）。因此本文件把公共模型
分成两类：
- 字段模型：必须配置 ``extra='forbid'``，未知字段报 ``extra_forbidden``；
- RootModel 包装的标量标识符：输入本身就是标量，任何 mapping 都会被
  直接判为 ``string_type``，未知字段没有可被静默接受的通道。

新增公共模型时必须同时在 ``VALUE_PAYLOADS`` 或 ``ROOT_MODELS`` 中登记，
否则 ``test_every_public_model_is_covered`` 会失败。
"""

from typing import Final

import pytest
from pydantic import BaseModel, RootModel, ValidationError

from personalization_core import domain
from personalization_core.domain.base import DomainModel, FrozenDomainModel
from personalization_core.domain.identifiers import (
    EntityRef,
    Namespace,
    SubjectId,
    SubjectRef,
    TenantId,
)

pytestmark = pytest.mark.unit


def _public_model_classes() -> list[type[BaseModel]]:
    models: list[type[BaseModel]] = []
    for name in domain.__all__:
        candidate = getattr(domain, name)
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            models.append(candidate)

    return sorted(models, key=lambda cls: cls.__name__)


PUBLIC_MODELS: Final = _public_model_classes()
PUBLIC_MODEL_PARAMS: Final = [
    pytest.param(cls, id=cls.__name__) for cls in PUBLIC_MODELS
]

# 字段模型：额外字段必须在 model_validate 时被拒绝。
VALUE_PAYLOADS: Final[dict[type[BaseModel], dict[str, object]]] = {
    DomainModel: {},
    FrozenDomainModel: {},
    SubjectRef: {
        "tenant_id": "tenant-1",
        "namespace": "default",
        "subject_id": "user-1",
    },
    EntityRef: {
        "subject": {
            "tenant_id": "tenant-1",
            "namespace": "default",
            "subject_id": "user-1",
        },
        "entity_type": "video",
        "external_id": "external-1",
    },
}
VALUE_PAYLOAD_PARAMS: Final = [
    pytest.param(cls, id=cls.__name__) for cls in VALUE_PAYLOADS
]

# RootModel 标量包装：无法配置 extra，改为验证 mapping 输入被整体拒绝。
ROOT_MODELS: Final = (TenantId, Namespace, SubjectId)
ROOT_MODEL_PARAMS: Final = [pytest.param(cls, id=cls.__name__) for cls in ROOT_MODELS]


def test_every_public_model_is_covered() -> None:
    assert PUBLIC_MODELS, "未从 domain.__all__ 中发现任何公共模型"

    covered = set(VALUE_PAYLOADS) | set(ROOT_MODELS)
    assert set(PUBLIC_MODELS) == covered, (
        "公共模型必须在本文件的 VALUE_PAYLOADS 或 ROOT_MODELS 中登记："
        f"未登记={sorted(cls.__name__ for cls in set(PUBLIC_MODELS) - covered)}，"
        f"已过期={sorted(cls.__name__ for cls in covered - set(PUBLIC_MODELS))}"
    )


def _is_root_model(model_cls: type[BaseModel]) -> bool:
    # 放进函数返回 bool，避免 RootModel[Unknown] 的收窄结果污染集合类型。
    return issubclass(model_cls, RootModel)


def test_field_models_and_root_models_are_classified_correctly() -> None:
    root_models = {cls for cls in PUBLIC_MODELS if _is_root_model(cls)}

    assert root_models == set(ROOT_MODELS)
    assert not any(_is_root_model(cls) for cls in VALUE_PAYLOADS)


@pytest.mark.parametrize("model_cls", VALUE_PAYLOAD_PARAMS)
def test_field_model_configures_extra_forbid(model_cls: type[BaseModel]) -> None:
    assert model_cls.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("model_cls", VALUE_PAYLOAD_PARAMS)
def test_extra_field_is_rejected(model_cls: type[BaseModel]) -> None:
    payload = {**VALUE_PAYLOADS[model_cls], "unexpected_field": "value"}

    with pytest.raises(ValidationError) as exc_info:
        model_cls.model_validate(payload)

    errors = exc_info.value.errors()
    assert [str(error["type"]) for error in errors] == ["extra_forbidden"]
    assert errors[0]["loc"] == ("unexpected_field",)


@pytest.mark.parametrize("model_cls", VALUE_PAYLOAD_PARAMS)
def test_registered_payload_is_itself_valid(model_cls: type[BaseModel]) -> None:
    assert isinstance(model_cls.model_validate(VALUE_PAYLOADS[model_cls]), BaseModel)


@pytest.mark.parametrize("model_cls", ROOT_MODEL_PARAMS)
def test_root_model_accepts_its_wrapped_scalar(model_cls: type[BaseModel]) -> None:
    validated = model_cls.model_validate("tenant-1")

    assert isinstance(validated, model_cls)
    assert validated.model_dump() == "tenant-1"


@pytest.mark.parametrize("model_cls", ROOT_MODEL_PARAMS)
def test_root_model_rejects_any_mapping_payload(model_cls: type[BaseModel]) -> None:
    with pytest.raises(ValidationError) as exc_info:
        model_cls.model_validate({"root": "tenant-1", "unexpected_field": "value"})

    assert exc_info.value.errors()[0]["type"] == "string_type"


def test_extra_forbid_is_inherited_by_subclasses() -> None:
    class _Child(DomainModel):
        name: str

    with pytest.raises(ValidationError) as exc_info:
        _Child.model_validate({"name": "n", "unexpected_field": 1})

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


def test_frozen_domain_model_rejects_attribute_assignment() -> None:
    class _FrozenChild(FrozenDomainModel):
        name: str

    child = _FrozenChild(name="n")

    with pytest.raises(ValidationError) as exc_info:
        child.name = "m"

    assert exc_info.value.errors()[0]["type"] == "frozen_instance"
