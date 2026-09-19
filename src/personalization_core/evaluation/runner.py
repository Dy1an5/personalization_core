"""Dataset loading and deterministic evaluation orchestration."""

from __future__ import annotations

import json
from pathlib import Path

from .metrics import (
    context_constraint_retention,
    memory_extraction_precision,
    memory_extraction_recall,
    preference_conflict_accuracy,
    profile_change_sensitivity,
    profile_stability,
    provider_failure_mapping_accuracy,
    retrieval_mrr,
    retrieval_recall_at_k,
    tenant_isolation_leakage_rate,
)
from .models import EvaluationDataset, EvaluationReport, MetricResult

_DATASET_PATH = Path(__file__).with_name("datasets") / "minimal.json"


def default_dataset_path() -> Path:
    return _DATASET_PATH


def load_dataset(path: str | Path | None = None) -> EvaluationDataset:
    source = Path(path) if path is not None else _DATASET_PATH
    if source.is_dir():
        source = source / "minimal.json"
    with source.open(encoding="utf-8") as handle:
        return EvaluationDataset.model_validate(json.load(handle))


def run_evaluation(
    dataset: EvaluationDataset, dataset_name: str = "evaluation"
) -> EvaluationReport:
    metrics: list[MetricResult] = [
        memory_extraction_precision(dataset.memory_extraction),
        memory_extraction_recall(dataset.memory_extraction),
        retrieval_recall_at_k(dataset.memory_retrieval),
        retrieval_mrr(dataset.memory_retrieval),
        preference_conflict_accuracy(dataset.preference_conflicts),
        context_constraint_retention(dataset.constraint_retention),
        profile_stability(dataset.profiles),
        profile_change_sensitivity(dataset.profiles),
        tenant_isolation_leakage_rate(dataset.tenant_isolation),
        provider_failure_mapping_accuracy(dataset.provider_failures),
    ]
    return EvaluationReport(dataset_name=dataset_name, metrics=metrics)
