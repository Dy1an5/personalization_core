import json

import pytest

from personalization_core.evaluation.report import render_json, render_markdown
from personalization_core.evaluation.runner import (
    default_dataset_path,
    load_dataset,
    run_evaluation,
)

pytestmark = pytest.mark.unit


def test_minimal_dataset_meets_deterministic_targets() -> None:
    report = run_evaluation(load_dataset())

    assert report.passed
    assert report.metrics[0].name == "memory_extraction_precision"
    assert report.metrics[2].name == "memory_retrieval_recall_at_5"
    assert report.metrics[2].value >= 0.85
    assert report.metrics[8].value == 0.0


def test_report_rendering_is_parseable_and_stable() -> None:
    report = run_evaluation(load_dataset(default_dataset_path()))

    parsed = json.loads(render_json(report))
    markdown = render_markdown(report)
    assert parsed["dataset_name"] == "evaluation"
    assert "| Metric | Value | Target |" in markdown
    assert markdown == render_markdown(report)
