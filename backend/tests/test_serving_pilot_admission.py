"""Paid E2E measurement requires complete independently qualified offline evidence."""

import importlib.util
from types import SimpleNamespace

import pytest

from app.config import ROOT
from app.contracts.dtos import Message
from app.contracts.training import GradingSpec, RawTrainingSample, TrainingCorpus

spec = importlib.util.spec_from_file_location(
    "serving_pilot_admission", ROOT / "scripts/run_router_serving_pilot.py"
)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def sample(task_id):
    return RawTrainingSample(
        task_id=task_id,
        group_id=task_id,
        domain="functional",
        split="holdout",
        messages=(Message(role="user", content=task_id),),
        gold="1",
        grading=GradingSpec(kind="numeric"),
    )


def test_partial_replay_never_dispatches_paid_serving_pilot(tmp_path, monkeypatch):
    rows = tuple(sample(str(i)) for i in range(16))
    (tmp_path / "corpus.json").write_text(
        TrainingCorpus(samples=rows).model_dump_json(), encoding="utf-8"
    )

    def never(*args):
        raise AssertionError("Must reject missing cases before further evaluation")

    monkeypatch.setattr(runner, "qualify", never)
    with pytest.raises(ValueError, match="Complete frozen HOLDOUT"):
        runner.validate_frozen_pilot_input(tmp_path, SimpleNamespace(samples=rows[:-1]))


@pytest.mark.parametrize(
    "extra",
    [
        None,
        "INSUFFICIENT_OR_FAILED_DOMAIN_EVIDENCE:math_reasoning",
        "ML_WITHOUT_ATTENTION_DOMINATES",
        "TRAINING_DATA_HASH_MISMATCH",
    ],
)
def test_only_missing_e2e_evidence_may_proceed_to_measurement(tmp_path, monkeypatch, extra):
    rows = tuple(sample(str(i)) for i in range(16))
    (tmp_path / "corpus.json").write_text(
        TrainingCorpus(samples=rows).model_dump_json(), encoding="utf-8"
    )
    issues = [
        "MEASURED_E2E_PILOT_REQUIRED",
        "E2E_ARTIFACT_HASH_MISMATCH",
        "E2E_LATENCY_GUARD_FAILED",
        "E2E_CRITICAL_REGRESSION",
    ]
    monkeypatch.setattr(
        runner, "qualify", lambda *args: ({"issues": issues + ([extra] if extra else [])}, None)
    )
    if extra:
        with pytest.raises(ValueError, match="Offline qualification blocks"):
            runner.validate_frozen_pilot_input(tmp_path, SimpleNamespace(samples=rows))
    else:
        runner.validate_frozen_pilot_input(tmp_path, SimpleNamespace(samples=rows))
