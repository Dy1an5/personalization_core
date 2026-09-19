"""Pure metric implementations for deterministic evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .models import (
    ConflictCase,
    ConstraintRetentionCase,
    MemoryExtractionCase,
    MetricResult,
    ProfileCase,
    ProviderFailureCase,
    RetrievalCase,
    TenantIsolationCase,
)


def _result(
    name: str,
    numerator: int | float,
    denominator: int | float,
    target: float,
    *,
    lower_is_better: bool = False,
) -> MetricResult:
    if denominator <= 0:
        raise ValueError(f"{name} requires a positive denominator")
    value = round(float(numerator) / float(denominator), 12)
    passed = value <= target if lower_is_better else value >= target
    return MetricResult(
        name=name,
        value=value,
        numerator=float(numerator),
        denominator=float(denominator),
        target=target,
        passed=passed,
    )


def _intersection_size(left: Iterable[str], right: Iterable[str]) -> int:
    return len(set(left) & set(right))


def memory_extraction_precision(
    cases: Sequence[MemoryExtractionCase], target: float = 0.90
) -> MetricResult:
    true_positive = sum(
        _intersection_size(case.expected_keys, case.predicted_keys) for case in cases
    )
    predicted = sum(len(case.predicted_keys) for case in cases)
    return _result("memory_extraction_precision", true_positive, predicted, target)


def memory_extraction_recall(
    cases: Sequence[MemoryExtractionCase], target: float = 0.90
) -> MetricResult:
    true_positive = sum(
        _intersection_size(case.expected_keys, case.predicted_keys) for case in cases
    )
    expected = sum(len(case.expected_keys) for case in cases)
    return _result("memory_extraction_recall", true_positive, expected, target)


def _retrieval_k(cases: Sequence[RetrievalCase]) -> int:
    values = {case.k for case in cases}
    return next(iter(values)) if len(values) == 1 else 0


def retrieval_recall_at_k(
    cases: Sequence[RetrievalCase], target: float = 0.85
) -> MetricResult:
    k = _retrieval_k(cases)
    name = f"memory_retrieval_recall_at_{k}" if k else "memory_retrieval_recall_at_k"
    hits = sum(
        _intersection_size(case.relevant_ids, case.ranked_ids[: case.k])
        for case in cases
    )
    relevant = sum(len(case.relevant_ids) for case in cases)
    return _result(name, hits, relevant, target)


def retrieval_mrr(cases: Sequence[RetrievalCase], target: float = 0.85) -> MetricResult:
    reciprocal_sum = 0.0
    for case in cases:
        relevant = set(case.relevant_ids)
        rank = next(
            (
                index
                for index, item in enumerate(case.ranked_ids, 1)
                if item in relevant
            ),
            None,
        )
        reciprocal_sum += 0.0 if rank is None else 1.0 / rank
    return _result("memory_retrieval_mrr", reciprocal_sum, len(cases), target)


def preference_conflict_accuracy(
    cases: Sequence[ConflictCase], target: float = 1.0
) -> MetricResult:
    correct = sum(
        case.expected_resolution == case.observed_resolution for case in cases
    )
    return _result("preference_conflict_accuracy", correct, len(cases), target)


def context_constraint_retention(
    cases: Sequence[ConstraintRetentionCase], target: float = 1.0
) -> MetricResult:
    retained = sum(
        _intersection_size(case.constraint_ids, case.retained_ids) for case in cases
    )
    constraints = sum(len(case.constraint_ids) for case in cases)
    return _result("context_constraint_retention_rate", retained, constraints, target)


def _profile_changes(case: ProfileCase) -> set[str]:
    before = {item.coordinate: item.state for item in case.before}
    after = {item.coordinate: item.state for item in case.after}
    return {
        coordinate
        for coordinate in before.keys() | after.keys()
        if before.get(coordinate) != after.get(coordinate)
    }


def profile_stability(
    cases: Sequence[ProfileCase], target: float = 1.0
) -> MetricResult:
    unchanged = 0
    coordinates = 0
    for case in cases:
        if case.expected_changed:
            continue
        before = {item.coordinate: item.state for item in case.before}
        after = {item.coordinate: item.state for item in case.after}
        keys = before.keys() | after.keys()
        unchanged += sum(before.get(key) == after.get(key) for key in keys)
        coordinates += len(keys)
    return _result("profile_stability", unchanged, coordinates, target)


def profile_change_sensitivity(
    cases: Sequence[ProfileCase], target: float = 1.0
) -> MetricResult:
    detected = 0
    expected = 0
    for case in cases:
        changes = _profile_changes(case)
        expected += max(len(case.expected_changed), 1)
        if case.expected_changed:
            detected += len(changes & set(case.expected_changed))
        elif not changes:
            detected += 1
    return _result("profile_change_sensitivity", detected, expected, target)


def tenant_isolation_leakage_rate(
    cases: Sequence[TenantIsolationCase], target: float = 0.0
) -> MetricResult:
    leaked = sum(len(set(case.returned_ids) - set(case.allowed_ids)) for case in cases)
    returned = sum(len(case.returned_ids) for case in cases)
    return _result(
        "tenant_isolation_leakage_rate",
        leaked,
        returned,
        target,
        lower_is_better=True,
    )


def provider_failure_mapping_accuracy(
    cases: Sequence[ProviderFailureCase], target: float = 1.0
) -> MetricResult:
    correct = sum(
        case.expected_error_code == case.observed_error_code for case in cases
    )
    return _result("provider_failure_mapping_accuracy", correct, len(cases), target)
