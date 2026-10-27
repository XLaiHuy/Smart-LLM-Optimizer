"""Freeze source-group splits for measured three-model calibration; no API calls.

Sources: MIT GSM8K, CC-BY-SA-4.0 SQuAD, CC-BY-SA-3.0 human MLQA Vietnamese QA.
Targets remain evaluator-only. A source group contributes at most one question.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from app.config import ROOT
from app.contracts.dtos import CostSnapshot, Message, RouteRate
from app.contracts.training import (
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingManifest,
    TrainingSource,
)
from app.providers.catalog import Catalog
from app.routing.ml.graders import validate_gold
from app.routing.ml.independence import content_key
from router_family_protocol import family_map

VERSION = "task-family-v1-20261027"
SPLITS = (("train", 100), ("calibration", 50), ("threshold", 50), ("holdout", 100))


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def aya_mcq(prompt: str, target: str):
    # Original option spellings/punctuation vary. Only one complete, ordered
    # A..C/D/E block and one explicit source answer are accepted.
    markers = list(
        re.finditer(r"(?:^|\n|(?<=\s))([A-Ea-e])(?:[.)/:]|\s*[–—-])\s+", prompt)
    )
    letters = [m[1].upper() for m in markers]
    if not 3 <= len(markers) <= 5 or letters != list("ABCDE"[: len(markers)]):
        return None
    answers = re.findall(
        r"(?:đáp\s*án|câu\s*trả\s*lời|lựa\s*chọn)(?:\s+đúng)?(?:\s+là)?\s*[:–—-]?\s*([A-E])\b",
        target,
        re.IGNORECASE,
    )
    first = target.strip().splitlines()[0] if target.strip() else ""
    first_match = re.match(r"^([A-E])(?:[.)/:]|\s*[–—-]|$)", first, re.IGNORECASE)
    if first_match:
        answers.append(first_match[1])
    answers = {a.upper() for a in answers}
    if len(answers) != 1 or not answers <= set(letters):
        return None
    stem = prompt[: markers[0].start()].strip()
    options = [
        prompt[
            m.end() : markers[i + 1].start() if i + 1 < len(markers) else len(prompt)
        ].strip()
        for i, m in enumerate(markers)
    ]
    if not stem or any(not option for option in options):
        return None
    text = (
        stem
        + "\n\n"
        + "\n".join(
            f"{letter}. {option}"
            for letter, option in zip(letters, options, strict=True)
        )
    )
    return text, next(iter(answers)), tuple(letters)


def prior_inputs(exclude: Path):
    keys, texts = set(), {}
    for path in (ROOT / "data").rglob("corpus.json"):
        if path.is_relative_to(exclude):
            continue
        try:
            samples = json.loads(path.read_text(encoding="utf-8")).get("samples", [])
        except (OSError, ValueError):
            continue
        for row in samples:
            for field in ("task_id", "group_id"):
                keys.add(re.sub(r"^(source-\d+:)+", "", row.get(field, "")))
            for message in row.get("messages", []):
                text = message.get("content", "")
                if message.get("role") == "user" and text:
                    texts["prior:" + sha(text)] = text
    return keys, texts


def pools(source_dir: Path):
    result = {
        k: {} for k in ("exact_arithmetic", "structured_extraction", "vietnamese_qa")
    }
    for row in json.loads(
        (ROOT / "data/router-pilot-v1/gsm8k.json").read_text(encoding="utf-8")
    ):
        text = row["question"].strip()
        if len(text.encode()) > 1800:
            continue
        key = "gsm8k:" + sha(text)
        gold = row["answer"].rsplit("####", 1)[-1].strip()
        spec = GradingSpec(kind="numeric")
        try:
            validate_gold(spec, gold)
        except ValueError:
            continue
        result["exact_arithmetic"][key] = RawTrainingSample(
            task_id=key,
            group_id=key,
            domain="exact_arithmetic",
            split="train",
            messages=(
                Message(
                    role="user", content=text + "\nGive only the final numeric answer."
                ),
            ),
            gold=gold,
            grading=spec,
        )
    squad = pq.read_table(source_dir / "squad-train.parquet").to_pylist()
    # SQuAD article titles, not question count, define independent source groups.
    for row in sorted(squad, key=lambda r: sha(r["id"])):
        key = "squad:" + row["id"]
        group = "wiki-article:" + sha(row["title"].casefold())
        context = row["context"]
        answers = list(row["answers"]["text"])
        starts = list(row["answers"]["answer_start"])
        if (
            len(context.encode()) > 4500
            or not answers
            or not all(
                context[s : s + len(a)] == a
                for a, s in zip(answers, starts, strict=True)
            )
        ):
            continue
        text = (
            'Extract the answer from the supplied passage. Return only JSON {"answer": "exact answer span"}.\nPASSAGE:\n'
            + context
            + "\nQUESTION:\n"
            + row["question"]
        )
        result["structured_extraction"].setdefault(
            group,
            RawTrainingSample(
                task_id=key,
                group_id=group,
                domain="structured_extraction",
                split="train",
                messages=(Message(role="user", content=text),),
                gold=json.dumps({"is_impossible": False, "answers": answers}),
                grading=GradingSpec(kind="extractive_qa"),
            ),
        )
    for path in sorted(source_dir.glob("*-context-vi-question-vi.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for article in document["data"]:
            group = "wiki-article:" + sha(article["title"].casefold())
            for paragraph in article["paragraphs"]:
                context = paragraph["context"]
                if len(context.encode()) > 4500:
                    continue
                for question in sorted(paragraph["qas"], key=lambda q: sha(q["id"])):
                    answers = question["answers"]
                    if not answers or not all(
                        context[a["answer_start"] : a["answer_start"] + len(a["text"])]
                        == a["text"]
                        for a in answers
                    ):
                        continue
                    text = (
                        'Trả lời câu hỏi dựa trên ngữ cảnh đã cho. Chỉ trả về JSON {"answer":"đoạn trả lời chính xác trong ngữ cảnh"}.\nNGỮ CẢNH:\n'
                        + context
                        + "\nCÂU HỎI:\n"
                        + question["question"]
                    )
                    result["vietnamese_qa"].setdefault(
                        group,
                        RawTrainingSample(
                            task_id="mlqa-vi:" + question["id"],
                            group_id=group,
                            domain="vietnamese_qa",
                            split="train",
                            messages=(Message(role="user", content=text),),
                            gold=json.dumps(
                                {
                                    "is_impossible": False,
                                    "answers": [a["text"] for a in answers],
                                },
                                ensure_ascii=False,
                            ),
                            grading=GradingSpec(kind="extractive_qa"),
                        ),
                    )
    return result


def prepare(args):
    output = args.directory.resolve()
    if (output / "protocol.json").exists():
        raise ValueError("Frozen protocol already exists; never overwrite or resample")
    output.mkdir(parents=True, exist_ok=True)
    used, old_texts = prior_inputs(output)
    source_dir = output / "sources"
    available = pools(source_dir)
    selected, audit = [], {}
    used_articles = set()
    old_pool_path = (
        ROOT / "data/router-live-qualification-20261027/round2-v5/family-pool-v2.json"
    )
    old_pool = json.loads(old_pool_path.read_text(encoding="utf-8"))
    used_aya_families = {old_pool["families"].get(key, key) for key in used}
    for family, raw in available.items():
        candidates = {
            key: row
            for key, row in raw.items()
            if key not in used
            and row.task_id not in used
            and row.group_id not in used
            and row.group_id not in used_articles
            and old_pool["families"].get(key, key) not in used_aya_families
        }
        texts = {
            **old_texts,
            **{key: row.messages[-1].content for key, row in candidates.items()},
        }
        mapped = family_map(texts)
        prior_families = {mapped[key] for key in old_texts}
        representatives = {}
        for key, row in sorted(candidates.items()):
            if mapped[key] in prior_families:
                continue
            representatives.setdefault(mapped[key], row)
        ranked = sorted(
            representatives.items(),
            key=lambda pair: sha(VERSION + ":" + family + ":" + pair[0]),
        )
        audit[family] = {
            "raw": len(raw),
            "fresh_independent": len(ranked),
            "required": 300,
        }
        if len(ranked) < 300:
            continue
        cursor = 0
        for split, count in SPLITS:
            for group, row in ranked[cursor : cursor + count]:
                selected.append(
                    row.model_copy(
                        update={"group_id": family + ":" + group, "split": split}
                    )
                )
                used_articles.add(row.group_id)
            cursor += count
    write(output / "source-audit.json", audit)
    if len(selected) != 900:
        print(json.dumps({"status": "SOURCE_COVERAGE_INSUFFICIENT", "counts": audit}))
        return
    if len({content_key(row.messages) for row in selected}) != 900:
        raise ValueError("Duplicate serving inputs")
    corpus = TrainingCorpus(samples=tuple(selected))
    corpus_raw = corpus.model_dump_json(indent=2)
    (output / "corpus.json").write_bytes(corpus_raw.encode("utf-8"))
    catalog = Catalog.load(args.catalog)
    artifact = json.loads(
        (ROOT / "config/router_attention_operator_accepted.json").read_text(
            encoding="utf-8"
        )
    )
    from app.contracts.dtos import ModelConfiguration

    configs = tuple(
        ModelConfiguration.model_validate(c) for c in artifact["configurations"]
    )
    rates = tuple(
        RouteRate(
            config_id=c.config_id,
            input_per_million=catalog.entry(c.config_id).input_per_million,
            output_per_million=catalog.entry(c.config_id).output_per_million,
        )
        for c in configs
    )
    manifest = TrainingManifest(
        version=VERSION,
        reviewed_by="Huy authorized 2026-10-27; source gold adapters reviewed in code/tests",
        pricing_source="frozen serving catalog",
        access_verified=True,
        source=TrainingSource(
            local_path=(Path("/app/data") / output.relative_to(ROOT / "data") / "corpus.json").as_posix(),
            sha256=hashlib.sha256(corpus_raw.encode()).hexdigest(),
            adapter="canonical",
            license="MIT + CC-BY-SA-3.0 + CC-BY-SA-4.0 (source attribution retained)",
            provenance="GSM8K numeric, MLQA Vietnamese article-group QA, SQuAD article-group extraction; source-only split, no provider outcomes used",
            license_url="https://huggingface.co/datasets/rajpurkar/squad",
            license_reviewed=True,
            allow_training=True,
        ),
        configurations=configs,
        reference_config_id=artifact["reference_config_id"],
        costs=CostSnapshot(version=catalog.version, rates=rates),
        max_samples=900,
        min_interval_seconds=1.4,
        encoder_spec_path="config/encoder.minilm-int8.json",
        attention_epochs=5,
        pilot=True,
        synthesize=False,
        split_protocol="frozen_canonical",
    )
    write(output / "manifest.json", manifest.model_dump(mode="json"))
    protocol = {
        "version": VERSION,
        "corpus_sha256": hashlib.sha256(corpus_raw.encode()).hexdigest(),
        "samples": 900,
        "families": audit,
        "splits": dict(Counter(r.split for r in corpus.samples)),
        "collection_cap_usd": "1.50",
        "pilot_cap_usd": "0.50",
        "additional_cap_usd": "2.00",
        "preserved_vae_reservation_usd": "0.00230895",
        "old_vae_exception_authorized": True,
        "max_concurrency": 1,
        "serving_scope": "single-turn only; numeric final answers, source-span JSON, Vietnamese grounded QA; no code/open/hybrid/memory/RAG certification",
        "grading_protocol": "source deterministic gold; no teacher outcomes; evaluator targets never sent to generation",
        "source_urls": [
            "https://huggingface.co/datasets/openai/gsm8k",
            "https://github.com/facebookresearch/MLQA",
            "https://huggingface.co/datasets/rajpurkar/squad",
        ],
        "sources_avoided": [
            "VMLU: original README says Licenses TBU",
            "UIT-ViQuAD2.0: original terms unresolved",
        ],
        "state": "FROZEN_BEFORE_COLLECTION",
    }
    write(output / "protocol.json", protocol)
    print(json.dumps({"status": "FROZEN", "samples": 900, "families": audit}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=ROOT / "data/router-task-family-v1-20261027"
    )
    parser.add_argument("--catalog", type=Path, default=ROOT / "config/models.json")
    prepare(parser.parse_args())
