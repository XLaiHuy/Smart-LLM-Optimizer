"""Collection completeness and fresh-test secrecy at the offline fitting boundary."""

import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
training = importlib.import_module("train_router_targeted")
evaluation = importlib.import_module("evaluate_router_targeted")


def setup(monkeypatch, incoming, expected):
    old_row = SimpleNamespace(
        group_id="old-train",
        split="train",
        messages=(SimpleNamespace(content="Complete old input"),),
    )
    manifest = SimpleNamespace(
        configurations=("same-profiles",), costs="same-price", max_samples=expected
    )
    old = SimpleNamespace(samples=(old_row,))
    monkeypatch.setattr(
        training,
        "load",
        lambda path: (
            incoming
            if path.name == "observations.json"
            else manifest
            if path.name == "manifest.json"
            else old
        ),
    )
    monkeypatch.setattr(training, "MultiDataset", SimpleNamespace(model_validate=lambda x: x))
    monkeypatch.setattr(training, "TrainingManifest", SimpleNamespace(model_validate=lambda x: x))

    def parse(row):
        assert row["split"] != "holdout", "HOLDOUT outcome must not be deserialized for fitting"
        return SimpleNamespace(
            group_id=row["group_id"],
            split=row["split"],
            messages=(SimpleNamespace(content="Complete fresh input"),),
        )

    monkeypatch.setattr(training, "MultiSample", SimpleNamespace(model_validate=parse))
    monkeypatch.setattr(training, "dataset", lambda manifest, rows: rows)
    return manifest


def test_holdout_rows_are_filtered_before_model_deserialization(monkeypatch):
    rows = [
        {"split": "holdout", "not_a_valid_training_sample": "must never deserialize"},
        {"split": "train", "group_id": "fresh-train"},
    ]
    manifest = setup(monkeypatch, rows, 2)
    fitted, _ = training.combined_dev(Path("old"), Path("current"), manifest)
    assert [r.group_id for r in fitted] == ["old-train", "fresh-train"]


def test_partial_collection_is_not_fit_even_if_some_dev_rows_exist(monkeypatch):
    manifest = setup(monkeypatch, [{"split": "train", "group_id": "fresh-train"}], 2)
    with pytest.raises(ValueError, match="entire frozen campaign"):
        training.combined_dev(Path("old"), Path("current"), manifest)


def test_artifact_hash_is_checked_before_test_data_is_opened(tmp_path):
    trained = tmp_path / "trained"
    trained.mkdir()
    (trained / "frozen.json").write_text(
        '{"baseline":"wrong-hash","attention":"not-read"}', encoding="utf8"
    )
    (trained / "baseline.json").write_text('{"tampered":true}', encoding="utf8")
    with pytest.raises(ValueError, match="Frozen artifact changed"):
        evaluation.sealed_test(
            tmp_path / "nonexistent-secret-test", tmp_path / "nonexistent-outcomes", trained
        )


def test_windows_crlf_artifact_uses_frozen_text_hash_protocol(tmp_path, monkeypatch):
    trained = tmp_path / "trained"
    trained.mkdir()
    content = '{\n  "same": true\n}'
    hashes = {}
    for name in ("baseline", "attention"):
        (trained / (name + ".json")).write_bytes(content.replace("\n", "\r\n").encode())
        hashes[name] = hashlib.sha256(content.encode()).hexdigest()
    (trained / "frozen.json").write_text(json.dumps(hashes), encoding="utf-8")
    # Reaching this missing sealed source proves both immutable hashes passed.
    with pytest.raises(FileNotFoundError, match="sealed-fresh-holdout"):
        evaluation.sealed_test(tmp_path / "missing-test", tmp_path / "missing-outcomes", trained)
