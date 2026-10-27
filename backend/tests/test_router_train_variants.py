"""TRAIN augmentation must use measured outputs and preserve parent provenance."""

import hashlib
import importlib
import json
import sys
from types import SimpleNamespace

import pytest

from app.config import ROOT
from app.contracts.dtos import Message
from app.contracts.errors import AppError
from app.contracts.training import (
    CachedGeneration,
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingJob,
    TrainingRequest,
)

sys.path.insert(0, str(ROOT / "scripts"))
collector = importlib.import_module("collect_router_train_variants")


def corpus():
    rows = tuple(
        RawTrainingSample(
            task_id=f"{split}-{i}",
            group_id=f"{split}-{i}",
            domain="functional",
            split=split,
            messages=(Message(role="user", content=f"Offline {split}-{i}"),),
            gold="A",
            grading=GradingSpec(kind="mcq", choices=tuple("ABCD")),
        )
        for split in ("train", "calibration", "threshold")
        for i in range(8)
    )
    variant = rows[0].model_copy(
        update={
            "task_id": "train-0-rotated",
            "messages": (Message(role="user", content="Rotated original TRAIN question"),),
            "gold": "B",
            "grading": rows[0].grading.model_copy(
                update={
                    "synthetic": True,
                    "parent_group_id": rows[0].group_id,
                    "label_source": "synthetic_verified",
                }
            ),
        }
    )
    return TrainingCorpus(samples=rows + (variant,))


def test_only_train_variant_is_selected_and_no_new_independent_group_created():
    prepared = corpus()
    selected = collector.training_variants(prepared)
    assert len(selected) == 1
    assert selected[0].group_id == prepared.samples[0].group_id
    assert selected[0].split == "train"


def test_holdout_is_not_a_valid_variant_collection_source():
    prepared = corpus()
    holdout = prepared.samples[8].model_copy(update={"split": "holdout"})
    with pytest.raises(ValueError, match="DEV only"):
        collector.training_variants(
            prepared.model_copy(
                update={
                    "samples": prepared.samples
                    + (
                        holdout.model_copy(
                            update={
                                "task_id": "unseen-test",
                                "group_id": "unseen-test",
                                "messages": (Message(role="user", content="Unseen test"),),
                            }
                        ),
                    )
                }
            )
        )


def test_missing_real_parent_is_rejected():
    prepared = corpus()
    with pytest.raises(AppError, match="Synthetic variants"):
        collector.training_variants(prepared.model_copy(update={"samples": prepared.samples[1:]}))


@pytest.mark.asyncio
async def test_actual_provider_output_determines_labels_not_source_gold_alone(tmp_path):
    prepared = corpus()
    source = tmp_path / "source.json"
    source.write_text(prepared.model_dump_json(), encoding="utf-8")
    configs = tuple(SimpleNamespace(config_id=k) for k in ("reference", "small", "medium"))
    manifest = SimpleNamespace(
        source=SimpleNamespace(
            local_path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest()
        ),
        configurations=configs,
        model_dump_json=lambda **kwargs: '{"fixture":true}',
    )
    finished = []
    calls = []

    async def save(job):
        pass

    async def finish(job):
        finished.append(job)

    async def generation(user, job, manifest, config_id, messages):
        calls.append(config_id)
        return CachedGeneration(
            text="A" if config_id == "small" else "B",
            input_tokens=1,
            output_tokens=1,
            latency_ms=1,
            usd=".0001",
        ), job

    pipeline = SimpleNamespace(
        directory=lambda _: tmp_path, save=save, finish_job=finish, _generation=generation
    )
    job = TrainingJob(
        id="fixture",
        request=TrainingRequest(client_request_id="fixture", auto_import=False, phase="collect"),
        active_phase="collect",
    )
    await collector.TrainVariantPipeline._run(pipeline, None, job, manifest)
    assert finished[0].status == "succeeded"
    assert finished[0].total == finished[0].completed == 1
    assert len(calls) == 3
    row = json.loads((tmp_path / "observations.json").read_text(encoding="utf8"))[0]
    assert {o["config_id"]: o["qualified"] for o in row["observations"]} == {
        "reference": True,
        "small": False,
        "medium": True,
    }
    assert {o["label_source"] for o in row["observations"]} == {"synthetic_verified"}
    assert finished[0].pilot_report["import_eligible"] is False
