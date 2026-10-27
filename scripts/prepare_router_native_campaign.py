"""Freeze a separate, metered native-provider experiment after Groq quota exhaustion.

Reuse public inputs only, never transfer Groq response labels to another provider.
The new test excludes every source family used in earlier campaigns.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from app.config import ROOT
from app.contracts.dtos import CostSnapshot, Message, ModelConfiguration, RouteRate
from app.contracts.training import (
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingManifest,
)
from app.providers.catalog import Catalog
from app.routing.ml.pilot import validate_corpus


def prepare(
    output: Path, catalog_path: Path = ROOT / "config/models.native-v2.json"
) -> dict:
    if output.exists():
        raise ValueError("Frozen experiment already exists")
    prior = ROOT / "data/router-live-qualification-20261027"
    round2 = prior / "round2-v5"
    pool = json.loads((round2 / "family-pool-v2.json").read_text(encoding="utf-8"))
    families = pool["families"]
    old_paths = [
        *prior.glob("final-gold-v5/runs/*/corpus.json"),
        *prior.glob("runs/*/corpus.json"),
        round2 / "family-deduplicated/corpus.json",
        *round2.glob("runs/*/corpus.json"),
    ]
    used_math, used_vi = set(), set()
    for path in old_paths:
        for row in TrainingCorpus.model_validate_json(
            path.read_text(encoding="utf-8")
        ).samples:
            group = row.group_id.removeprefix("source-0:")
            if row.domain == "math_reasoning":
                used_math.add(group)
            else:
                original = row.task_id.removeprefix("source-0:")
                used_vi.add(families.get(original, group))
    math = {}
    for raw in json.loads(
        (ROOT / "data/router-pilot-v1/gsm8k.json").read_text(encoding="utf-8")
    ):
        text = raw["question"].strip()
        if len(text.encode()) > 2300:
            continue
        key = "gsm8k:" + hashlib.sha256(text.encode()).hexdigest()
        math[key] = RawTrainingSample(
            task_id=key,
            group_id=key,
            domain="math_reasoning",
            split="train",
            messages=(
                Message(
                    role="user", content=text + "\nGive only the final numeric answer."
                ),
            ),
            gold=raw["answer"].rsplit("####", 1)[-1].strip(),
            grading=GradingSpec(kind="numeric"),
        )
    vi: dict[str, RawTrainingSample] = {}
    for key, raw in sorted(pool["rows"].items()):
        group = families[key]
        vi.setdefault(
            group,
            RawTrainingSample(
                task_id=key,
                group_id=group,
                domain="vietnamese_mcq",
                split="train",
                messages=(
                    Message(
                        role="user",
                        content=raw["prompt"]
                        + "\nChỉ trả lời một chữ cái trong các lựa chọn.",
                    ),
                ),
                gold=raw["gold"],
                grading=GradingSpec(kind="mcq", choices=tuple(raw["choices"])),
            ),
        )
    rows = []
    for candidates, used in ((math, used_math), (vi, used_vi)):
        order = lambda key: hashlib.sha256(("native-v1:" + key).encode()).hexdigest()
        dev = sorted(set(candidates) & used, key=order)[:100]
        test = sorted(set(candidates) - used, key=order)[:100]
        if len(dev) != 100 or len(test) != 100:
            raise ValueError(
                "Need 100 old DEV and 100 entirely fresh test families per domain"
            )
        for index, key in enumerate(dev):
            split = (
                "train" if index < 60 else "calibration" if index < 80 else "threshold"
            )
            rows.append(candidates[key].model_copy(update={"split": split}))
        rows.extend(
            candidates[key].model_copy(update={"split": "holdout"}) for key in test
        )
    corpus = TrainingCorpus(samples=tuple(rows))
    validate_corpus(corpus)
    catalog = Catalog.load(catalog_path)
    ids = tuple(m.config_id for m in catalog.models if m.kind == "generation")
    entries = [catalog.entry(key) for key in ids]
    assert all(entries)
    if len(ids) != 3 or ids[0] != catalog.baseline_config:
        raise ValueError(
            "Exactly three native profiles with the reference first required"
        )
    if any(
        m.api_key_env != "OPENAI_API_KEY" or m.base_url != "https://api.openai.com/v1"
        for m in entries
    ):
        raise ValueError("Native campaign requires explicit OpenAI profiles")
    version = "smartllm-" + output.name + "-qualification-20261027"
    # Keep the generation profile and published prices; change only registry membership.
    native = catalog.model_copy(
        update={
            "version": version,
            "baseline_config": ids[0],
            "models": tuple(
                m for m in catalog.models if m.config_id in ids or m.kind == "embedding"
            ),
        }
    )
    configs = tuple(
        ModelConfiguration.model_validate(
            {
                **m.model_dump(include=set(ModelConfiguration.model_fields)),
                "execution_source": "live",
                "available": True,
                "availability_reason": "reviewed",
            }
        )
        for m in entries
    )
    template = TrainingManifest.model_validate_json(
        (round2 / "family-deduplicated/manifest.json").read_text(encoding="utf-8")
    )
    output.mkdir(parents=True)
    path = output / "corpus.json"
    path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    source = template.source.model_copy(
        update={
            "local_path": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "provenance": template.source.provenance
            + f"; {output.name}: new measurements, no Groq label transfer; unseen family HOLDOUT",
        }
    )
    manifest = template.model_copy(
        update={
            "version": version,
            "pricing_source": version,
            "source": source,
            "sources": (),
            "configurations": configs,
            "reference_config_id": ids[0],
            "max_samples": 400,
            "attention_epochs": 5,
            "costs": CostSnapshot(
                version=version,
                rates=tuple(
                    RouteRate(
                        config_id=m.config_id,
                        input_per_million=m.input_per_million,
                        output_per_million=m.output_per_million,
                    )
                    for m in entries
                ),
            ),
        }
    )
    # Validation is intentional: model_copy alone does not validate nested DTO changes.
    TrainingManifest.model_validate_json(manifest.model_dump_json())
    (output / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    (output / "catalog.json").write_text(
        native.model_dump_json(indent=2), encoding="utf-8"
    )
    plan = {
        "budget_usd": "1.00",
        "provider_calls": 1200,
        "splits": dict(Counter(r.split for r in rows)),
        "test_families": [r.group_id for r in rows if r.split == "holdout"],
        "training": "existing paired ML and Attention implementation; 5 epochs fixed before new test",
        "activation": "formal qualification and measured serving pilot required; coverage only math and adapted Vietnamese MCQ",
        "responses_reused_from_other_providers": False,
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "config/models.native-v2.json"
    )
    args = parser.parse_args()
    plan = prepare(args.output, args.catalog)
    print(json.dumps({k: v for k, v in plan.items() if k != "test_families"}))
