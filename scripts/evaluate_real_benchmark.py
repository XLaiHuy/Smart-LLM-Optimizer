"""Automated Evaluator for Real Benchmark Datasets using Gemini & OpenAI APIs.

Executes real inference on authentic benchmark samples (VMLU, UIT-ViQuAD)
and grades deterministically using official ground truths:
- VMLU: Letter-matching Accuracy (Regex / Exact Choice extraction)
- UIT-ViQuAD: Token-level F1 & Exact Match (EM) extraction

Supports:
- Gemini (gemini-3.5-flash-lite, gemini-3.5-flash) via Google AI Studio Key
- OpenAI (gpt-4o-mini, gpt-4o) via OpenAI Key
"""

import json
import re
import sys
import time
from decimal import Decimal
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Pricing rates per million tokens
PRICING = {
    "gemini-3.5-flash-lite": {"input": Decimal("0.075"), "output": Decimal("0.30")},
    "gemini-3.5-flash": {"input": Decimal("0.15"), "output": Decimal("0.60")},
    "gpt-4o-mini": {"input": Decimal("0.15"), "output": Decimal("0.60")},
    "gpt-4o": {"input": Decimal("2.50"), "output": Decimal("10.00")},
}


def normalize_answer(s: str) -> str:
    """Lower text and remove punctuation, articles and extra whitespace."""
    s = s.lower()
    # remove punctuation
    s = re.sub(r"[^\w\s]", "", s)
    return " ".join(s.split())


def compute_f1(prediction: str, ground_truth: str) -> float:
    pred_tokens = normalize_answer(prediction).split()
    gold_tokens = normalize_answer(ground_truth).split()
    if not pred_tokens or not gold_tokens:
        return 1.0 if pred_tokens == gold_tokens else 0.0
    common = set(pred_tokens) & set(gold_tokens)
    if not common:
        return 0.0
    precision = sum(
        min(pred_tokens.count(w), gold_tokens.count(w)) for w in common
    ) / len(pred_tokens)
    recall = sum(min(pred_tokens.count(w), gold_tokens.count(w)) for w in common) / len(
        gold_tokens
    )
    return (2 * precision * recall) / (precision + recall)


def grade_vmlu(model_output: str, ground_truth: str) -> tuple[bool, str]:
    """Extract answer choice letter from model output and compare with ground truth."""
    gt = ground_truth.strip().upper()
    # Check for explicit patterns like 'Đáp án: A', 'Chọn: B', 'Đáp án đúng là C'
    matches = list(
        re.finditer(
            r"(?:đáp án(?: đúng)?(?: là)?|chọn)\s*[:：]?\s*[\*\"\']?([A-D])\b",
            model_output,
            re.IGNORECASE,
        )
    )
    if matches:
        extracted = matches[-1].group(1).upper()
        return extracted == gt, extracted
    # Check if the last isolated capital letter at the end of output matches
    end_match = re.search(r"\b([A-D])[\.\)]?\s*$", model_output.strip())
    if end_match:
        extracted = end_match.group(1).upper()
        return extracted == gt, extracted
    return False, "NONE"


def grade_viquad(
    model_output: str, gold_answers: list[str], is_impossible: bool
) -> tuple[bool, float]:
    """Grade reading comprehension with Exact Match (EM) and Token F1."""
    if is_impossible:
        norm = normalize_answer(model_output)
        passed = any(
            kw in norm
            for kw in [
                "không có thông tin",
                "không thể trả lời",
                "không đề cập",
                "không rõ",
            ]
        )
        return passed, 1.0 if passed else 0.0
    if not gold_answers:
        return False, 0.0
    best_f1 = 0.0
    for gold in gold_answers:
        f1 = compute_f1(model_output, gold)
        best_f1 = max(best_f1, f1)
    # Qualify as pass if F1 >= 0.5 or substring containment
    passed = best_f1 >= 0.5 or any(
        normalize_answer(g) in normalize_answer(model_output) for g in gold_answers
    )
    return passed, best_f1


def call_llm(
    prompt: str, provider: str, model: str, api_key: str, max_tokens: int = 256
) -> dict:
    started = time.perf_counter()
    if provider == "gemini":
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    else:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    res = requests.post(
        url,
        headers=headers,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.0,
        },
        timeout=30,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    if res.status_code != 200:
        return {"success": False, "error": res.text, "duration_ms": elapsed_ms}

    data = res.json()
    choice = data["choices"][0]["message"]["content"] or ""
    usage = data.get("usage", {})
    in_tok = usage.get("prompt_tokens", 0)
    out_tok = usage.get("completion_tokens", 0)

    # Cost calculation
    rates = PRICING.get(model, {"input": Decimal("0.10"), "output": Decimal("0.40")})
    cost_usd = (
        Decimal(in_tok) * rates["input"] + Decimal(out_tok) * rates["output"]
    ) / Decimal(1_000_000)

    return {
        "success": True,
        "text": choice.strip(),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": float(cost_usd),
        "duration_ms": elapsed_ms,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate on Real Benchmark Dataset")
    parser.add_argument("--dataset", default="data/benchmarks/real_benchmark_50.json")
    parser.add_argument(
        "--limit", type=int, default=10, help="Number of questions to test"
    )
    parser.add_argument("--provider", default="gemini", choices=["gemini", "openai"])
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    args = parser.parse_args()

    # Read API key from .env
    from app.config import Settings

    settings = Settings()

    if args.provider == "gemini":
        key = settings.gemini_api_key.get_secret_value()
        if not key:
            print("ERROR: GEMINI_API_KEY is not set in .env")
            return
    else:
        key = settings.openai_api_key.get_secret_value()
        if not key:
            print("ERROR: OPENAI_API_KEY is not set in .env")
            return

    ds_path = ROOT / args.dataset
    if not ds_path.exists():
        print(f"ERROR: Dataset {ds_path} does not exist.")
        return

    with open(ds_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    samples = data.get("samples", [])[: args.limit]
    print(
        f"=== Evaluating {len(samples)} Real Benchmark Samples with {args.provider.upper()} ({args.model}) ==="
    )

    passed_count = 0
    total_tokens = 0
    total_cost = 0.0
    latencies = []

    for i, s in enumerate(samples):
        task_id = s["task_id"]
        domain = s["domain"]
        prompt = s["formatted_prompt"]
        gt = s["ground_truth"]

        result = call_llm(prompt, args.provider, args.model, key)
        if not result["success"]:
            print(f"[{i + 1}/{len(samples)}] {task_id} -> ERROR: {result.get('error')}")
            continue

        pred_text = result["text"]
        duration = result["duration_ms"]
        latencies.append(duration)
        tokens = result["input_tokens"] + result["output_tokens"]
        total_tokens += tokens
        total_cost += result["cost_usd"]

        if s["grader_type"] == "mcq_letter":
            passed, pred_letter = grade_vmlu(pred_text, gt)
            detail = f"Gold={gt} | Pred={pred_letter} | Line: {pred_text.splitlines()[-1] if pred_text else ''}"
        else:
            passed, f1 = grade_viquad(pred_text, gt, s.get("is_impossible", False))
            detail = f"F1={f1:.2f} | Gold={gt[:1]} | Output: {pred_text[:50]}"

        if passed:
            passed_count += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"

        print(
            f"[{i + 1}/{len(samples)}] {task_id} ({domain}) -> {status_str} in {duration:.0f}ms | {detail}"
        )

    pass_rate = (passed_count / len(samples)) * 100 if samples else 0.0
    p50_lat = sorted(latencies)[len(latencies) // 2] if latencies else 0.0

    print("\n" + "=" * 50)
    print(f"EVALUATION SUMMARY ({args.model}):")
    print(f"- Total Evaluated: {len(samples)} real samples")
    print(f"- Pass Rate (Accuracy): {pass_rate:.1f}% ({passed_count}/{len(samples)})")
    print(f"- P50 Latency: {p50_lat:.1f} ms")
    print(f"- Total Tokens: {total_tokens:,}")
    print(f"- Total Cost: ${total_cost:.5f} USD")
    print("=" * 50)


if __name__ == "__main__":
    main()
