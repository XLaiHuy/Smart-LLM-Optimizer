"""Create a deterministic, split-safe local corpus for a Router training pilot.

The generated corpus is intentionally written below ``data/`` (gitignored). It
never modifies the supplied source dataset, and every source group stays in one
split to prevent prompt leakage between DEV and HOLDOUT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SPLITS = ("train", "calibration", "threshold", "holdout")


def split_for(group_id: str) -> str:
    bucket = int(hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 50:
        return "train"
    if bucket < 70:
        return "calibration"
    if bucket < 85:
        return "threshold"
    return "holdout"


def prepare(source: Path, output: Path, limit: int) -> dict[str, int]:
    if limit < 16:
        raise ValueError("limit must be at least 16")
    raw: Any = json.loads(source.read_text(encoding="utf-8"))
    rows = raw.get("samples") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise ValueError("source must contain a samples array")

    quotas = {
        "train": limit // 2,
        "calibration": max(4, limit // 5),
        "threshold": max(4, limit // 7),
    }
    quotas["holdout"] = limit - sum(quotas.values())
    if quotas["holdout"] < 4:
        raise ValueError("limit is too small to keep four independent splits")

    selected: list[dict[str, Any]] = []
    counts = {split: 0 for split in SPLITS}
    seen_groups: set[str] = set()
    ordered = sorted(rows, key=lambda row: str(row.get("task_id", "")))
    for row in ordered:
        group_id = row.get("group_id")
        if not isinstance(group_id, str) or group_id in seen_groups:
            continue
        split = split_for(group_id)
        if counts[split] >= quotas[split]:
            continue
        copied = dict(row)
        copied["split"] = split
        selected.append(copied)
        seen_groups.add(group_id)
        counts[split] += 1
        if len(selected) == limit:
            break

    if len(selected) != limit or any(counts[split] < 4 for split in SPLITS):
        raise ValueError(f"insufficient independent groups for requested split: {counts}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"samples": selected}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=64)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.limit), ensure_ascii=False))


if __name__ == "__main__":
    main()
