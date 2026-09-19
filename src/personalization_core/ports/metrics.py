from __future__ import annotations

from typing import Protocol


class MetricsSink(Protocol):
    """Application-facing metrics hooks implemented by infrastructure adapters."""

    def provider_call(self, provider: str, operation: str, status: str) -> None: ...

    def set_processing_backlog(self, value: int) -> None: ...
