"""A good replay cannot import an incomplete or financially unresolved pilot."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from app.config import ROOT
from app.contracts.dtos import CostSnapshot, Message, ModelConfiguration, RouteRate
from app.contracts.training import (
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingJob,
    TrainingManifest,
    TrainingRequest,
    TrainingSource,
)
from app.routing.ml import attention, pilot
from app.routing.ml.multi_training import MultiSample, Observation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "partial,unresolved,eligible", [(True, 0, False), (False, 1, False), (False, 0, True)]
)
async def test_observed_replay_requires_complete_settled_collection(
    tmp_path, monkeypatch, partial, unresolved, eligible
):
    configs = tuple(
        ModelConfiguration(config_id=k, model_id=k, context_window=16000, max_output_tokens=128)
        for k in ("reference", "small", "medium")
    )
    raw = tuple(
        RawTrainingSample(
            task_id=f"{split}-{i}",
            group_id=f"{split}-{i}",
            domain="functional",
            split=split,
            messages=(Message(role="user", content=f"Offline case {split} {i}"),),
            gold="1",
            grading=GradingSpec(kind="numeric"),
        )
        for split in ("train", "calibration", "threshold", "holdout")
        for i in range(5 if partial else 4)
    )
    corpus = TrainingCorpus(samples=raw)
    source_path = tmp_path / "corpus.json"
    source_path.write_text(corpus.model_dump_json(), encoding="utf-8")
    source = TrainingSource(
        local_path=str(source_path),
        sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        license="test-only",
        provenance="offline functional fixture",
    )
    manifest = TrainingManifest(
        version="functional",
        reviewed_by="test-only",
        pricing_source="test-only",
        software_test=True,
        source=source,
        configurations=configs,
        reference_config_id="reference",
        costs=CostSnapshot(
            version="test-only",
            rates=tuple(
                RouteRate(config_id=c.config_id, input_per_million=".1", output_per_million=".2")
                for c in configs
            ),
        ),
        pilot=True,
        encoder_spec_path=str(ROOT / "config/encoder.minilm-int8.json"),
    )
    rows = [
        MultiSample(
            task_id=r.task_id,
            group_id=r.group_id,
            split=r.split,
            domain=r.domain,
            messages=r.messages,
            observations=tuple(
                Observation(
                    config_id=c.config_id,
                    qualified=True,
                    usd=".001",
                    latency_ms=10,
                    input_tokens=1,
                    output_tokens=1,
                    label_source="dataset_gold",
                    grader_version="functional",
                    response_sha256="f" * 64,
                )
                for c in configs
            ),
        )
        for r in raw
        if not r.task_id.endswith("-4")
    ]
    (tmp_path / "observations.json").write_text(
        json.dumps([r.model_dump(mode="json") for r in rows]), encoding="utf-8"
    )
    monkeypatch.setattr(pilot, "OnnxTokenEncoder", lambda spec: None)
    monkeypatch.setattr(attention, "torch_module", lambda hidden: None)
    artifact = SimpleNamespace(model_dump_json=lambda **kwargs: '{"functional":true}')
    monkeypatch.setattr(pilot, "train_multi", lambda *args, **kwargs: artifact)
    monkeypatch.setattr(
        pilot,
        "MultiRouterService",
        lambda raw: SimpleNamespace(status="ML_ARTIFACT_READY", hash="functional"),
    )
    score = {
        "report": {"observed_pass_rate": 1, "serving_usd": 0.1},
        "all_in_p50_ratio": 1,
        "guardrails_with_routing_overhead": True,
    }
    monkeypatch.setattr(pilot, "timed_evaluate", lambda *args: score)
    monkeypatch.setattr(pilot, "paired_comparison", lambda *args: {})
    imports = []

    async def save(job):
        return None

    pipeline = SimpleNamespace(directory=lambda job_id: tmp_path, save=save, _import=imports.append)
    job = TrainingJob(
        id="functional",
        request=TrainingRequest(client_request_id="functional", auto_import=True),
        active_phase="train",
        unknown_cost_calls=unresolved,
    )
    result = await pilot.run_pilot(pipeline, None, job, manifest)
    assert result.pilot_report["import_eligible"] is eligible
    assert bool(imports) is eligible
    assert result.pilot_report["conclusion"] == (
        "PASS_OBSERVED" if eligible else "INSUFFICIENT_EVIDENCE"
    )
