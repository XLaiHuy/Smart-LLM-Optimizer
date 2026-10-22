"""Download pinned public assets and prepare candidate DEV/HOLDOUT; never call an LLM."""

import argparse
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "2c4055b12046f11709e9df2c122e59ffbdc2f900"
MODEL_HASH = "d6ea442ff6a891daefed7c83b2f596fc5dc66bf697e4d006236f64f34bbcf4c8"
SOURCES = (
    ("tridm/VMLU", "9ed8d5ca21c680783da62e26f499facf47788568", "train.jsonl", "vmlu"),
    ("tridm/VMLU", "9ed8d5ca21c680783da62e26f499facf47788568", "valid.jsonl", "vmlu"),
    (
        "tridm/VMLU",
        "9ed8d5ca21c680783da62e26f499facf47788568",
        "test.jsonl",
        "vmlu_unlabeled",
    ),
    (
        "taidng/UIT-ViQuAD2.0",
        "406f09a45cc106a8f7b7fd0c25078883fe58cb1f",
        "data/train-00000-of-00001.parquet",
        "viquad",
    ),
    (
        "taidng/UIT-ViQuAD2.0",
        "406f09a45cc106a8f7b7fd0c25078883fe58cb1f",
        "data/validation-00000-of-00001.parquet",
        "viquad",
    ),
    (
        "aisingapore/Instruction-Following-IFEval",
        "1b7947549d2871c44b21956e9f23e90ce830cc37",
        "vi/eval-00000-of-00001.parquet",
        "ifeval",
    ),
)

SOURCE_HASHES = {
    "train.jsonl": "e4eb5a51a75639bdcc080c96556b09fcfb875033aec867844c15d308ed3c1f0b",
    "valid.jsonl": "02082d081e8e57b5a1c4c91b11e3caefea2f0f92937d649f5cc61b065bae5e8c",
    "test.jsonl": "f625e503b6e6713759d8f9ae259724a0b0ce2261fb1e0e0428724d52e184aa3e",
    "data/train-00000-of-00001.parquet": "6e68a0c8fb6fa3c7f89e5b3825e3b3e96fd66913db89a9bdfcaf8fa2b5469e19",
    "data/validation-00000-of-00001.parquet": "8c81bdd75bd39eeff98df769f2282453397fa8c7004085e4fe3fc6e419733ae0",
}


def fetch(url: str, target: Path, expected: str | None = None) -> str:
    if target.exists():
        raw_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected is None or raw_hash == expected:
            return raw_hash
        raise ValueError(
            "Existing asset differs from pinned hash; review before replacing"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".download")
    hasher = hashlib.sha256()
    with (
        httpx.Client(timeout=120, follow_redirects=True) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        with temporary.open("wb") as output:
            for chunk in response.iter_bytes():
                output.write(chunk)
                hasher.update(chunk)
    value = hasher.hexdigest()
    if expected and value != expected:
        raise ValueError("Downloaded asset hash mismatch")
    temporary.replace(target)
    return value


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def encoder() -> None:
    directory = ROOT / "data/router-assets/minilm-int8"
    model = directory / "model_int8.onnx"
    tokenizer = directory / "tokenizer.json"
    base = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/"
    model_hash = fetch(base + "onnx/model_int8.onnx", model, MODEL_HASH)
    token_hash = fetch(
        base + "tokenizer.json",
        tokenizer,
        "b60b6b43406a48bf3638526314f3d232d97058bc93472ff2de930d43686fa441",
    )
    fetch(base + "README.md", directory / "README.md")
    save(
        ROOT / "config/encoder.minilm-int8.json",
        {
            "repository": MODEL_REPO,
            "revision": MODEL_REVISION,
            "model_path": model.relative_to(ROOT).as_posix(),
            "model_sha256": model_hash,
            "tokenizer_path": tokenizer.relative_to(ROOT).as_posix(),
            "tokenizer_sha256": token_hash,
            "hidden_size": 384,
            "max_tokens": 128,
            "recipe": "feature-view-v2-balanced-token-budget",
            "quantization": "int8",
        },
    )
    save(
        directory / "provenance.json",
        {
            "export_repository": MODEL_REPO,
            "revision": MODEL_REVISION,
            "upstream": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "upstream_revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
            "upstream_license": "apache-2.0",
            "upstream_card": "https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "model_sha256": model_hash,
            "tokenizer_sha256": token_hash,
        },
    )
    print("Pinned INT8 encoder and tokenizer ready (public weights; no API usage)")


def datasets() -> None:
    import pyarrow.parquet as pq  # type: ignore[import-not-found]
    from app.contracts.dtos import Message
    from app.contracts.training import RawTrainingSample, TrainingSource
    from app.routing.ml.collection import parse_corpus

    directory = ROOT / "data/router-corpus-v1"
    records, candidates = [], []
    for repo, revision, filename, adapter in SOURCES:
        path = directory / "raw" / repo.replace("/", "--") / filename
        try:
            sha = fetch(
                f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{filename}",
                path,
                SOURCE_HASHES.get(filename),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (401, 403):
                raise
            records.append(
                {
                    "repository": repo,
                    "revision": revision,
                    "file": filename,
                    "status": "access_required_not_downloaded",
                    "http_status": exc.response.status_code,
                }
            )
            continue
        records.append(
            {
                "repository": repo,
                "revision": revision,
                "file": filename,
                "sha256": sha,
                "local_path": path.relative_to(ROOT).as_posix(),
                "license": "cc-by-4.0"
                if adapter == "ifeval"
                else "REVIEW_ORIGINAL_LICENSE_REQUIRED",
                "status": "candidate",
                "grader_status": "instruction_rules_review_required"
                if adapter == "ifeval"
                else "source_grader_review_required",
            }
        )
        heldout = "valid.jsonl" in filename or "validation-" in filename
        if adapter == "vmlu_unlabeled":
            records[-1]["status"] = "unlabeled_inputs_only_not_accuracy_evidence"
            continue
        if adapter == "vmlu":
            source = TrainingSource(
                local_path=str(path),
                sha256=sha,
                adapter="vmlu",
                license="pending original review",
                provenance=repo + "@" + revision,
            )
            for row in parse_corpus(path.read_bytes(), source, limit=2000).samples:
                if not heldout and row.split == "holdout":
                    continue
                candidates.append(
                    row.model_copy(
                        update={
                            "task_id": "vmlu:" + row.task_id,
                            "split": "holdout" if heldout else row.split,
                        }
                    )
                )
        else:
            for row in pq.read_table(path).to_pylist():
                if adapter == "viquad":
                    context, question = row["context"], row["question"]
                    # Whole document title is the grouping unit, not individual QA rows.
                    group = (
                        "viquad:"
                        + hashlib.sha256(
                            str(row.get("title") or context).encode()
                        ).hexdigest()
                    )
                    answers = row["answers"]
                    gold = json.dumps(
                        {
                            "answers": answers,
                            "is_impossible": row.get(
                                "is_impossible", not bool(answers.get("text"))
                            ),
                        },
                        ensure_ascii=False,
                    )
                    prompt = (
                        context
                        + "\n\n"
                        + question
                        + "\nTrả lời ngắn; nêu rõ nếu không có thông tin."
                    )
                    domain = "reading_comp_rag"
                else:
                    prompt = row["prompt"]
                    group = "ifeval:" + hashlib.sha256(prompt.encode()).hexdigest()
                    gold = json.dumps(
                        {
                            "instruction_id_list": row["instruction_id_list"],
                            "kwargs": row["kwargs"],
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                    domain = "instruction_following"
                from app.routing.ml.collection import group_split

                candidates.append(
                    RawTrainingSample(
                        task_id=group
                        + ":"
                        + str(
                            row.get(
                                "id",
                                row.get("key", question if adapter == "viquad" else ""),
                            )
                        ),
                        group_id=group,
                        domain=domain,
                        split="holdout" if heldout else group_split(group),
                        messages=(Message(role="user", content=prompt),),
                        gold=gold,
                        has_rag_context=adapter == "viquad",
                    )
                )
    # Freeze 160 independent units; keep one question per source group.
    counts = {"train": 80, "calibration": 24, "threshold": 24, "holdout": 32}
    groups, hashes, selected = set(), set(), []
    # Interleave source families rather than taking a VMLU-only prefix.
    buckets = {}
    representatives = {}
    overlap_groups = set()
    for row in candidates:
        previous = representatives.get(row.group_id)
        if previous is not None and previous.split != row.split:
            if "holdout" not in (previous.split, row.split):
                raise ValueError("Source document crosses DEV splits")
            overlap_groups.add(row.group_id)
            if row.split == "holdout":
                representatives[row.group_id] = row
            continue
        representatives.setdefault(row.group_id, row)
    for row in representatives.values():
        buckets.setdefault(row.domain, []).append(row)
    ordered = []
    while any(buckets.values()):
        for bucket in buckets.values():
            if bucket:
                ordered.append(bucket.pop(0))
    for row in ordered:
        key = hashlib.sha256(row.messages[0].content.strip().encode()).hexdigest()
        if counts[row.split] > 0 and row.group_id not in groups and key not in hashes:
            selected.append(row)
            groups.add(row.group_id)
            hashes.add(key)
            counts[row.split] -= 1
    if any(counts.values()):
        raise ValueError(f"Insufficient independent source coverage: {counts}")
    save(
        directory / "corpus.json",
        {"samples": [row.model_dump(mode="json") for row in selected]},
    )
    save(
        directory / "sources.json",
        {
            "status": "candidate_not_qualified",
            "sources": records,
            "samples": len(selected),
            "overlap_groups_excluded_from_dev": sorted(overlap_groups),
            "independent_groups": len(groups),
            "splits": {
                split: sum(r.split == split for r in selected) for split in counts
            },
            "domains": {
                domain: sum(r.domain == domain for r in selected) for domain in buckets
            },
            "corpus_sha256": hashlib.sha256(
                (directory / "corpus.json").read_bytes()
            ).hexdigest(),
            "limitations": [
                "Original VMLU/ViQuAD licensing and grader review pending",
                "SEA-IFEval access required; not downloaded or grader-qualified",
                "No model observations/distillation or measured quality/cost fabricated",
                "Only source families listed here are prepared; coding/memory coverage incomplete",
            ],
        },
    )
    print(
        "160 independent candidate units prepared; source/grader qualification remains pending"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--encoder", action="store_true")
    parser.add_argument("--datasets", action="store_true")
    options = parser.parse_args()
    if options.encoder:
        encoder()
    if options.datasets:
        datasets()
