import pytest

from personalization_core.infrastructure.observability.metrics import (
    MetricsRegistry,
    safe_metric_label,
    safe_metric_path,
)

pytestmark = pytest.mark.unit


def test_metrics_do_not_store_subject_ids_in_paths() -> None:
    registry = MetricsRegistry()
    registry.increment(
        "http_requests_total",
        labels={"path": safe_metric_path("/v1/subjects/user-secret/events")},
    )

    snapshot = registry.snapshot()
    assert "user-secret" not in str(snapshot)
    assert "/v1/subjects/{subject_id}/events" in str(snapshot)


def test_metrics_collect_counters_gauges_and_latency() -> None:
    registry = MetricsRegistry()
    registry.provider_call("provider", "embed", "success")
    registry.set_processing_backlog(3)
    registry.observe_latency("request", 12.5, labels={"path": "/health"})

    snapshot = registry.snapshot()
    assert snapshot["gauges"]["processing_backlog"] == 3.0
    assert snapshot["latencies"]["request{path=/health}"]["count"] == 1
    assert any("provider_calls_total" in key for key in snapshot["counters"])


def test_metric_label_is_bounded_and_normalized() -> None:
    value = safe_metric_label("bad value\n" + "x" * 200)
    assert " " not in value
    assert len(value) <= 80
