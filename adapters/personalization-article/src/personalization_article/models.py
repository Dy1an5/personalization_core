from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from personalization_core.public import UtcDatetime


class _AdapterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Article(_AdapterModel):
    article_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    topics: list[str] = Field(default_factory=list)

    @field_validator("article_id", "title", mode="before")
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


class ArticleRead(_AdapterModel):
    article: Article
    event_id: str = Field(min_length=1)
    occurred_at: UtcDatetime
    progress: float = Field(ge=0, le=1)

    @field_validator("event_id", mode="before")
    @classmethod
    def validate_event_id(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("event_id must be a non-blank string")
        return value.strip()
