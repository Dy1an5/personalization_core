"""阶段 1.9：naive datetime 拒绝策略（plan.md §0 / 阶段 1 验收）。

冻结的行为：
- naive datetime（含无时区的 ISO 字符串）必须被拒绝；
- 任何带时区的时间统一归一化为 UTC；
- 归一化不改变时刻，只改变表示。
"""

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Final

import pytest
from pydantic import TypeAdapter, ValidationError

from personalization_core.domain.base import DomainModel
from personalization_core.domain.types import UtcDatetime

pytestmark = pytest.mark.unit

UTC_ADAPTER: Final[TypeAdapter[datetime]] = TypeAdapter(UtcDatetime)

NAIVE_DATETIMES: Final = [
    pytest.param(datetime(2024, 1, 1), id="midnight"),
    pytest.param(datetime(2024, 1, 1, 12, 30, 45, 123456), id="with-microseconds"),
    pytest.param(datetime.now(), id="now"),
    pytest.param(datetime(2024, 1, 1) + timedelta(days=1), id="arithmetic-result"),
]

NAIVE_ISO_STRINGS: Final = [
    pytest.param("2024-01-01T00:00:00", id="iso-without-offset"),
    pytest.param("2024-01-01 00:00:00", id="space-separated"),
    pytest.param("2024-01-01", id="date-only"),
    pytest.param("2024-01-01T00:00:00.000000", id="with-microseconds"),
]

OFFSET_DATETIMES: Final = [
    pytest.param(
        datetime(2024, 1, 1, 8, 0, tzinfo=timezone(timedelta(hours=8))),
        datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        id="plus-8",
    ),
    pytest.param(
        datetime(2024, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=-5))),
        datetime(2024, 1, 1, 5, 0, tzinfo=UTC),
        id="minus-5",
    ),
    pytest.param(
        datetime(2024, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        datetime(2023, 12, 31, 18, 30, tzinfo=UTC),
        id="plus-5-30",
    ),
    pytest.param(
        datetime(2024, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=-9, minutes=-30))),
        datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
        id="minus-9-30",
    ),
    pytest.param(
        datetime(2024, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=14))),
        datetime(2023, 12, 31, 10, 0, tzinfo=UTC),
        id="plus-14",
    ),
]

AWARE_ISO_STRINGS: Final = [
    pytest.param(
        "2024-01-01T08:00:00+08:00",
        datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        id="plus-8",
    ),
    pytest.param(
        "2024-01-01T00:00:00Z",
        datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        id="zulu",
    ),
    pytest.param(
        "2024-01-01T00:00:00+00:00",
        datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        id="explicit-utc",
    ),
    pytest.param(
        "2023-12-31T19:00:00-05:00",
        datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        id="minus-5",
    ),
]


class _NoOffsetTzInfo(tzinfo):
    """tzinfo 存在但 utcoffset() 返回 None，仍必须视为 naive。"""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None


class _Timestamped(DomainModel):
    occurred_at: UtcDatetime


@pytest.mark.parametrize("value", NAIVE_DATETIMES)
def test_naive_datetime_is_rejected(value: datetime) -> None:
    with pytest.raises(ValidationError) as exc_info:
        UTC_ADAPTER.validate_python(value)

    error = exc_info.value.errors()[0]
    assert error["type"] == "value_error"
    assert "timezone-aware" in str(error["msg"])


@pytest.mark.parametrize("raw", NAIVE_ISO_STRINGS)
def test_naive_iso_string_is_rejected(raw: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        UTC_ADAPTER.validate_python(raw)

    assert exc_info.value.errors()[0]["type"] == "value_error"


def test_datetime_without_usable_utcoffset_is_rejected() -> None:
    naive_like = datetime(2024, 1, 1, tzinfo=_NoOffsetTzInfo())

    with pytest.raises(ValidationError) as exc_info:
        UTC_ADAPTER.validate_python(naive_like)

    assert exc_info.value.errors()[0]["type"] == "value_error"


def test_utc_datetime_is_returned_unchanged() -> None:
    value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    result = UTC_ADAPTER.validate_python(value)

    assert result == value
    assert result.tzinfo is UTC
    assert result.utcoffset() == timedelta(0)


@pytest.mark.parametrize(("aware", "expected_utc"), OFFSET_DATETIMES)
def test_offset_datetime_is_normalized_to_utc(
    aware: datetime, expected_utc: datetime
) -> None:
    result = UTC_ADAPTER.validate_python(aware)

    assert result == expected_utc
    assert result.tzinfo is UTC
    assert result == aware  # 归一化不改变时刻


@pytest.mark.parametrize(("aware", "expected_utc"), OFFSET_DATETIMES)
def test_normalization_is_idempotent(aware: datetime, expected_utc: datetime) -> None:
    once = UTC_ADAPTER.validate_python(aware)
    twice = UTC_ADAPTER.validate_python(once)

    assert once == twice == expected_utc
    assert twice.tzinfo is UTC


@pytest.mark.parametrize(("raw", "expected_utc"), AWARE_ISO_STRINGS)
def test_aware_iso_string_is_normalized_to_utc(
    raw: str, expected_utc: datetime
) -> None:
    result = UTC_ADAPTER.validate_python(raw)

    assert result == expected_utc
    assert result.tzinfo is UTC


def test_model_field_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _Timestamped(occurred_at=datetime(2024, 1, 1))

    error = exc_info.value.errors()[0]
    assert error["type"] == "value_error"
    assert error["loc"] == ("occurred_at",)


def test_model_field_normalizes_offset_datetime() -> None:
    model = _Timestamped(
        occurred_at=datetime(2024, 1, 1, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    )

    assert model.occurred_at == datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    assert model.occurred_at.tzinfo is UTC
