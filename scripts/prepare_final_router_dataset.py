"""Build deduplicated SOFTWARE TEST data. Never evidence of real model quality/cost.

Templates and document titles, rather than generated group IDs, define independent
units. Existing source HOLDOUT stays separate. DEV units are split before training.
Missing sources fail closed; raw pinned data must already exist locally.
"""

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
from app.contracts.dtos import Message
from app.routing.experiments.fixtures import fixture_setup
from app.routing.ml.independence import content_key
from app.routing.ml.multi_training import MultiDataset
from prepare_golden_5k_dataset import generate_golden_dataset

ROOT = Path(__file__).resolve().parents[1]


def clean_prompt(text: str) -> str:
    text = re.sub(r"^\[[\w-]+-grp-\d+\.\d+\]\s*", "", text)
    return re.sub(
        r"- (?:Phân nhánh|Biến thể|Hồ sơ vụ việc|Ca nghiên cứu|Phiên đối thoại) \d+:",
        ":",
        text,
    ).strip()


def split_units(units: dict[str, tuple[str, str]]) -> dict[str, str]:
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for key, cohort in units.items():
        buckets[cohort].append(key)
    result = {}
    for cohort, keys in sorted(buckets.items()):
        keys.sort(key=lambda key: hashlib.sha256(key.encode()).hexdigest())
        if len(keys) < 3:
            raise ValueError(
                f"Not enough independent families for three DEV splits: {cohort}"
            )
        train = min(len(keys) - 2, max(1, int(len(keys) * 0.6)))
        calibration = max(1, (len(keys) - train) // 2)
        for i, key in enumerate(keys):
            result[key] = (
                "train"
                if i < train
                else "calibration"
                if i < train + calibration
                else "threshold"
            )
    return result


def build() -> tuple[MultiDataset, MultiDataset, dict]:
    dev, holdout = generate_golden_dataset()
    context_titles = {}
    directory = ROOT / "data/router-corpus-v1/raw/taidng--UIT-ViQuAD2.0/data"
    for path in sorted(directory.glob("*.parquet")):
        for row in pq.read_table(path, columns=["context", "title"]).to_pylist():
            context_titles[str(row["context"]).strip()] = str(row["title"])
    units = {}
    pending = []
    seen = set()
    source_groups: dict[str, set[str]] = defaultdict(set)
    for row in [*dev, *holdout]:
        prompt = clean_prompt(row.messages[0].content)
        messages = (Message(role="user", content=prompt),)
        digest = content_key(messages)
        side = "holdout" if row.split == "holdout" else "dev"
        if row.domain == "viquad_reading_comprehension":
            context = prompt.split("\n", 1)[1].split("\n\n", 1)[0].strip()
            if context not in context_titles:
                raise ValueError("Source document title missing")
            family = row.domain + ":" + context_titles[context]
        elif row.domain == "vmlu_multidisciplinary_mcq":
            family = row.domain + ":" + digest
        else:
            family = row.domain + ":" + prompt.split("\n", 1)[0]
        source_groups[family].add(side)
        if len(source_groups[family]) > 1:
            raise ValueError("Source family crosses DEV/HOLDOUT")
        if digest in seen:
            continue
        seen.add(digest)
        # These remain explicit simulation labels; no claim that any LLM answered.
        observations = {o.config_id: o for o in row.observations}
        if row.domain in {"viquad_reading_comprehension", "vmlu_multidisciplinary_mcq"}:
            tier = int(hashlib.sha256(family.encode()).hexdigest()[:8], 16) % 10
            small, medium = tier < 3, tier < 6
        else:
            small, medium = (
                observations["fixture-small"].qualified,
                observations["fixture-medium"].qualified,
            )
        cohort = "easy" if small else "medium" if medium else "hard"
        if side == "dev":
            units[family] = (row.domain, cohort)
        updated = tuple(
            o.model_copy(
                update={
                    "qualified": small
                    if o.config_id == "fixture-small"
                    else medium
                    if o.config_id == "fixture-medium"
                    else True
                }
            )
            for o in row.observations
        )
        pending.append(
            (
                row.model_copy(
                    update={
                        "task_id": digest,
                        "messages": messages,
                        "group_id": hashlib.sha256(family.encode()).hexdigest(),
                        "observations": updated,
                        "critical": not medium,
                    }
                ),
                family,
                side,
            )
        )
    allocation = split_units(units)
    rows = tuple(
        r.model_copy(
            update={"split": "holdout" if side == "holdout" else allocation[family]}
        )
        for r, family, side in pending
    )
    registry, costs, _ = fixture_setup("huy-router-fixtures-v2")
    metadata = {
        "format_version": "router-dataset-v2",
        "purpose": "software_test",
        "provenance": "Deduplicated templates plus pinned public VMLU/ViQuAD inputs; ALL outcomes, tokens, USD and latency are SIMULATED",
        "grader_version": "synthetic-labels-v3-not-a-grader",
        "configurations": registry.configurations,
        "reference_config_id": registry.mock_config_id,
        "costs": costs,
    }
    development = MultiDataset(
        version="router-final-dev-v3",
        samples=tuple(r for r in rows if r.split != "holdout"),
        **metadata,
    )
    validation = MultiDataset(
        version="router-final-holdout-v3",
        samples=tuple(r for r in rows if r.split == "holdout"),
        **metadata,
    )
    # Validate all four splits together, beyond the artifact's raw input hashes.
    MultiDataset(version="audit-only", samples=rows, **metadata)
    audit = {
        "purpose": "software_test",
        "samples": len(rows),
        "independent_source_families": len(source_groups),
        "splits": dict(Counter(r.split for r in rows)),
        "domains": dict(Counter(r.domain for r in rows)),
        "duplicate_inputs_removed": len(dev) + len(holdout) - len(rows),
        "cross_split_content_overlap": 0,
        "cross_split_source_family_overlap": 0,
        "limitations": [
            "Simulation outcomes and prices are not real benchmark evidence",
            "Original source licenses and deterministic graders remain to be qualified",
            "No fixed class proportions or artificial sample count guarantee",
            "VMLU public test has no answer keys; cannot measure accuracy from it",
        ],
    }
    raw = ROOT / "data/router-corpus-v1/raw"
    source_manifest = json.loads(
        (ROOT / "data/router-corpus-v1/sources.json").read_text(encoding="utf-8")
    )
    revisions = {s["repository"]: s["revision"] for s in source_manifest["sources"]}
    audit["source_files"] = []
    for repository, local, filenames in [
        ("tridm/VMLU", "tridm--VMLU", ["train.jsonl", "valid.jsonl", "test.jsonl"]),
        (
            "taidng/UIT-ViQuAD2.0",
            "taidng--UIT-ViQuAD2.0/data",
            ["train-00000-of-00001.parquet", "validation-00000-of-00001.parquet"],
        ),
    ]:
        for name in filenames:
            path = raw / local / name
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            audit["source_files"].append(
                {
                    "repository": repository,
                    "revision": revisions[repository],
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": digest,
                    "license_status": "original_license_review_required",
                }
            )
    audit["builder_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return development, validation, audit


def main() -> None:
    dev, holdout, audit = build()
    output = ROOT / "data/research"
    output.mkdir(exist_ok=True, parents=True)
    for name, data in [
        ("router-final-dev-v3.json", dev),
        ("router-final-holdout-v3.json", holdout),
    ]:
        path = output / name
        path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
        audit[name + ".sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "router-final-audit-v3.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
