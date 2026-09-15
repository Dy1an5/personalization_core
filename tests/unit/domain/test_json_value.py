"""阶段 1.1：``JsonValue`` 递归类型契约（plan.md §6.2/§6.3/§6.4/§6.5）。

.. warning::

   **本文件目前是故意失败的（TDD 契约先行，plan.md §0）。**

   ``domain/types.py`` 里的 ``JsonValue`` 是手写的隐式递归别名
   （``str | int | ... | list["JsonValue"] | dict[str, JsonValue]``），
   pydantic 无法为它构建 schema，因此下面每个用例都会在调用
   ``TypeAdapter(...)`` / 声明模型字段时抛 ``RecursionError``。

   契约冻结的行为：
   - 接受全部 JSON 标量与任意嵌套的 list/dict；
   - 拒绝 datetime / set / bytes / 任意对象等非 JSON 值；
   - 作为模型字段时可通过 ``model_dump(mode="json")`` 与 ``json.dumps`` 序列化；
   - 序列化再反序列化结果稳定，bool 不被当成 int。

   修好 ``JsonValue`` 后本文件应当全绿，无需修改任何断言。
"""

import json
from datetime import datetime
from typing import Final

import pytest
from pydantic import TypeAdapter, ValidationError

from personalization_core.domain.base import DomainModel
from personalization_core.domain.types import JsonValue

pytestmark = pytest.mark.unit

JSON_SCALARS: Final = [
    pytest.param("text", id="str"),
    pytest.param(0, id="int-zero"),
    pytest.param(-42, id="int-negative"),
    pytest.param(1.5, id="float"),
    pytest.param(True, id="bool-true"),
    pytest.param(False, id="bool-false"),
    pytest.param(None, id="null"),
]

NESTED_JSON: Final[dict[str, JsonValue]] = {
    "string": "value",
    "number": 1.5,
    "integer": 7,
    "boolean": False,
    "null": None,
    "list": [1, "two", None, {"deep": [True, 3.5]}],
    "object": {"nested": {"deeper": ["x"]}},
}

NON_JSON_VALUES: Final = [
    pytest.param(datetime(2024, 1, 1), id="datetime"),
    pytest.param({1, 2}, id="set"),
    pytest.param(b"bytes", id="bytes"),
    pytest.param(object(), id="plain-object"),
]


@pytest.mark.parametrize("value", JSON_SCALARS)
def test_type_adapter_accepts_json_scalars(value: object) -> None:
    adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

    assert adapter.validate_python(value) == value


def test_type_adapter_accepts_nested_containers() -> None:
    adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

    assert adapter.validate_python(NESTED_JSON) == NESTED_JSON


def test_type_adapter_accepts_empty_containers() -> None:
    adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

    assert adapter.validate_python({}) == {}
    assert adapter.validate_python([]) == []


@pytest.mark.parametrize("value", NON_JSON_VALUES)
def test_type_adapter_rejects_non_json_values(value: object) -> None:
    adapter: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

    with pytest.raises(ValidationError):
        adapter.validate_python(value)


def test_model_field_accepts_nested_json() -> None:
    class Model(DomainModel):
        properties: dict[str, JsonValue]

    model = Model(properties=NESTED_JSON)

    assert model.properties == NESTED_JSON


@pytest.mark.parametrize("value", NON_JSON_VALUES)
def test_model_field_rejects_non_json_values(value: object) -> None:
    class Model(DomainModel):
        properties: dict[str, JsonValue]

    with pytest.raises(ValidationError):
        Model.model_validate({"properties": {"key": value}})


def test_model_field_is_json_serializable() -> None:
    class Model(DomainModel):
        properties: dict[str, JsonValue]

    model = Model(properties=NESTED_JSON)

    dumped = model.model_dump(mode="json")

    assert json.loads(json.dumps(dumped)) == {"properties": NESTED_JSON}
    assert Model.model_validate_json(model.model_dump_json()) == model


def test_boolean_is_not_coerced_to_int() -> None:
    class Model(DomainModel):
        properties: dict[str, JsonValue]

    model = Model(properties={"flag": True})

    assert model.properties["flag"] is True
