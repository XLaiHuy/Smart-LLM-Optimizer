"""Balanced collection and rotated execution keep model observations aligned."""

import hashlib
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.config import ROOT
from app.contracts.dtos import CostSnapshot, Message, ModelConfiguration, RouteRate
from app.contracts.training import (
    CachedGeneration,
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingJob,
    TrainingManifest,
    TrainingRequest,
    TrainingSource,
)
from app.routing.ml import attention, pilot


def cases():
    return tuple(
        RawTrainingSample(
            task_id=f"{domain}-{split}-{i}",
            group_id=f"{domain}-{split}-{i}",
            domain=domain,
            split=split,
            messages=(Message(role="user", content=f"Offline {domain} {split} {i}"),),
            gold="1",
            grading=GradingSpec(kind="numeric"),
        )
        for domain in ("a", "z")
        for split in ("train", "calibration", "threshold", "holdout")
        for i in range(4)
    )


def test_each_split_alternates_domains_without_changing_membership():
    rows = cases()
    first = pilot.interleave(rows)
    assert first == pilot.interleave(tuple(reversed(rows)))
    assert {r.task_id for r in first} == {r.task_id for r in rows}
    for split in ("train", "calibration", "threshold", "holdout"):
        assert [r.domain for r in first if r.split == split] == ["a", "z"] * 4


@pytest.mark.asyncio
async def test_rotating_generation_order_never_rotates_model_labels(tmp_path, monkeypatch):
    corpus = TrainingCorpus(samples=cases())
    path = tmp_path / "corpus.json"
    path.write_text(corpus.model_dump_json(), encoding="utf-8")
    configs = tuple(
        ModelConfiguration(config_id=k, model_id=k, context_window=16000, max_output_tokens=128)
        for k in ("reference", "small", "medium")
    )
    manifest = TrainingManifest(
        version="functional",
        reviewed_by="offline test",
        pricing_source="test",
        software_test=True,
        source=TrainingSource(
            local_path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            license="functional",
            provenance="offline only",
        ),
        configurations=configs,
        reference_config_id="reference",
        costs=CostSnapshot(
            version="test",
            rates=tuple(
                RouteRate(config_id=c.config_id, input_per_million=".1", output_per_million=".2")
                for c in configs
            ),
        ),
        pilot=True,
        encoder_spec_path=str(ROOT / "config/encoder.minilm-int8.json"),
    )
    monkeypatch.setattr(pilot, "OnnxTokenEncoder", lambda spec: None)
    monkeypatch.setattr(attention, "torch_module", lambda hidden: None)
    orders = []

    async def save(job):
        return None

    async def generation(user, job, manifest, config_id, messages):
        orders.append(config_id)
        return CachedGeneration(
            text="0" if config_id == "small" else "1",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            usd=Decimal(".001"),
        ), job

    pipeline = SimpleNamespace(directory=lambda job_id: tmp_path, save=save, _generation=generation)
    job = TrainingJob(
        id="functional",
        request=TrainingRequest(client_request_id="functional", collection_batches=2),
        active_phase="collect",
    )
    result = await pilot.run_pilot(pipeline, None, job, manifest)
    assert result.completed == 32
    assert len({tuple(orders[i : i + 3]) for i in range(0, len(orders), 3)}) == 3
    rows = json.loads((tmp_path / "observations.json").read_text(encoding="utf-8"))
    for row in rows:
        assert {r["config_id"]: r["qualified"] for r in row["observations"]} == {
            "reference": True,
            "small": False,
            "medium": True,
        }


@pytest.mark.asyncio
async def test_full_phase_never_freezes_dev_at_a_batch_boundary(tmp_path, monkeypatch):
    corpus = TrainingCorpus(samples=cases())
    path = tmp_path / "corpus.json"
    path.write_text(corpus.model_dump_json(), encoding="utf-8")
    configs = tuple(
        ModelConfiguration(config_id=k, model_id=k, context_window=16000, max_output_tokens=128)
        for k in ("reference", "small", "medium")
    )
    manifest = TrainingManifest(
        version="functional",
        reviewed_by="offline test",
        pricing_source="test",
        software_test=True,
        source=TrainingSource(
            local_path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            license="functional",
            provenance="offline only",
        ),
        configurations=configs,
        reference_config_id="reference",
        costs=CostSnapshot(
            version="test",
            rates=tuple(
                RouteRate(config_id=c.config_id, input_per_million=".1", output_per_million=".2")
                for c in configs
            ),
        ),
        pilot=True,
        encoder_spec_path=str(ROOT / "config/encoder.minilm-int8.json"),
    )
    monkeypatch.setattr(pilot, "OnnxTokenEncoder", lambda spec: None)
    monkeypatch.setattr(attention, "torch_module", lambda hidden: None)

    def never_train(*args, **kwargs):
        raise AssertionError("Batch checkpoint must not train or inspect HOLDOUT")

    monkeypatch.setattr(pilot, "train_multi", never_train)

    async def save(job):
        return None

    async def generation(user, job, manifest, config_id, messages):
        return CachedGeneration(
            text="1", input_tokens=1, output_tokens=1, latency_ms=1, usd=Decimal(".001")
        ), job

    pipeline = SimpleNamespace(directory=lambda job_id: tmp_path, save=save, _generation=generation)
    job = TrainingJob(
        id="functional",
        request=TrainingRequest(client_request_id="functional", collection_batches=1),
        active_phase="full",
    )
    result = await pilot.run_pilot(pipeline, None, job, manifest)
    assert result.completed == 25 and result.total == 32
    assert result.pilot_report["collection_stopped_reason"] == "BATCH_COMPLETE"
    assert result.pilot_report["partial_collection"]
    assert not (tmp_path / "frozen.json").exists()
    assert not (tmp_path / "artifact.json").exists()
