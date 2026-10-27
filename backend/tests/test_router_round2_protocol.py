"""Retired HOLDOUT handling and safe quota waiting; no live data or provider calls."""

import importlib.util
import json

import pytest

from app.config import ROOT
from app.contracts.dtos import CallRecord


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("round2_pilot_runner", "run_router_pilot.py")
training = load("round2_training", "train_router_round2.py")
families = load("round2_families", "router_family_protocol.py")
evaluation = load("round2_evaluation", "evaluate_router_round2.py")


@pytest.mark.parametrize("state", ["unknown", "completed"])
def test_quota_wait_never_replays_uncertain_or_completed_dispatch(state):
    call = CallRecord(
        call_id="test",
        model_id="fake",
        error_code="RATE_LIMITED",
        dispatch_state=state,
        retry_after_seconds=2,
    )
    assert runner.quota_retry_delay(call, 300) is None


@pytest.mark.parametrize("state", ["not_dispatched", "rejected"])
def test_quota_wait_obeys_retry_after_and_wait_cap(state):
    call = CallRecord(
        call_id="test",
        model_id="fake",
        error_code="RATE_LIMITED",
        dispatch_state=state,
        retry_after_seconds=125,
    )
    assert runner.quota_retry_delay(call, 300) == 126
    assert runner.quota_retry_delay(call, 125) is None
    assert (
        runner.quota_retry_delay(call.model_copy(update={"error_code": "PROVIDER_TIMEOUT"}), 300)
        is None
    )
    assert runner.quota_retry_delay(None, 300) is None


def test_old_test_groups_are_explicitly_retired_and_reproducible():
    groups = [f"old-source-{i}" for i in range(1000)]
    assigned = {g: training.retired_dev_split(g) for g in groups}
    assert set(assigned.values()) == {"train", "calibration", "threshold"}
    assert assigned == {g: training.retired_dev_split(g) for g in reversed(groups)}
    assert "holdout" not in assigned.values()


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("Chọn đáp án B.\n\nGiải thích từ nguồn.", "B"),
        ("Lời giải\n\n2 + 2 = 4\n\nĐáp án cần chọn là: A", "A"),
        ("Đáp án A.\nĐáp án B.", None),
        ("a) đáp án phần một\nb) đáp án phần hai\nc) đáp án phần ba", None),
        ("Tôi nghĩ đáp án là B", None),
        ("Đáp án D", None),
    ],
)
def test_original_explicit_answer_adaptation(target, expected):
    result = families.explicit_gold("Question\nA. one\nB. two\nC. three", target)
    assert (result[0] if result else None) == expected


def test_source_family_grouping_is_order_independent_and_does_not_count_wrappers():
    body = " ".join(
        ["Một người đang đứng trong căn phòng bên cạnh cửa sổ và quan sát bầu trời."] * 12
    )
    texts = {
        "one": body + "\nA. xanh\nB. đỏ\nC. vàng",
        "variant": "Hãy chọn đáp án đúng:\n" + body + "\nA. xanh\nB. đỏ\nC. vàng",
        "different": "Calculate the integral of a polynomial from zero to infinity.",
    }
    grouped = families.family_map(texts)
    assert grouped == families.family_map(dict(reversed(list(texts.items()))))
    assert grouped["one"] == grouped["variant"]
    assert grouped["different"] != grouped["one"]


def test_expanded_training_never_deserializes_new_holdout_and_keeps_families_together(tmp_path):
    from decimal import Decimal

    from app.contracts.dtos import CostSnapshot, Message, ModelConfiguration, RouteRate
    from app.contracts.training import TrainingManifest, TrainingSource
    from app.routing.ml.multi_training import MultiSample, Observation

    source = TrainingSource(
        local_path="test-only", sha256="a" * 64, license="fixture", provenance="offline test"
    )
    models = tuple(
        ModelConfiguration(config_id=k, model_id=k, context_window=10000)
        for k in ("reference", "small", "medium")
    )
    manifest = TrainingManifest(
        version="fixture",
        reviewed_by="test",
        pricing_source="fake",
        software_test=True,
        source=source,
        configurations=models,
        reference_config_id="reference",
        costs=CostSnapshot(
            version="fake",
            rates=tuple(
                RouteRate(config_id=k, input_per_million=Decimal(1), output_per_million=Decimal(1))
                for k in ("reference", "small", "medium")
            ),
        ),
    )
    root = tmp_path / "campaign"
    previous, pilot, partial, current = (
        root / "old",
        root / "pilot",
        root / "runs" / "superseded",
        root / "runs" / "current",
    )

    def row(task, group):
        return MultiSample(
            task_id=task,
            group_id=group,
            domain="vietnamese_mcq",
            split="train",
            messages=(Message(role="user", content=task),),
            observations=tuple(
                Observation(
                    config_id=k,
                    qualified=True,
                    usd=Decimal(".001"),
                    latency_ms=10,
                    input_tokens=1,
                    output_tokens=1,
                )
                for k in ("reference", "small", "medium")
            ),
        ).model_dump(mode="json")

    # Intentionally missing all observation fields in held-out cases: fitting
    # must filter on input metadata before it could parse these outcomes.
    sealed = {
        "task_id": "sealed",
        "group_id": "test-source",
        "domain": "vietnamese_mcq",
        "split": "holdout",
    }
    for path, rows in [
        (previous, [row("old", "old-source")]),
        (pilot, [row("variant", "alias-source")]),
        (partial, [row("fresh", "fresh-source"), sealed]),
        (current, [row("fresh", "fresh-source"), sealed]),
    ]:
        path.mkdir(parents=True)
        (path / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
        (path / "observations.json").write_text(json.dumps(rows), encoding="utf-8")
    (root / "independent-family-plan.json").write_text(
        json.dumps(
            {
                "family_map": {
                    "old-source": "same-family",
                    "alias-source": "same-family",
                    "test-source": "test-family",
                },
                "mcq_holdout_families": ["test-family"],
                "superseded_job_id": "superseded",
            }
        ),
        encoding="utf-8",
    )
    result = training.expanded_dev(previous, pilot, current, manifest, allow_partial=True)
    assert {r.task_id for r in result.samples} == {"old", "variant", "fresh"}
    same = [r for r in result.samples if r.group_id == "same-family"]
    assert len(same) == 2 and len({r.split for r in same}) == 1
    assert not any(r.split == "holdout" or r.group_id == "test-family" for r in result.samples)


def test_incomplete_test_cannot_emit_a_full_report(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        evaluation, "available_holdout", lambda _: (object(), [{"task_id": "unmeasured"}])
    )
    path = tmp_path / "full-report.json"
    with pytest.raises(ValueError, match="incomplete"):
        evaluation.run(SimpleNamespace(campaign=tmp_path, report=path, partial=False))
    assert not path.exists()


@pytest.mark.asyncio
async def test_daily_quota_diagnostic_keeps_only_safe_category(monkeypatch):
    from app.contracts.errors import AppError
    from app.providers.openai_compatible import OpenAICompatibleProvider

    async def rejected(self, messages, opts):
        upstream = RuntimeError("private")
        upstream.message = "Private organization identifier; Rate limit on tokens per day"
        raise AppError(
            "RATE_LIMITED",
            429,
            "Provider request failed",
            upstream_status=429,
            dispatch_state="rejected",
        ) from upstream

    monkeypatch.setattr(OpenAICompatibleProvider, "generate", rejected)
    provider = object.__new__(runner.PilotProvider)
    with pytest.raises(AppError) as error:
        await provider.generate((), None)
    assert provider.last_quota_category == "tokens_per_day"
    assert "Private" not in error.value.message
    assert runner.quota_category("requests per minute") == "requests_per_minute"
    assert runner.quota_category("something private") == "unspecified"
