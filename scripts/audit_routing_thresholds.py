"""DEV-only threshold frontier and prompt activation probes. No provider calls.

Never reads HOLDOUT. Does not mutate serving artifacts, receipts or catalog.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from app.contracts.dtos import ContextResult, Message, OptimizationState
from app.routing.ml.multi import MultiRouterService
from app.routing.ml.multi_training import MultiDataset, replay_rows


def prompt_context(text):
    return ContextResult(
        messages=(Message(role="user", content=text),),
        provenance=(),
        state=OptimizationState(
            module="context", status="disabled", reason="activation_probe"
        ),
    )


def measure(replays, reference, thresholds):
    selected = []
    for row, scores, order in replays:
        chosen = next((c for c in order if scores[c] >= thresholds[c]), reference)
        observations = {o.config_id: o for o in row.observations}
        selected.append((row, chosen, observations[chosen], observations[reference]))
    return {
        "thresholds": thresholds,
        "n": len(selected),
        "correct": sum(obs.qualified for _, _, obs, _ in selected),
        "reference_correct": sum(ref.qualified for _, _, _, ref in selected),
        "regressions": sum(
            ref.qualified and not obs.qualified for _, _, obs, ref in selected
        ),
        "cost_usd": str(sum(obs.usd for _, _, obs, _ in selected)),
        "distribution": dict(Counter(c for _, c, _, _ in selected)),
        "domains": {
            domain: {
                "n": sum(row.domain == domain for row, *_ in selected),
                "correct": sum(
                    obs.qualified for row, _, obs, _ in selected if row.domain == domain
                ),
                "regressions": sum(
                    ref.qualified and not obs.qualified
                    for row, _, obs, ref in selected
                    if row.domain == domain
                ),
            }
            for domain in sorted({row.domain for row, *_ in selected})
        },
    }


def main(args):
    data = MultiDataset.model_validate_json(args.dev.read_text(encoding="utf-8"))
    # Only the designated threshold split may select a new operating point.
    rows = tuple(row for row in data.samples if row.split == "threshold")
    if not rows or any(row.split == "holdout" for row in data.samples):
        raise ValueError("DEV-only input with independent threshold rows required")
    engine = MultiRouterService(
        args.artifact.read_text(encoding="utf-8"), allow_research_candidate=True
    )
    if not engine.artifact or not engine.semantic:
        raise ValueError("Attention artifact required")
    ids = [p.config_id for p in engine.artifact.predictors]
    current = {p.config_id: p.threshold for p in engine.artifact.predictors}
    replays = replay_rows(data, engine, rows)
    baseline = measure(replays, data.reference_config_id, current)
    frontier = []
    for small in sorted(
        {
            current[ids[0]],
            0.92,
            0.915,
            0.91,
            0.905,
            0.90,
            0.875,
            0.85,
            0.825,
            0.80,
            0.75,
            0.70,
            0.60,
            0.50,
        }
    ):
        for luna in sorted(
            {
                current[ids[1]],
                0.895,
                0.89,
                0.875,
                0.85,
                0.80,
                0.75,
                0.70,
                0.60,
                0.50,
                0.40,
                0.30,
            }
        ):
            frontier.append(
                measure(
                    replays, data.reference_config_id, dict(zip(ids, (small, luna)))
                )
            )
    # Predeclared conservative DEV rule: do not lose total or per-domain correct
    # answers and do not add regressions compared with current research policy.
    eligible = [
        r
        for r in frontier
        if r["correct"] >= baseline["correct"]
        and r["regressions"] <= baseline["regressions"]
        and all(
            r["domains"][d]["correct"] >= v["correct"]
            and r["domains"][d]["regressions"] <= v["regressions"]
            for d, v in baseline["domains"].items()
        )
    ]
    best = (
        min(
            eligible,
            key=lambda r: (float(r["cost_usd"]), -sum(r["thresholds"].values())),
        )
        if eligible
        else baseline
    )
    probes = [
        "1 + 1 bằng mấy? Chỉ trả lời một từ.",
        "Xin chào!",
        "Tính (−313) + (−211). Chỉ trả lời kết quả.",
        "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
        "Viết hàm Python tìm phần tử xuất hiện nhiều nhất, hòa chọn phần tử đầu tiên.",
        "Translate into English: Tôi đang học tại Đại học Mở.",
        "Thủ đô của Việt Nam là thành phố nào? Chỉ trả lời tên.",
        "Bạn nhớ tôi tên gì không?",
        "Giải thích ELBO trong VAE.",
    ]
    # Source DEV prompts can supply additional real score activation examples.
    probes += [row.messages[-1].content for row in rows]
    activations = []
    for text in probes:
        context = prompt_context(text)
        scores = {key: engine.score(key, context, False, False) for key in ids}
        selected = next(
            (key for key in ids if scores[key] >= best["thresholds"][key]),
            data.reference_config_id,
        )
        old = next(
            (key for key in ids if scores[key] >= current[key]),
            data.reference_config_id,
        )
        activations.append(
            {
                "prompt": text,
                "scores": scores,
                "current_selection": old,
                "proposed_selection": selected,
                "dry_run_only": True,
            }
        )
    report = {
        "dev_source": str(args.dev),
        "no_holdout_read": True,
        "baseline": baseline,
        "selected_dev_policy": best,
        "frontier": frontier,
        "activations": activations,
        "formal_qualification": False,
        "serving_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"baseline": baseline, "selected_dev_policy": best}, ensure_ascii=False
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args())
