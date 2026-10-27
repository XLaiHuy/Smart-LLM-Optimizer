"""Train the router from an already labeled router-dataset-v2 file.

This script is intentionally offline: it never calls a provider and never
performs distillation. It is suitable for Google Colab or Kaggle after the
DEV dataset has been prepared and reviewed locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Labeled router-dataset-v2 JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output artifact JSON")
    parser.add_argument(
        "--hybrid",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use grouped-OOF hybrid training (default: enabled)",
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=None,
        help="Optional number of GBDT trees",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output artifact",
    )
    return parser.parse_args()


def _preflight(raw: dict) -> None:
    if raw.get("format_version") != "router-dataset-v2":
        raise ValueError("Dataset must have format_version=router-dataset-v2")

    reference = raw.get("reference_config_id")
    configs = [item["config_id"] for item in raw.get("configurations", [])]
    candidates = [config_id for config_id in configs if config_id != reference]
    rows = raw.get("samples", [])
    print(f"Dataset: {raw.get('version')} | samples={len(rows)}")
    print(f"Reference: {reference} | candidates={', '.join(candidates)}")

    for candidate in candidates:
        print(f"\n{candidate}")
        for split in ("train", "calibration", "threshold", "holdout"):
            split_rows = [row for row in rows if row.get("split") == split]
            values = [
                bool(next(obs["qualified"] for obs in row["observations"] if obs["config_id"] == candidate))
                for row in split_rows
            ]
            passed = sum(values)
            failed = len(values) - passed
            print(f"  {split:11s} PASS={passed:3d} FAIL={failed:3d}")
            if split in ("train", "calibration") and (passed == 0 or failed == 0):
                raise ValueError(
                    f"{candidate} thiếu cả hai nhãn ở {split}: PASS={passed}, FAIL={failed}. "
                    "Không được sửa tay nhãn; cần bổ sung/review dữ liệu."
                )

    train_rows = [row for row in rows if row.get("split") == "train"]
    for candidate in candidates:
        for label in (False, True):
            groups = {
                row["group_id"]
                for row in train_rows
                if bool(next(obs["qualified"] for obs in row["observations"] if obs["config_id"] == candidate))
                == label
            }
            if len(groups) < 2:
                raise ValueError(
                    f"{candidate} có {len(groups)} group độc lập cho label={label} trong train; "
                    "hybrid grouped OOF cần ít nhất 2 group mỗi lớp."
                )


def main() -> int:
    args = _parse_args()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "backend"))

    raw = json.loads(args.dataset.read_text(encoding="utf-8"))
    _preflight(raw)

    from app.routing.ml.multi_training import MultiDataset, train_multi

    dataset = MultiDataset.model_validate(raw)
    if dataset.purpose == "qualified_holdout":
        raise ValueError("A qualified HOLDOUT dataset cannot be used for training")

    artifact = train_multi(
        dataset,
        hybrid=args.hybrid,
        n_estimators=args.n_estimators,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"Output exists; use --overwrite: {args.output}")
    artifact_json = artifact.model_dump_json()
    args.output.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")

    print("\nTRAIN_SUCCESS")
    print(json.dumps({
        "output": str(args.output),
        # MultiArtifact is the persisted model; its runtime hash is the SHA-256
        # of the compact Pydantic JSON representation used by the service.
        "artifact_hash": hashlib.sha256(artifact_json.encode()).hexdigest(),
        "architecture": "hybrid_grouped_oof" if args.hybrid else "linear",
        "threshold_report": artifact.threshold_report,
        "live_approved": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"TRAIN_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
