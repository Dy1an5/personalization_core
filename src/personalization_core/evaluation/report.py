"""Stable report renderers for evaluation results."""

from __future__ import annotations

import json

from .models import EvaluationReport


def render_json(report: EvaluationReport) -> str:
    return report.model_dump_json(indent=2) + "\n"


def render_markdown(report: EvaluationReport) -> str:
    lines = [
        f"# Evaluation report: {report.dataset_name}",
        "",
        f"Overall: **{'PASS' if report.passed else 'FAIL'}**",
        "",
        "| Metric | Value | Target | Numerator | Denominator | Status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for metric in report.metrics:
        lines.append(
            "| {name} | {value:.6f} | {target:.6f} | {numerator:.3f} | "
            "{denominator:.3f} | {status} |".format(
                name=metric.name,
                value=metric.value,
                target=metric.target,
                numerator=metric.numerator,
                denominator=metric.denominator,
                status="PASS" if metric.passed else "FAIL",
            )
        )
    return "\n".join(lines) + "\n"


def report_as_dict(report: EvaluationReport) -> dict[str, object]:
    """Return a JSON-compatible mapping for callers that need structured output."""

    return json.loads(render_json(report))
