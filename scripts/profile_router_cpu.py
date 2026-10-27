"""Local policy timings. No HTTP/DB/provider latency or live qualification."""

import argparse
import json
import os
import platform
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import numpy as np
from app.contracts.dtos import (
    FeatureFlags,
    PolicySnapshot,
    RegistrySnapshot,
    RemainingBudget,
)
from app.routing.features import extract_context_features
from app.routing.ml.multi_training import MultiDataset
from app.routing.ml.service import MLRouterService
from app.routing.policies import PolicyRouter


def profile(model: Path, dataset: Path, count: int, concurrency: int) -> dict:
    started = perf_counter()
    engine = MLRouterService.load(model)
    load_ms = (perf_counter() - started) * 1000
    if engine.status != "ML_ARTIFACT_READY" or not engine.multi.semantic:
        raise ValueError("Semantic router unavailable")
    data = MultiDataset.model_validate_json(dataset.read_text(encoding="utf-8"))
    rows = list(data.samples)[:: max(1, len(data.samples) // count)][:count]
    router = PolicyRouter(engine)
    registry = RegistrySnapshot(
        configurations=data.configurations, mock_config_id=data.reference_config_id
    )
    policy = PolicySnapshot(
        policy_id="local-timing",
        strategy="ml_multi_model",
        sandbox=True,
        flags=FeatureFlags(router=True),
    )

    def run(row):
        start = perf_counter()
        result = router.select(
            extract_context_features(row.messages, row.has_rag_context),
            row.context(),
            registry,
            data.costs,
            policy,
            RemainingBudget(usd=row.max_usd, deadline_ms=row.deadline_ms),
        )
        if result.reason_code not in {
            "ROUTE_ML_MULTI_REFERENCE",
            "ROUTE_ML_MULTI_CANDIDATE",
        }:
            raise ValueError("Timing run unexpectedly fell back")
        return (perf_counter() - start) * 1000

    def stats(values):
        return dict(
            zip(
                ("p50_ms", "p95_ms", "p99_ms"),
                [round(float(v), 3) for v in np.percentile(values, [50, 95, 99])],
                strict=True,
            )
        )

    misses, hits = [], []
    for row in rows:
        engine.multi.semantic.cache.clear()
        misses.append(run(row))
        hits.append(run(row))
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        concurrent = list(pool.map(run, rows))
    elapsed = perf_counter() - started

    # Explicit benchmark of NumPy CPU cross-attention pooling
    from app.routing.ml.attention import numpy_features

    attn_timings = []
    if engine.multi.semantic and engine.multi.semantic.state:
        attn_state = engine.multi.semantic.state
        mock_states = np.random.randn(32, attn_state.encoder.hidden_size).astype(np.float32)
        mock_mask = np.ones(32, dtype=bool)
        for _ in range(10):
            _ = numpy_features(attn_state, mock_states, mock_mask)
        for _ in range(200):
            t0 = perf_counter()
            _ = numpy_features(attn_state, mock_states, mock_mask)
            attn_timings.append((perf_counter() - t0) * 1000)

    attn_stats = stats(attn_timings) if attn_timings else {}

    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "numpy": np.__version__,
        },
        "measurement": "local_policy_selection_excludes_http_db_and_provider",
        "purpose": data.purpose,
        "backend": engine.multi.semantic.backend,
        "artifact_hash": engine.hash,
        "samples": len(rows),
        "concurrency": concurrency,
        "load_ms": round(load_ms, 3),
        "attention_numpy_cpu": attn_stats,
        "attention_latency_target_met": (attn_stats.get("p50_ms", 999.0) < 0.5) if attn_stats else False,
        "cache_miss": stats(misses),
        "cache_hit": stats(hits),
        "concurrent_cache_miss": stats(concurrent),
        "concurrent_requests_per_second": round(len(rows) / elapsed, 2),
        "limitations": [
            "Local timings depend on hardware and load",
            "No LLM quality, savings or TTFT overhead percentage is inferred",
            "CPU pooling does not prove CUDA FlashAttention",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", type=Path, default=Path("config/router_final_candidate.json")
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/research/router-final-holdout-v3.json"),
    )
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--output", type=Path, default=Path("output/router-final/profile.json")
    )
    args = parser.parse_args()
    if args.samples < 2 or args.concurrency < 1:
        parser.error("Need at least two samples and one worker")
    result = profile(args.model, args.dataset, args.samples, args.concurrency)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
