"""Small dependency-free runtime metrics registry."""

from __future__ import annotations

import re
from collections import defaultdict
from threading import Lock
from time import monotonic
from typing import Any, Final

_LABEL_RE: Final = re.compile(r"[^a-zA-Z0-9_./:{}-]")
_SUBJECT_PATH_RE: Final = re.compile(r"(/subjects/)[^/]+")
_MAX_LABEL_LENGTH: Final = 80


def safe_metric_label(value: object) -> str:
    """Normalize labels so IDs, secrets, and unbounded user input are not stored."""

    normalized = _LABEL_RE.sub("_", str(value))[:_MAX_LABEL_LENGTH]
    return normalized or "unknown"


def safe_metric_path(path: str) -> str:
    return _SUBJECT_PATH_RE.sub(r"\1{subject_id}", path.split("?", 1)[0])


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: defaultdict[tuple[str, tuple[tuple[str, str], ...]], int] = (
            defaultdict(int)
        )
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._latencies: defaultdict[
            tuple[str, tuple[tuple[str, str], ...]], list[float]
        ] = defaultdict(list)

    @staticmethod
    def _key(
        name: str, labels: dict[str, object] | None
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        normalized = tuple(
            sorted(
                (safe_metric_label(key), safe_metric_label(value))
                for key, value in (labels or {}).items()
            )
        )
        return safe_metric_label(name), normalized

    def increment(
        self, name: str, amount: int = 1, *, labels: dict[str, object] | None = None
    ) -> None:
        if amount < 0:
            raise ValueError("counter increment must be non-negative")
        with self._lock:
            self._counters[self._key(name, labels)] += amount

    def set_gauge(
        self, name: str, value: float, *, labels: dict[str, object] | None = None
    ) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = float(value)

    def observe_latency(
        self, name: str, milliseconds: float, *, labels: dict[str, object] | None = None
    ) -> None:
        if milliseconds < 0:
            raise ValueError("latency must be non-negative")
        with self._lock:
            self._latencies[self._key(name, labels)].append(float(milliseconds))

    def provider_call(self, provider: str, operation: str, status: str) -> None:
        self.increment(
            "provider_calls_total",
            labels={"provider": provider, "operation": operation, "status": status},
        )

    def set_processing_backlog(self, value: int) -> None:
        if value < 0:
            raise ValueError("processing backlog must be non-negative")
        self.set_gauge("processing_backlog", value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = {
                self._format_key(key): value for key, value in self._counters.items()
            }
            gauges = {
                self._format_key(key): value for key, value in self._gauges.items()
            }
            latencies = {
                self._format_key(key): {
                    "count": len(values),
                    "sum_ms": round(sum(values), 3),
                    "max_ms": round(max(values), 3) if values else 0.0,
                }
                for key, values in self._latencies.items()
            }
        return {"counters": counters, "gauges": gauges, "latencies": latencies}

    @staticmethod
    def _format_key(key: tuple[str, tuple[tuple[str, str], ...]]) -> str:
        name, labels = key
        if not labels:
            return name
        return name + "{" + ",".join(f"{k}={v}" for k, v in labels) + "}"


def elapsed_milliseconds(start: float) -> float:
    return (monotonic() - start) * 1000.0
