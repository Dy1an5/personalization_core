from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, StringConstraints
from pydantic import JsonValue as JsonValue

NonEmptyString = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]


def _normalize_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")

    return value.astimezone(UTC)


UtcDatetime = Annotated[
    datetime,
    AfterValidator(_normalize_to_utc),
]
