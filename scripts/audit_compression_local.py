"""Manual real-weights CPU audit. No provider calls, training or paid APIs."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from app.contracts.dtos import ContextResult, FeatureFlags, OptimizationState
from app.optimizers.llmlingua_compressor import LLMLinguaCompressor
from app.optimizers.prompt_optimizer import AdaptivePromptOptimizer
from app.routing.ml.service import MLRouterService


def cases():
    vi = "Cuộc họp trao đổi thông tin chung về hoạt động và kế hoạch của nhóm sinh viên.\n\n"
    en = "The meeting provides general background information about university planning and student activities.\n\n"
    return [
        ("short", "1 + 1 bằng mấy?", ["1 + 1"]),
        (
            "long_vi",
            vi * 40 + "Mã xác nhận là BLUE-851. Chỉ trả lời mã xác nhận.",
            ["BLUE-851", "Chỉ trả lời mã xác nhận."],
        ),
        (
            "long_en",
            en * 40 + "The confirmation code is BLUE-851. Reply only with the code.",
            ["BLUE-851", "Reply only with the code."],
        ),
        (
            "bounds",
            vi * 20
            + "An có 20 USD, Bình có 10 USD. Chọn người có không ít hơn 15 USD. Chỉ trả lời tên.",
            ["An có 20 USD, Bình có 10 USD.", "không ít hơn 15 USD"],
        ),
        (
            "unicode",
            vi * 20 + "Tính (−313) + (−211). Chỉ trả lời kết quả, giữ dấu âm.",
            ["−313", "−211"],
        ),
        (
            "identifiers",
            vi * 20
            + 'Gửi tới huy@example.com, mã OU-4729, trường user_id, tên "Huy". Chỉ xác nhận.',
            ["huy@example.com", "OU-4729", "user_id", '"Huy"'],
        ),
        (
            "code",
            vi * 20 + "```python\ndef f(x):\n    return x - 2\n```\nGiữ nguyên code.",
            ["```python\ndef f(x):\n    return x - 2\n```"],
        ),
        (
            "json",
            vi * 20 + '{"user_id": "Huy", "limit": -20}\nGiữ nguyên JSON.',
            ['{"user_id": "Huy", "limit": -20}'],
        ),
        (
            "single_oversized_paragraph",
            vi.replace("\n", " ") * 80 + "Mã BLUE-851.",
            ["BLUE-851"],
        ),
        (
            "many_unique",
            "\n\n".join(
                (word + " general background information ") * 50
                for word in ("University", "Meeting", "Library", "Garden")
            )
            + "\n\nReply only BLUE-851.",
            ["Reply only BLUE-851."],
        ),
    ]


async def main(args):
    router = MLRouterService.load(args.artifact, allow_research_candidate=True)
    if not router.multi.semantic:
        raise ValueError("Real local encoder/Attention artifact required")
    compressor = LLMLinguaCompressor(router.multi.semantic.similarity)
    started = perf_counter()
    if not compressor.warmup():
        raise ValueError("Real weights did not load")
    warm_ms = (perf_counter() - started) * 1000
    optimizer = AdaptivePromptOptimizer(compressor)
    context = ContextResult(
        messages=(),
        provenance=(),
        state=OptimizationState(
            module="context", status="disabled", reason="local_compression_audit"
        ),
    )
    report = {
        "real_weights": True,
        "provider_calls": 0,
        "warmup_ms": warm_ms,
        "semantic_threshold": 0.85,
        "cases": [],
        "finished": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name, text, required in cases():
        start = perf_counter()
        raw = await asyncio.to_thread(compressor.compress, text)
        raw_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        optimized = await optimizer.optimize(
            SimpleNamespace(request=SimpleNamespace(message=text)),
            context,
            FeatureFlags(rewrite=True),
        )
        elapsed = (perf_counter() - start) * 1000
        checks = {literal: literal in optimized.proposed for literal in required}
        raw_checks = {literal: literal in raw["compressed"] for literal in required}
        entry = {
            "name": name,
            "input_chars": len(text),
            "raw_ms": raw_ms,
            "optimizer_ms": elapsed,
            "raw": raw,
            "optimized": optimized.model_dump(mode="json"),
            "required_preserved": checks,
            "raw_required_preserved": raw_checks,
        }
        report["cases"].append(entry)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "case": name,
                    "raw_ms": raw_ms,
                    "optimizer_ms": elapsed,
                    "state": optimized.state.model_dump(mode="json"),
                    "hard_checks": all(checks.values()) and all(raw_checks.values()),
                }
            ),
            flush=True,
        )
        if not all(checks.values()) or not all(raw_checks.values()):
            raise ValueError("Protected content changed")
    # Let any bounded worker that outlived its 2s request finish before exit.
    await asyncio.to_thread(lambda: None)
    report["finished"] = True
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact",
        type=Path,
        default=Path("/app/config/router_attention_operator_accepted.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
