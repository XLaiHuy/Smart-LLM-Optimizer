"""Create a catalog-aligned copy of a router dataset without re-calling providers.

This is safe only for an existing measured dataset whose three config IDs are
the same as the runtime catalog. It updates configuration metadata and keeps
all measured observations unchanged. The resulting dataset must be retrained
before it can be loaded by the live router.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    generation = [m for m in catalog["models"] if m.get("kind") == "generation"]
    ids = {c["config_id"] for c in dataset["configurations"]}
    catalog_by_id = {m["config_id"]: m for m in generation}
    if not ids <= set(catalog_by_id):
        missing = sorted(ids - set(catalog_by_id))
        raise SystemExit(f"Config ID mismatch; missing_in_catalog={missing}")

    aligned = dict(dataset)
    aligned["configurations"] = [
        {
            "config_id": m["config_id"],
            "model_id": m["model_id"],
            "execution_source": "live",
            "context_window": m["context_window"],
            "available": bool(m.get("verified_access") and m.get("pricing_verified")),
            "availability_reason": "reviewed",
            "endpoint": m["endpoint"],
            "max_output_tokens": m["max_output_tokens"],
            "structured_output": bool(m.get("structured_output", False)),
            "supported_parameters": m.get("supported_parameters", []),
            "function_calling": bool(m.get("function_calling", False)),
            "reasoning_effort": m.get("reasoning_effort"),
        }
        for m in generation
        if m["config_id"] in ids
    ]
    aligned["reference_config_id"] = catalog["baseline_config"]
    if aligned["reference_config_id"] not in ids:
        raise SystemExit("Catalog baseline_config is not one of the dataset configurations")
    aligned["costs"] = dict(aligned["costs"])
    aligned["costs"]["version"] = catalog["version"]
    aligned["version"] = f"{dataset['version']}-runtime-aligned"
    aligned["provenance"] = (
        dataset.get("provenance", "")
        + " | configuration metadata aligned to config/models.json; observations unchanged"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aligned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ALIGNED_DATASET={args.output}")
    print(f"REFERENCE={aligned['reference_config_id']}")
    print("OBSERVATIONS_UNCHANGED=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
