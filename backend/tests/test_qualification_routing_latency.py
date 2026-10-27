"""A fast provider must not hide slow Attention or an inferior routing policy."""

import pytest

from app.routing.ml.qualification import runtime_guard_issues


def measured(provider_ratio=0.9, complete_ratio=1.0, quality=0.9, cost=0.1):
    return {
        "report": {"p50_ratio": provider_ratio, "observed_pass_rate": quality, "serving_usd": cost},
        "all_in_p50_ratio": complete_ratio,
    }


def test_fast_provider_cannot_hide_attention_overhead_past_latency_guard():
    result = runtime_guard_issues(
        measured(complete_ratio=1.18), measured(quality=0.8, complete_ratio=1.0)
    )
    assert "HOLDOUT_LATENCY_GUARD_FAILED" in result


def test_identical_routes_with_slower_attention_are_dominated():
    result = runtime_guard_issues(measured(complete_ratio=1.05), measured(complete_ratio=0.96))
    assert "ML_WITHOUT_ATTENTION_DOMINATES" in result
    assert "HOLDOUT_LATENCY_GUARD_FAILED" not in result


def test_attention_quality_improvement_is_not_erased_by_faster_ablation():
    assert (
        runtime_guard_issues(
            measured(quality=0.95, complete_ratio=1.05), measured(quality=0.9, complete_ratio=0.96)
        )
        == []
    )


@pytest.mark.parametrize("missing", [None, float("nan"), float("inf"), -1, True])
def test_missing_or_invalid_routing_measurements_cannot_pass(missing):
    a, b = measured(), measured()
    a["all_in_p50_ratio"] = missing
    b["all_in_p50_ratio"] = missing
    result = runtime_guard_issues(a, b)
    assert "HOLDOUT_LATENCY_GUARD_FAILED" in result
    assert "ABLATION_ROUTING_TIMING_REQUIRED" in result
