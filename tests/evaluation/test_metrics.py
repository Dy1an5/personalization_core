import pytest

from personalization_core.evaluation.metrics import (
    context_constraint_retention,
    memory_extraction_precision,
    profile_change_sensitivity,
    profile_stability,
    retrieval_mrr,
    retrieval_recall_at_k,
    tenant_isolation_leakage_rate,
)
from personalization_core.evaluation.models import (
    ConstraintRetentionCase,
    MemoryExtractionCase,
    ProfileCase,
    ProfilePreference,
    RetrievalCase,
    TenantIsolationCase,
)

pytestmark = pytest.mark.unit


def test_extraction_precision_counts_false_positives() -> None:
    result = memory_extraction_precision(
        [
            MemoryExtractionCase(
                case_id="case",
                expected_keys=["a"],
                predicted_keys=["a", "false-positive"],
            )
        ],
        target=0.5,
    )

    assert result.value == 0.5
    assert result.numerator == 1
    assert result.denominator == 2


def test_retrieval_recall_and_mrr_use_first_relevant_rank() -> None:
    cases = [
        RetrievalCase(
            case_id="first",
            relevant_ids=["a"],
            ranked_ids=["a", "b"],
            k=1,
        ),
        RetrievalCase(
            case_id="second",
            relevant_ids=["b"],
            ranked_ids=["a", "b"],
            k=1,
        ),
    ]

    assert retrieval_recall_at_k(cases, target=0.5).value == 0.5
    assert retrieval_mrr(cases, target=0.75).value == 0.75


def test_constraint_retention_does_not_count_unknown_ids() -> None:
    result = context_constraint_retention(
        [
            ConstraintRetentionCase(
                case_id="constraints",
                constraint_ids=["required"],
                retained_ids=["required", "unknown"],
            )
        ]
    )

    assert result.value == 1.0


def test_profile_metrics_separate_stability_from_expected_changes() -> None:
    cases = [
        ProfileCase(
            case_id="stable",
            before=[
                ProfilePreference(dimension="topic", value_key="a", state="positive")
            ],
            after=[
                ProfilePreference(dimension="topic", value_key="a", state="positive")
            ],
        ),
        ProfileCase(
            case_id="changed",
            before=[
                ProfilePreference(dimension="topic", value_key="b", state="positive")
            ],
            after=[
                ProfilePreference(dimension="topic", value_key="b", state="negative")
            ],
            expected_changed=["topic:b"],
        ),
    ]

    assert profile_stability(cases).value == 1.0
    assert profile_change_sensitivity(cases).value == 1.0


def test_tenant_leakage_is_lower_is_better() -> None:
    result = tenant_isolation_leakage_rate(
        [
            TenantIsolationCase(
                case_id="leak",
                allowed_ids=["subject:a"],
                returned_ids=["subject:a", "subject:b"],
            )
        ]
    )

    assert result.value == 0.5
    assert not result.passed


def test_invalid_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError):
        MemoryExtractionCase(
            case_id="duplicate",
            expected_keys=["a", "a"],
            predicted_keys=["a"],
        )
