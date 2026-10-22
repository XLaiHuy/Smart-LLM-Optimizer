"""Prepare pinned, license-reviewed public TRAIN pools; no LLM calls or API keys."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pyarrow.parquet as pq
from app.config import ROOT
from prepare_flash_resources import fetch

SOURCES = (
    (
        "openai/gsm8k",
        "740312add88f781978c0658806c59bc2815b9866",
        "main/train-00000-of-00001.parquet",
        "gsm8k",
        "mit",
    ),
    (
        "google-research-datasets/mbpp",
        "4bb6404fdc6cacfda99d4ac4205087b89d32030c",
        "full/train-00000-of-00001.parquet",
        "mbpp",
        "cc-by-4.0",
    ),
    (
        "CohereLabs/aya_dataset",
        "f9ea04583f02a8f86404ff6c58bf75fe637df8a2",
        "data/train-00000-of-00001.parquet",
        "aya",
        "apache-2.0",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=ROOT / "data/router-pilot-v1")
    parser.add_argument(
        "--without-aya",
        action="store_true",
        help="Deterministic-only pilot; records the missing open-instruction coverage",
    )
    parser.add_argument(
        "--synthesize",
        action="store_true",
        help="Enable at most 20 verified arithmetic variants, inside the same 5 USD operation",
    )
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    image = subprocess.run(
        ["docker", "image", "inspect", "python:3.11-slim", "--format", "{{.Id}}"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    sources, provenance = [], []
    for repo, revision, filename, adapter, license_name in SOURCES:
        if adapter == "aya" and args.without_aya:
            continue
        path = args.directory / "raw" / repo.replace("/", "--") / Path(filename).name
        sidecar = path.with_suffix(".sha256")
        if path.exists() and not sidecar.exists():
            raise ValueError(
                "Existing raw file has no provenance hash; review before reusing"
            )
        expected = sidecar.read_text().strip() if sidecar.exists() else None
        print("Preparing public source:", repo, flush=True)
        sha = fetch(
            f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{filename}",
            path,
            expected,
        )
        sidecar.write_text(sha, encoding="utf-8")
        rows = pq.read_table(path).to_pylist()
        if adapter == "aya":
            rows = [
                r
                for r in rows
                if r.get("language_code") == "vie"
                and r.get("inputs")
                and r.get("targets")
            ]
        if adapter == "mbpp":
            for row in rows:
                row["docker_image"] = image
        output = args.directory / f"{adapter}.json"
        # Original output/code/answer stays evaluator-only in the adapter.
        output.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        sources.append(
            {
                "local_path": output.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "adapter": adapter,
                "license": license_name,
                "license_url": f"https://huggingface.co/datasets/{repo}/blob/{revision}/README.md",
                "license_reviewed": True,
                "allow_training": True,
                "provenance": f"Public dataset TRAIN split {repo}@{revision}; raw={filename}; raw-sha256={sha}; license per publisher dataset card",
            }
        )
        provenance.append(
            {
                "repository": repo,
                "revision": revision,
                "file": filename,
                "raw_sha256": sha,
                "license": license_name,
                "rows": len(rows),
            }
        )
    names = ("gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro")
    manifest = {
        "version": "gemini-gold-pilot-v1",
        "reviewed_by": "operator-authorized-pilot; publisher-card-license-check",
        "pricing_source": "https://ai.google.dev/gemini-api/docs/pricing; Standard text <=200k, reviewed 2026-10-22; conservative paid-tier estimates, not free-tier claims",
        "access_verified": True,
        "software_test": False,
        "pilot": True,
        "source": sources[0],
        "sources": sources,
        "configurations": [
            {
                "config_id": name,
                "model_id": name,
                "execution_source": "live",
                "endpoint": "gemini_chat_completions",
                "context_window": 32768,
                "max_output_tokens": 4096,
                "reasoning_effort": "none" if i == 0 else "low",
            }
            for i, name in enumerate(names)
        ],
        "reference_config_id": names[-1],
        "costs": {
            "version": "gemini-standard-text-20261022",
            "rates": [
                {"config_id": name, "input_per_million": inp, "output_per_million": out}
                for name, inp, out in zip(
                    names,
                    ("0.10", "0.30", "1.25"),
                    ("0.40", "2.50", "10.00"),
                    strict=True,
                )
            ],
        },
        "max_samples": 500,
        "min_interval_seconds": 6.2,
        "encoder_spec_path": "config/encoder.minilm-int8.json",
        "attention_epochs": 15,
        "domain_loss_weight": 0,
        "docker_image": image,
        "synthesize": args.synthesize,
    }
    (args.directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (args.directory / "sources.json").write_text(
        json.dumps(
            {
                "sources": provenance,
                "excluded_pending_original_terms": ["VMLU", "UIT-ViQuAD2.0"],
                "coverage_limitations": [
                    "No legal/medical-specific qualified corpus",
                    "English math/code; Vietnamese instruction subset only when Aya included",
                ],
                "labels": "Actual labels will be measured from candidate responses; never copied from fixture observations",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Prepared pilot manifest:", args.directory / "manifest.json", flush=True)


if __name__ == "__main__":
    main()
