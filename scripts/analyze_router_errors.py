"""Read-only error attribution and targeted source sampling; never calls providers.

Old HOLDOUT is diagnostic only and is not copied into the new training set.
New source families are split before any provider outcomes are collected.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from app.contracts.dtos import Message
from app.contracts.training import (
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingManifest,
)
from app.routing.ml.pilot import validate_corpus
from app.routing.ml.pipeline import cache_key
from prepare_router_qualification import mcq_gold, mcq_options
from router_family_protocol import family_map


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def source_text(text):
    return re.sub(
        r"\n(?:Give only the final numeric answer\.|Chỉ trả lời một chữ cái trong các lựa chọn\.)$",
        "",
        text.strip(),
    )


def surface_issues(text):
    """Conservative visible input defects; not a semantic correctness judge."""
    issues = []
    if "\ufffd" in text:
        issues.append("unicode_replacement_character")
    if re.search(r"https?://|<img|!\[.*?\]\(|Bài tập trắc nghiệm .*có đáp án \|", text):
        issues.append("possible_missing_or_scraped_content")
    if re.search(
        r"(?:hình (?:vẽ |ảnh )?(?:sau|dưới)|bảng (?:sau|dưới))", text, re.IGNORECASE
    ):
        issues.append("external_visual_or_table_requires_review")
    if re.search(r"hiện nay|hiện tại|cuối cùng", text, re.IGNORECASE) and not re.search(
        r"\b(?:19|20)\d{2}\b", text
    ):
        issues.append("time_dependent_question_without_reference_date")
    if "giàu nhất thế giới" in text.casefold() and not re.search(
        r"GDP|PPP|bình quân|đầu người|theo", text, re.IGNORECASE
    ):
        issues.append("wealth_ranking_metric_unspecified")
    return issues


def topics(text, domain):
    value = text.casefold()
    tags = []
    if re.search(r"%|percent|phần trăm", value):
        tags.append("percent_and_inverse_percent")
    if re.search(r"[−–-]\s*\d|số nguyên|âm|integer", value):
        tags.append("signed_arithmetic")
    if re.search(r"chia hết|ước|bội|nguyên tố|divisib|prime", value):
        tags.append("divisibility_and_prime")
    if re.search(r"\b(?:age|years old|tuổi|twice|half|less|more)\b", value):
        tags.append("relations_and_multistep")
    if re.search(r"không|sai|ngoại trừ|except|not\b", value):
        tags.append("negation_or_exception")
    return tags or ["math_other" if domain == "math_reasoning" else "mcq_other"]


def error_breakdown(outcomes, measured):
    counts = Counter()
    for row in outcomes:
        observations = measured[row["task_id"]]["observations"]
        if row["qualified"]:
            category = (
                "route_improves_reference"
                if not row["reference_qualified"]
                else "both_pass"
            )
        elif row["reference_qualified"]:
            category = "routing_regression"
        else:
            category = (
                "missed_successful_alternative"
                if any(o["qualified"] for o in observations)
                else "all_measured_profiles_fail"
            )
        counts[category] += 1
    return dict(counts)


def analyze(run, qualification):
    manifest = TrainingManifest.model_validate(load(run / "manifest.json"))
    raw = {s["task_id"]: s for s in load(run / "corpus.json")["samples"]}
    measured = {s["task_id"]: s for s in load(run / "observations.json")}
    outcomes = load(qualification)["holdout"]["outcomes"]
    failures = []
    for result in outcomes:
        if result["qualified"]:
            continue
        sample = raw[result["task_id"]]
        messages = tuple(Message.model_validate(m) for m in sample["messages"])
        answers = []
        for config in manifest.configurations:
            path = (
                run.parent
                / "cache"
                / (cache_key(manifest, config.config_id, messages) + ".json")
            )
            answer = load(path)
            answers.append({"config_id": config.config_id, "text": answer["text"]})
        failures.append(
            {
                **result,
                "prompt": sample["messages"][0]["content"],
                "source_gold": sample["gold"],
                "topics": topics(sample["messages"][0]["content"], sample["domain"]),
                "input_review_flags": surface_issues(sample["messages"][0]["content"]),
                "cached_answers": answers,
            }
        )
    return {
        "version": "router-error-analysis-v1",
        "old_holdout_usage": "diagnostics only; never added to new DEV",
        "counts": error_breakdown(outcomes, measured),
        "failures": failures,
        "attention_diagnostics": load(run / "attention-dev-diagnostics.json"),
        "limitations": [
            "Source gold is retained verbatim; suspicious answers require independent review",
            "Formatting failure remains failure when prompt requires only a number",
            "Feature saturation is descriptive and does not establish causality",
        ],
    }


def prepare(root, run, qualification, output):
    if output.exists():
        raise ValueError("Use a new output directory; frozen sources are immutable")
    analysis = analyze(run, qualification)
    manifest = TrainingManifest.model_validate(load(run / "manifest.json"))
    historical = {}
    for directory in (
        root / "data/router-live-qualification-20261027",
        root / "data/router-pilot-v1",
    ):
        # A prepared-but-never-measured pool is not an exposed test. Exclude all
        # measured campaigns plus the complete active study, including its test.
        for path in sorted(directory.rglob("observations.json")):
            for row in load(path):
                text = source_text(row["messages"][-1]["content"])
                historical[hashlib.sha256(text.encode()).hexdigest()] = text
    for row in load(run / "corpus.json")["samples"]:
        text = source_text(row["messages"][-1]["content"])
        historical[hashlib.sha256(text.encode()).hexdigest()] = text
    candidates = {}
    rejected = Counter()
    for row in load(root / "data/router-pilot-v1/gsm8k.json"):
        text = row["question"].strip()
        key = hashlib.sha256(text.encode()).hexdigest()
        if key in historical or len(text.encode()) > 2000 or surface_issues(text):
            rejected["math_seen_length_or_surface"] += 1
            continue
        candidates[key] = (
            text,
            "math_reasoning",
            row["answer"].rsplit("####", 1)[-1].strip(),
            (),
        )
    for row in load(root / "data/router-pilot-v1/aya.json"):
        text = row["inputs"].strip()
        key = hashlib.sha256(text.encode()).hexdigest()
        gold = mcq_gold(text, row["targets"])
        if (
            not gold
            or key in historical
            or len(text.encode()) > 2000
            or surface_issues(text)
        ):
            rejected["mcq_seen_unparsable_length_or_surface"] += 1
            continue
        candidates[key] = (text, "vietnamese_mcq", gold, mcq_options(text))
    # Family mapping sees original input only, never answer gold or model success.
    mapping = family_map({**historical, **{k: v[0] for k, v in candidates.items()}})
    excluded_families = {mapping[key] for key in historical}
    unique = {}
    for key in sorted(candidates):
        family = mapping[key]
        if family not in excluded_families:
            unique.setdefault(family, key)
    selected = []
    selected_metadata = []
    available = {}
    for domain in ("math_reasoning", "vietnamese_mcq"):
        pool = [key for key in unique.values() if candidates[key][1] == domain]
        pool.sort(
            key=lambda k: hashlib.sha256(("targeted-v1:" + k).encode()).hexdigest()
        )
        # Seal a fresh, unselected-by-outcome test first. It is not in collection manifest.
        available[domain] = len(pool)
        print(
            json.dumps({"domain": domain, "available_unseen_families": len(pool)}),
            flush=True,
        )
        test_count = min(100, len(pool) // 2)
        holdout = pool[:test_count]
        remaining = pool[test_count:]
        prioritized = [
            k
            for k in remaining
            if topics(candidates[k][0], domain)[0] not in ("math_other", "mcq_other")
        ]
        other = [k for k in remaining if k not in set(prioritized)]
        dev = prioritized[:36] + other[:12]
        dev += [k for k in remaining if k not in set(dev)][: max(0, 48 - len(dev))]
        if len(dev) < 8 or len(holdout) < 8:
            raise ValueError(
                f"Insufficient independent source coverage in {domain}: {len(pool)}"
            )
        train_count = int(len(dev) * 0.6)
        calibration_end = train_count + int(len(dev) * 0.2)
        for i, key in enumerate(dev + holdout):
            text, _, gold, choices = candidates[key]
            split = (
                (
                    "train"
                    if i < train_count
                    else "calibration"
                    if i < calibration_end
                    else "threshold"
                )
                if i < len(dev)
                else "holdout"
            )
            suffix = (
                "\nGive only the final numeric answer."
                if domain == "math_reasoning"
                else "\nChỉ trả lời một chữ cái trong các lựa chọn."
            )
            selected.append(
                RawTrainingSample(
                    task_id="targeted-v1:" + key,
                    group_id=mapping[key],
                    domain=domain,
                    split=split,
                    messages=(Message(role="user", content=text + suffix),),
                    gold=gold,
                    grading=GradingSpec(
                        kind="numeric" if domain == "math_reasoning" else "mcq",
                        choices=choices,
                    ),
                )
            )
            selected_metadata.append(
                {
                    "task_id": selected[-1].task_id,
                    "split": split,
                    "domain": domain,
                    "topics": topics(text, domain),
                }
            )
    corpus = TrainingCorpus(samples=tuple(selected))
    validate_corpus(corpus)
    output.mkdir(parents=True)
    write(output / "error-analysis.json", analysis)
    write(output / "selection.json", selected_metadata)
    (output / "sealed-fresh-holdout.json").write_text(
        TrainingCorpus(
            samples=tuple(s for s in selected if s.split == "holdout")
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    dev_path = output / "corpus.json"
    new_dev_count = sum(s.split != "holdout" for s in selected)
    new_holdout_count = len(selected) - new_dev_count
    dev_path.write_text(
        TrainingCorpus(
            samples=tuple(s for s in selected if s.split != "holdout")
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    source = manifest.source.model_copy(
        update={
            "local_path": str(dev_path.resolve()),
            "sha256": hashlib.sha256(dev_path.read_bytes()).hexdigest(),
            "provenance": manifest.source.provenance
            + "; targeted-v1 original unseen text families; visible defect screen; no new human annotation asserted",
        }
    )
    manifest = manifest.model_copy(
        update={
            "version": "router-targeted-v1-20261027",
            "source": source,
            "max_samples": new_dev_count,
        }
    )
    (output / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    old_dev = load(run / "dev.json")
    quarantine = [
        {"task_id": s["task_id"], "flags": surface_issues(s["messages"][-1]["content"])}
        for s in old_dev["samples"]
        if surface_issues(s["messages"][-1]["content"])
    ]
    write(output / "dev-input-review-queue.json", quarantine)
    plan = {
        "version": "targeted-supplement-v1",
        "source_run": str(run),
        "new_dev": new_dev_count,
        "sealed_new_holdout": new_holdout_count,
        "available_unseen_source_families": available,
        "old_holdout_copied_to_dev": False,
        "old_dev": 300,
        "dev_review_flags": len(quarantine),
        "excluded_historical_families": len(excluded_families),
        "source_rejections": dict(rejected),
        "selection_uses_new_model_outcomes": False,
        "source_family_rule": "char_wb TFIDF3-5 cosine>=0.90 connected components; heuristic, not semantic proof",
        "source_data_sha256": {
            n: hashlib.sha256(
                (root / f"data/router-pilot-v1/{n}.json").read_bytes()
            ).hexdigest()
            for n in ("gsm8k", "aya")
        },
        "recipe": {
            "attention_epochs": 5,
            "change": "targeted data supplement only; keep existing training formula",
            "activation": "no automatic replacement of serving artifact",
        },
        "new_collection_cap_usd": "0.15",
        "overall_existing_cap_usd": "0.80",
        "old_unknown_reserve_usd": "0.0034292",
        "paid_calls_made_by_preparation": 0,
        "holdout_sha256": hashlib.sha256(
            (output / "sealed-fresh-holdout.json").read_bytes()
        ).hexdigest(),
    }
    write(output / "plan.json", plan)
    print(
        json.dumps(
            {
                "counts": analysis["counts"],
                "new_dev": new_dev_count,
                "sealed_test": new_holdout_count,
                "dev_review_flags": len(quarantine),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.root.resolve(), args.run, args.qualification, args.output)
