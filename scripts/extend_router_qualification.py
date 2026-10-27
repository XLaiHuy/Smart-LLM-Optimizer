"""Freeze a second campaign: retire old HOLDOUT to DEV and seal entirely fresh tests.

Preparation only; actual generations use the bounded persistent training pipeline.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from app.config import ROOT
from app.contracts.dtos import Message
from app.contracts.training import (
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingManifest,
    TrainingSource,
)
from app.routing.ml.independence import content_key
from app.routing.ml.pilot import validate_corpus
from prepare_router_qualification import mcq_gold, mcq_options


def prepare(directory: Path, previous: Path, pilot: Path):
    if directory.exists():
        raise ValueError("Use a new campaign directory")
    old_manifest = TrainingManifest.model_validate_json(
        (previous / "manifest.json").read_text(encoding="utf-8")
    )
    old_corpora = [
        TrainingCorpus.model_validate_json(
            (p / "corpus.json").read_text(encoding="utf-8")
        )
        for p in (previous, pilot)
    ]
    excluded = {r.group_id for corpus in old_corpora for r in corpus.samples}
    excluded_content = {
        content_key(r.messages) for corpus in old_corpora for r in corpus.samples
    }
    pools: dict[str, dict[str, RawTrainingSample]] = {
        "math_reasoning": {},
        "vietnamese_mcq": {},
    }
    for row in json.loads(
        (ROOT / "data/router-pilot-v1/gsm8k.json").read_text(encoding="utf-8")
    ):
        question = row["question"].strip()
        if len(question.encode()) > 2300:
            continue
        key = "gsm8k:" + hashlib.sha256(question.encode()).hexdigest()
        messages = (
            Message(
                role="user", content=question + "\nGive only the final numeric answer."
            ),
        )
        if key in excluded or content_key(messages) in excluded_content:
            continue
        pools["math_reasoning"][key] = RawTrainingSample(
            task_id=key,
            group_id=key,
            domain="math_reasoning",
            split="train",
            messages=messages,
            gold=row["answer"].rsplit("####", 1)[-1].strip(),
            grading=GradingSpec(kind="numeric"),
        )
    for row in json.loads(
        (ROOT / "data/router-pilot-v1/aya.json").read_text(encoding="utf-8")
    ):
        question = row["inputs"].strip()
        gold = mcq_gold(question, row["targets"])
        if not gold or len(question.encode()) > 2300:
            continue
        key = "aya-mcq:" + content_key((Message(role="user", content=question),))
        messages = (
            Message(
                role="user",
                content=question + "\nChỉ trả lời một chữ cái trong các lựa chọn.",
            ),
        )
        if key in excluded or content_key(messages) in excluded_content:
            continue
        pools["vietnamese_mcq"][key] = RawTrainingSample(
            task_id=key,
            group_id=key,
            domain="vietnamese_mcq",
            split="train",
            messages=messages,
            gold=gold,
            grading=GradingSpec(kind="mcq", choices=mcq_options(question)),
        )
    selected: list[RawTrainingSample] = []
    for domain, pool in pools.items():
        ordered = sorted(
            pool.values(),
            key=lambda r: hashlib.sha256(("round2:" + r.group_id).encode()).hexdigest(),
        )
        if len(ordered) < 150:
            raise ValueError(
                f"Insufficient unseen originals in {domain}: {len(ordered)}"
            )
        splits = (
            ["train"] * 30
            + ["calibration"] * 10
            + ["threshold"] * 10
            + ["holdout"] * 100
        )
        selected.extend(
            r.model_copy(update={"split": s})
            for r, s in zip(ordered[:150], splits, strict=True)
        )
    corpus = TrainingCorpus(samples=tuple(selected))
    validate_corpus(corpus)
    directory.mkdir(parents=True)
    path = directory / "corpus.json"
    path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    source = TrainingSource(
        local_path=str(path.resolve()),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adapter="canonical",
        license=old_manifest.source.license,
        provenance=old_manifest.source.provenance
        + "; round2 fresh groups exclude every prior pilot/DEV/HOLDOUT identity",
        license_url=old_manifest.source.license_url,
        license_reviewed=True,
        allow_training=True,
    )
    manifest = old_manifest.model_copy(
        update={
            "version": "router-qualification-round2-v5-20261027",
            "source": source,
            "max_samples": 300,
        }
    )
    (directory / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    report = {
        "fresh_groups": 300,
        "fresh_splits": dict(Counter(r.split for r in selected)),
        "candidate_configs": [c.config_id for c in manifest.configurations],
        "budget_usd": "1",
        "prior_holdout_retired_to_dev": True,
        "new_holdout_groups_per_domain": 100,
        "previous": str(previous),
        "pilot": str(pilot),
        "unchanged_acceptance": "one-sided regression upper95 <=3%/domain, E2E p50 ratio<=1.10, reviewed provenance and measurable routing benefit",
    }
    (directory / "plan.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--pilot", required=True, type=Path)
    args = parser.parse_args()
    prepare(args.directory, args.previous, args.pilot)
