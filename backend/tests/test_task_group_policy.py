"""Software fixtures only: do not use these synthetic rows as live evidence."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from app.contracts.dtos import ChatRequest
from app.routing.task_groups import TaskGroupPolicy, content_hash, hint


def request(message, **kwargs):
    return ChatRequest(
        session_id="s", client_request_id="r", mode="optimized", message=message, **kwargs
    )


@pytest.mark.parametrize(
    ("message", "family"),
    [
        ("xin chào", "simple_conversation"),
        ("Tính 1 + 1. Chỉ trả lời số.", "exact_arithmetic"),
        ("Chỉ trả lời JSON", "structured_extraction"),
        ("Tóm tắt đoạn văn và nhớ tên tôi", "hybrid"),
        ("Viết Python và tóm tắt giải pháp", "code_reasoning"),
        ("Bạn nhớ tên tôi không?", "memory_recall"),
        ("Câu không xác định", "unknown"),
    ],
)
def test_conservative_shadow_hints(message, family):
    task = hint(request(message))
    assert task["family"] == family
    assert task["source"] == "observable_shadow"


def fixture_bundle(tmp_path):
    artifact = SimpleNamespace(
        configuration_hashes={"small": "a", "reference": "b"},
        costs_hash="cost",
        predictors=[SimpleNamespace(config_id="small")],
    )
    engine = SimpleNamespace(hash="ml", multi=SimpleNamespace(artifact=artifact))
    profile = {
        "thresholds": {"small": 0.95},
        "platt": {"small": [1.0, 0.0]},
        "quality_fallbacks": [],
    }
    bundle = dict(
        version="task-groups-v1",
        policy_version="fixture-only",
        ml_artifact_hash="ml",
        configuration_hashes=artifact.configuration_hashes,
        costs_hash="cost",
        classifier=None,
        profiles={"simple_conversation": profile},
    )
    report = dict(
        profile_sha256=content_hash(profile),
        classifier_sha256=content_hash(None),
        ml_artifact_hash="ml",
        configuration_hashes=artifact.configuration_hashes,
        costs_hash="cost",
        latency_scope="serving_e2e",
        reviewed_by="test-only",
        grader_review_id="test-only",
        synthetic=False,
        family="simple_conversation",
        thresholds=profile["thresholds"],
        dev_group_ids=["dev"],
        all_in_p50_ratio=1.0,
        holdout=[
            dict(
                group_id=f"holdout-{i}",
                prior_pass=True,
                policy_pass=True,
                critical_regression=False,
            )
            for i in range(100)
        ],
    )
    path = tmp_path / "bundle.json"

    def save():
        raw = json.dumps(report).encode()
        (tmp_path / "evidence.json").write_bytes(raw)
        profile.update(
            evidence_path="evidence.json", evidence_sha256=hashlib.sha256(raw).hexdigest()
        )
        path.write_text(json.dumps(bundle))

    save()
    return path, engine, bundle, report, save


def test_missing_bundle_keeps_old_policy(tmp_path):
    policy = TaskGroupPolicy(tmp_path / "missing.json", None)
    assert policy.status == "GROUP_POLICY_MISSING_SHADOW"
    assert policy.quality_candidates(hint(request("hello"))) == set()


def test_software_fixture_gate_accepts_exact_bound_evidence(tmp_path):
    path, engine, _, _, _ = fixture_bundle(tmp_path)
    assert TaskGroupPolicy(path, engine).status == "GROUP_POLICY_READY"


@pytest.mark.parametrize(
    "defect",
    [
        "few",
        "overlap",
        "regression",
        "slow",
        "synthetic",
        "provider_time",
        "changed_calibration",
        "changed_classifier",
        "fallback_without_evidence",
        "critical",
    ],
)
def test_bad_evidence_never_activates_profile(tmp_path, defect):
    path, engine, bundle, report, save = fixture_bundle(tmp_path)
    if defect == "few":
        report["holdout"].pop()
    elif defect == "overlap":
        report["dev_group_ids"] = ["holdout-0"]
    elif defect == "regression":
        report["holdout"][0]["policy_pass"] = False
    elif defect == "slow":
        report["all_in_p50_ratio"] = 1.11
    elif defect == "synthetic":
        report["synthetic"] = True
    elif defect == "provider_time":
        report["latency_scope"] = "provider_only"
    elif defect == "critical":
        report["holdout"][0]["critical_regression"] = True
    elif defect == "changed_calibration":
        bundle["profiles"]["simple_conversation"]["platt"]["small"] = [2.0, 0.0]
    elif defect == "changed_classifier":
        bundle["classifier"] = {"bad": "data"}
    elif defect == "fallback_without_evidence":
        bundle["profiles"]["simple_conversation"]["quality_fallbacks"] = ["reference"]
    save()
    assert TaskGroupPolicy(path, engine).status == "GROUP_POLICY_INVALID_SHADOW"


@pytest.mark.parametrize(
    "defect",
    [None, "missing_pilot", "few_pairs", "duplicate_pair", "no_saving", "latency", "unresolved",
     "zero_latency", "nan_cost", "negative_cost", "string_verdict", "string_resolved"],
)
def test_new_family_requires_real_paired_cost_and_latency_evidence(tmp_path, defect):
    path, engine, bundle, report, save = fixture_bundle(tmp_path)
    profile = bundle["profiles"]["simple_conversation"]
    profile["scope"] = "single_turn_no_memory_no_tools"
    payload = {k: v for k, v in profile.items() if k not in ("evidence_path", "evidence_sha256")}
    report["profile_sha256"] = content_hash(payload)
    report["policy_serving_usd"] = ".01"
    report["prior_serving_usd"] = ".02"
    pilot = {
        "profile_sha256": report["profile_sha256"],
        "classifier_sha256": report["classifier_sha256"],
        "all_costs_resolved": True,
        "pairs": [
            dict(
                pair_id=str(i),
                prior_pass=True,
                policy_pass=True,
                critical_regression=False,
                prior_usd=".002",
                policy_usd=".001",
                prior_ms=100,
                policy_ms=90,
            )
            for i in range(20)
        ],
    }
    report["serving_pilot"] = pilot
    if defect == "missing_pilot":
        del report["serving_pilot"]
    elif defect == "few_pairs":
        pilot["pairs"].pop()
    elif defect == "duplicate_pair":
        pilot["pairs"][1]["pair_id"] = "0"
    elif defect == "no_saving":
        report["policy_serving_usd"] = ".03"
    elif defect == "latency":
        for pair in pilot["pairs"]:
            pair["policy_ms"] = 111
    elif defect == "unresolved":
        pilot["all_costs_resolved"] = False
    elif defect == "zero_latency":
        for pair in pilot["pairs"]:
            pair["prior_ms"] = 0
    elif defect == "nan_cost":
        pilot["pairs"][0]["policy_usd"] = "nan"
    elif defect == "negative_cost":
        pilot["pairs"][0]["policy_usd"] = "-.001"
    elif defect == "string_verdict":
        pilot["pairs"][0]["policy_pass"] = "false"
    elif defect == "string_resolved":
        pilot["all_costs_resolved"] = "false"
    save()
    expected = "GROUP_POLICY_READY" if defect is None else "GROUP_POLICY_INVALID_SHADOW"
    assert TaskGroupPolicy(path, engine).status == expected
