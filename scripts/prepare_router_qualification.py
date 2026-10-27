"""Freeze public gold, split identities and acceptance rules before live collection.

No API calls and no simulated model outcomes. The adapted Aya MCQ slice is not an
official Aya benchmark score. Code, open writing and multi-turn memory remain gaps.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from app.config import ROOT
from app.contracts.dtos import CostSnapshot, Message, ModelConfiguration, RouteRate
from app.contracts.training import (
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingManifest,
    TrainingSource,
)
from app.providers.catalog import Catalog
from app.routing.ml.independence import content_key
from app.routing.ml.pilot import validate_corpus


def mcq_options(prompt: str) -> tuple[str, ...]:
    choices = tuple(
        c.upper()
        for c in re.findall(r"(?:^|\n)[ \t]*([A-E])[.)][ \t]+", prompt, re.IGNORECASE)
    )
    return (
        choices
        if 3 <= len(choices) <= 5 and choices == tuple("ABCDE"[: len(choices)])
        else ()
    )


def mcq_gold(prompt: str, target: str) -> str | None:
    choices = mcq_options(prompt)
    if not choices:
        return None
    # Require one explicit original answer on its first nonempty line. Do not
    # infer truth from prompt keywords or ask a teacher to invent a label.
    first = target.strip().splitlines()[0] if target.strip() else ""
    match = re.match(
        r"^(?:(?:Đáp án|Câu trả lời|Lựa chọn)(?:[ \t]+đúng)?(?:[ \t]+là)?[ \t]*:?[ \t]*)?([A-E])(?:[.) \t:]|$)",
        first,
        re.IGNORECASE,
    )
    if (
        not match
        or match[1].upper() not in choices
        or len(
            {
                c.upper()
                for c in re.findall(
                    r"(?:^|\n)[ \t]*([A-E])[.)][ \t]+", target, re.IGNORECASE
                )
            }
        )
        > 1
        or len(re.findall(r"(?:^|[ ,;])([A-E])[.)]", first, re.IGNORECASE)) > 1
    ):
        return None
    return match[1].upper()


def freeze_groups(
    rows: list[RawTrainingSample], excluded: set[str]
) -> list[RawTrainingSample]:
    unique = {r.group_id: r for r in rows if r.group_id not in excluded}
    ordered = sorted(
        unique.values(), key=lambda r: hashlib.sha256(r.group_id.encode()).hexdigest()
    )
    if len(ordered) < 200:
        raise ValueError(f"Need 200 original groups per domain; found {len(ordered)}")
    splits = (
        ["train"] * 60 + ["calibration"] * 20 + ["threshold"] * 20 + ["holdout"] * 100
    )
    return [
        r.model_copy(update={"split": split})
        for r, split in zip(ordered[:200], splits, strict=True)
    ]


def prepare(directory: Path, pilot_corpus: Path) -> dict:
    if directory.exists():
        raise ValueError("Use a new directory; frozen plans are never overwritten")
    excluded = {
        r.group_id
        for r in TrainingCorpus.model_validate_json(
            pilot_corpus.read_text(encoding="utf-8")
        ).samples
    }
    paths = {
        "gsm8k": ROOT / "data/router-pilot-v1/gsm8k.json",
        "aya": ROOT / "data/router-pilot-v1/aya.json",
    }
    pools: dict[str, list[RawTrainingSample]] = {k: [] for k in paths}
    for row in json.loads(paths["gsm8k"].read_text(encoding="utf-8")):
        question = row["question"].strip()
        if len(question.encode()) > 2300:
            continue
        key = "gsm8k:" + hashlib.sha256(question.encode()).hexdigest()
        pools["gsm8k"].append(
            RawTrainingSample(
                task_id=key,
                group_id=key,
                domain="math_reasoning",
                split="train",
                messages=(
                    Message(
                        role="user",
                        content=question + "\nGive only the final numeric answer.",
                    ),
                ),
                gold=row["answer"].rsplit("####", 1)[-1].strip(),
                grading=GradingSpec(kind="numeric"),
            )
        )
    for row in json.loads(paths["aya"].read_text(encoding="utf-8")):
        question = row["inputs"].strip()
        gold = mcq_gold(question, row["targets"])
        if not gold or len(question.encode()) > 2300:
            continue
        # Keep original public input and labels; only make the output interface explicit.
        messages = (
            Message(
                role="user",
                content=question + "\nChỉ trả lời một chữ cái trong các lựa chọn.",
            ),
        )
        key = "aya-mcq:" + content_key((Message(role="user", content=question),))
        pools["aya"].append(
            RawTrainingSample(
                task_id=key,
                group_id=key,
                domain="vietnamese_mcq",
                split="train",
                messages=messages,
                gold=gold,
                grading=GradingSpec(kind="mcq", choices=mcq_options(question)),
            )
        )
    selected = [r for pool in pools.values() for r in freeze_groups(pool, excluded)]
    corpus = TrainingCorpus(samples=tuple(selected))
    validate_corpus(corpus)
    catalog = Catalog.load(ROOT / "config/models.json")
    ids = [
        catalog.baseline_config,
        "groq-openai-gpt-oss-20b-o2048-rlow",
        "openai-gpt-6-luna-o2048",
    ]
    entries = [catalog.entry(key) for key in ids]
    configs = tuple(
        ModelConfiguration(
            config_id=e.config_id,
            model_id=e.model_id,
            execution_source="live",
            context_window=e.context_window,
            available=True,
            availability_reason="reviewed",
            endpoint=e.endpoint,
            max_output_tokens=e.max_output_tokens,
            structured_output=e.structured_output,
            function_calling=e.function_calling,
            reasoning_effort=e.reasoning_effort,
            supported_parameters=e.supported_parameters,
        )
        for e in entries
    )
    costs = CostSnapshot(
        version=catalog.version,
        rates=tuple(
            RouteRate(
                config_id=e.config_id,
                input_per_million=e.input_per_million,
                output_per_million=e.output_per_million,
            )
            for e in entries
        ),
    )
    directory.mkdir(parents=True)
    corpus_path = directory / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")
    provenance = {
        "GSM8K": {
            "revision": "740312add88f781978c0658806c59bc2815b9866",
            "license": "MIT",
            "license_url": "https://github.com/openai/grade-school-math/blob/master/LICENSE",
        },
        "CohereLabs/aya_dataset": {
            "revision": "f9ea04583f02a8f86404ff6c58bf75fe637df8a2",
            "license": "Apache-2.0",
            "license_url": "https://huggingface.co/datasets/CohereLabs/aya_dataset",
        },
        "prepared_source_sha256": {
            key: hashlib.sha256(path.read_bytes()).hexdigest()
            for key, path in paths.items()
        },
        "protocol": "original numeric gold and adapted MCQ first-line answer, no teacher judge; frozen stratified groups",
        "excluded_prior_pilot_groups": sorted(excluded),
        "limitations": [
            "English math and Vietnamese MCQ only",
            "Not an official Aya benchmark",
            "Paraphrase-family independence beyond exact normalized inputs is unverified",
            "No code execution, open writing, multi-turn memory or RAG certification",
        ],
    }
    source = TrainingSource(
        local_path=str(corpus_path.resolve()),
        sha256=hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        adapter="canonical",
        license="MIT (GSM8K); Apache-2.0 (Aya)",
        provenance=json.dumps(provenance),
        license_url="https://huggingface.co/datasets/CohereLabs/aya_dataset",
        license_reviewed=True,
        allow_training=True,
    )
    manifest = TrainingManifest(
        version="router-qualification-gold-v5-20261027",
        reviewed_by="Codex automated protocol review authorized by Huy; no human review asserted",
        pricing_source=catalog.version,
        access_verified=True,
        source=source,
        configurations=configs,
        reference_config_id=catalog.baseline_config,
        costs=costs,
        max_samples=400,
        min_interval_seconds=1.2,
        encoder_spec_path="config/encoder.minilm-int8.json",
        attention_epochs=15,
        pilot=True,
        split_protocol="frozen_canonical",
    )
    (directory / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    plan = {
        "groups": 400,
        "splits": dict(Counter(r.split for r in selected)),
        "domains": dict(Counter(r.domain for r in selected)),
        "provider_calls": 1200,
        "budget_cap_usd": "1.00",
        "acceptance": {
            "quality": "exact one-sided 95% regression upper bound <= .03 per domain",
            "holdout_per_domain": 100,
            "p50_e2e_ratio_max": 1.10,
            "critical_regressions": 0,
            "requires_measured_serving_pilot": True,
            "coverage_gaps_prevent_unrestricted_activation": True,
        },
        "provenance": provenance,
    }
    (directory / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--pilot-corpus", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.directory, args.pilot_corpus), ensure_ascii=True))
