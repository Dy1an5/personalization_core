from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from personalization_core.public import Polarity, UtcDatetime


class _AdapterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BilibiliVideo(_AdapterModel):
    video_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    duration_seconds: float = Field(ge=0)
    topics: list[str] = Field(default_factory=list)
    popularity_score: float = Field(ge=0, le=1)

    @field_validator("video_id", "title", "creator_id", mode="before")
    @classmethod
    def validate_text(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("value must be a non-blank string")
        return value.strip()

    @field_validator("topics", mode="before")
    @classmethod
    def normalize_topics(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("topics must be a list")
        result: list[str] = []
        raw_topics = cast(list[Any], value)
        for topic in raw_topics:
            if not isinstance(topic, str) or not topic.strip():
                raise ValueError("topics must contain non-blank strings")
            normalized = topic.strip()
            if normalized not in result:
                result.append(normalized)
        return result


class BilibiliWatchEvent(_AdapterModel):
    video: BilibiliVideo
    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    occurred_at: UtcDatetime
    watched_seconds: float = Field(ge=0)
    polarity: Polarity = Polarity.POSITIVE

    @field_validator("event_id", mode="before")
    @classmethod
    def validate_event_id(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("event_id must be a non-blank string")
        return value.strip()

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("event_type must be a string")
        normalized = value.strip()
        prefix = "bilibili.video."
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
        if normalized not in {"viewed", "liked", "completed"}:
            raise ValueError("unsupported Bilibili event type")
        return normalized
