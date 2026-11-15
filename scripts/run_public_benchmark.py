"""Run a bounded live paired benchmark through the real orchestrator.

This is an engineering pilot, not a research-quality claim. It keeps the
benchmark database isolated and reports deterministic scores where available.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.cli import migrate
from app.composition import Container
from app.config import Settings
from app.contracts.dtos import ChatRequest, Principal
from app.evaluation.graders import grade_extractive_qa


ROOT = Path(__file__).resolve().parents[1]


def _number(text: str) -> str | None:
    matches = re.findall(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    return matches[-1] if matches else None


def _normalize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def _f1(prediction: str, gold: str) -> float:
    pred = _normalize(prediction)
    ref = _normalize(gold)
    if not pred or not ref:
        return float(pred == ref)
    common = sum(min(pred.count(token), ref.count(token)) for token in set(pred) & set(ref))
    if not common:
        return 0.0
    precision = common / len(pred)
    recall = common / len(ref)
    return 2 * precision * recall / (precision + recall)


def _load_cases(data_dir: Path, names: list[str], limit: int) -> list[dict]:
    cases: list[dict] = []
    if "gsm8k" in names:
        rows = json.loads((data_dir / "router-pilot-v1/gsm8k.json").read_text())[:limit]
        cases.extend(
            {
                "dataset": "GSM8K",
                "id": f"gsm8k-{i}",
                "prompt": f"Solve the problem. Give the final numeric answer clearly.\n\n{row['question']}",
                "gold": row["answer"].split("####")[-1].strip(),
                "metric": "exact_numeric",
            }
            for i, row in enumerate(rows)
        )
    if "aya" in names:
        rows = json.loads((data_dir / "router-pilot-v1/aya.json").read_text())[:limit]
        cases.extend(
            {
                "dataset": "Aya",
                "id": f"aya-{i}",
                "prompt": row["inputs"],
                "gold": row["targets"],
                "metric": "judge_pending",
            }
            for i, row in enumerate(rows)
        )
    if "vmlu" in names or "viquad" in names:
        payload = json.loads(
            (data_dir / "real-benchmarks/real_benchmark_50.json").read_text()
        )
        for row in payload["samples"]:
            dataset = "VMLU" if row["grader_type"] == "mcq_letter" else "UIT-ViQuAD 2.0"
            key = "vmlu" if dataset == "VMLU" else "viquad"
            if key not in names:
                continue
            cases.append(
                {
                    "dataset": dataset,
                    "id": row["task_id"],
                    "prompt": row["formatted_prompt"],
                    "gold": row["ground_truth"],
                    "metric": "mcq_accuracy" if key == "vmlu" else "em_f1",
                    "is_impossible": row.get("is_impossible", False),
                }
            )
            if sum(1 for item in cases if item["dataset"] == dataset) >= limit:
                continue
    selected: list[dict] = []
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["dataset"]] = counts.get(case["dataset"], 0) + 1
        if counts[case["dataset"]] <= limit:
            selected.append(case)
    return selected


def _grade(case: dict, prediction: str) -> dict:
    if case["metric"] == "exact_numeric":
        value = _number(prediction)
        return {"passed": value == case["gold"], "score": float(value == case["gold"]), "detail": value}
    if case["metric"] == "mcq_accuracy":
        found = re.findall(r"(?:Đáp án|answer|choice)\s*[:：]?\s*([A-D])", prediction, re.I)
        found += re.findall(r"\b([A-D])\s*[.)]?\s*$", prediction, re.I)
        value = found[-1].upper() if found else "NONE"
        return {"passed": value == case["gold"].upper(), "score": float(value == case["gold"].upper()), "detail": value}
    if case["metric"] == "em_f1":
        golds = case["gold"] if isinstance(case["gold"], list) else [case["gold"]]
        qa = grade_extractive_qa(
            prediction=prediction,
            gold_answers=tuple(golds),
            is_impossible=case.get("is_impossible", False),
        )
        return {
            "passed": qa.passed,
            "score": qa.token_f1,
            "detail": {"em": qa.exact_match, "f1": qa.token_f1},
        }
    return {"passed": None, "score": None, "detail": "blind judge pending"}


async def _run(args: argparse.Namespace) -> Path:
    cases = _load_cases(ROOT / "benchmark/data", args.datasets, args.limit)
    if not cases:
        raise SystemExit("Không tìm thấy dữ liệu benchmark đã chuẩn bị.")

    stamp = date.today().isoformat()
    run_dir = (
        Path(args.run_dir).resolve()
        if args.run_dir
        else ROOT / "benchmark/data/router-pilot-v1/run" / f"public-{stamp}-{int(time.time())}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "benchmark.db"
    # Alembic owns its event loop, so run migrations outside this async loop.
    await asyncio.to_thread(migrate, db_path)
    settings = Settings().model_copy(
        update={
            "database_path": db_path,
            "model_catalog_path": ROOT / "config/models.json",
            "provider_mode": "live",
            "research_live_enabled": True,
        }
    )
    container = Container(settings)
    user = await container.auth.create_user(
        f"benchmark-{hashlib.sha256((str(run_dir) + str(time.time())).encode()).hexdigest()[:10]}",
        "benchmark-isolated-user",
    )
    partial_path = run_dir / "results.partial.json"
    rows: list[dict] = []
    if args.run_dir and partial_path.exists():
        rows = json.loads(partial_path.read_text(encoding="utf-8")).get("rows", [])
        retry_keys = {(row["case_id"], row["arm"]) for row in rows if "error" in row}
        rows = [row for row in rows if (row["case_id"], row["arm"]) not in retry_keys]
        case_by_id = {case["id"]: case for case in cases}
        for row in rows:
            if "prediction" in row and row["case_id"] in case_by_id:
                row["grade"] = _grade(case_by_id[row["case_id"]], row["prediction"])
        print(f"Resume: giữ {len(rows)} kết quả thành công, thử lại {len(retry_keys)} lỗi")
    checkpoint = run_dir / "results.partial.json"
    spent = sum(
        (Decimal(row["cost_usd"]) for row in rows if row.get("cost_usd") not in (None, "None", "null")),
        Decimal("0"),
    )
    try:
        for case in cases:
            for mode in ("baseline", "optimized"):
                if any(row.get("case_id") == case["id"] and row.get("arm") == mode for row in rows):
                    continue
                session = await container.sessions.create(user, f"benchmark:{case['id']}:{mode}")
                started = time.perf_counter()
                try:
                    if spent + args.max_usd > args.project_cap_usd:
                        raise RuntimeError(
                            f"project benchmark cap reached: {spent} + {args.max_usd} > {args.project_cap_usd}"
                        )
                    response = await asyncio.wait_for(container.orchestrator.execute(
                        user,
                        ChatRequest(
                            session_id=session.id,
                            client_request_id=f"benchmark-{case['id']}-{mode}",
                            message=case["prompt"],
                            mode=mode,
                            constraints={
                                "max_total_usd": str(args.max_usd),
                                "deadline_ms": args.deadline_ms,
                            },
                        ),
                        namespace="eval",
                    ), timeout=args.request_timeout)
                    prediction = response.response.content
                    grade = _grade(case, prediction)
                    rows.append(
                        {
                            "dataset": case["dataset"],
                            "case_id": case["id"],
                            "arm": mode,
                            "prediction": prediction,
                            "grade": grade,
                            "cost_usd": str(response.cost.serving_usd),
                            "latency_ms": response.timing.e2e_ms,
                            "route": response.route.model_dump(mode="json"),
                            "execution_source": response.execution_source,
                        }
                    )
                    if response.cost.serving_usd is not None:
                        spent += response.cost.serving_usd
                    checkpoint.write_text(
                        json.dumps({"generated": stamp, "limit_per_dataset": args.limit, "rows": rows}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    print(f"{case['dataset']} {case['id']} {mode}: done")
                except Exception as exc:
                    rows.append(
                        {
                            "dataset": case["dataset"],
                            "case_id": case["id"],
                            "arm": mode,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    checkpoint.write_text(
                        json.dumps({"generated": stamp, "limit_per_dataset": args.limit, "rows": rows}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    print(f"{case['dataset']} {case['id']} {mode}: ERROR ({type(exc).__name__})")
                finally:
                    await container.sessions.purge(user, session.id)
        raw = {"generated": stamp, "limit_per_dataset": args.limit, "rows": rows}
        (run_dir / "results.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        report = _report(raw, run_dir)
        output = ROOT / "benchmark/reports" / f"public-benchmark-{stamp}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        return output
    finally:
        await container.db.close()


def _report(raw: dict, run_dir: Path) -> str:
    rows = raw["rows"]
    lines = [
        "# Báo cáo benchmark public — pilot live",
        "",
        f"- Ngày: `{raw['generated']}`",
        "- Trạng thái: `ENGINEERING_PILOT / CHƯA ĐỦ BẰNG CHỨNG NGHIÊN CỨU`",
        f"- Database cô lập: `{run_dir}`",
        f"- Số mẫu mỗi bộ: `{raw['limit_per_dataset']}`; mỗi mẫu chạy `baseline` và `optimized`",
        "",
        "> Đây là kết quả chạy qua OpenRouter → Orchestrator thật. Không được xem là bằng chứng ML Router nếu route optimized báo fallback hoặc `ml_executed=false`.",
        "",
        "| Dataset | Arm | N | Điểm tự động | Cost USD | Latency TB (ms) | Fallback optimized |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset in sorted({row["dataset"] for row in rows}):
        for arm in ("baseline", "optimized"):
            subset = [r for r in rows if r["dataset"] == dataset and r["arm"] == arm]
            completed = [r for r in subset if "grade" in r]
            scores = [r["grade"]["score"] for r in completed if r["grade"]["score"] is not None]
            costs = [Decimal(r["cost_usd"]) for r in completed if r["cost_usd"] not in ("None", "null")]
            latencies = [r["latency_ms"] for r in completed]
            fallback = sum(1 for r in completed if arm == "optimized" and (not r["route"].get("ml_executed", False) or r["route"].get("fallback_used", False)))
            if dataset == "UIT-ViQuAD 2.0":
                em_values = [float(r["grade"]["detail"]["em"]) for r in completed]
                f1_values = [float(r["grade"]["detail"]["f1"]) for r in completed]
                score = "n/a" if not completed else f"EM {sum(em_values)/len(em_values):.3f}; F1 {sum(f1_values)/len(f1_values):.3f}"
            else:
                score = "judge pending" if not scores else f"{sum(scores)/len(scores):.3f}"
            latency = "n/a" if not latencies else f"{sum(latencies)/len(latencies):.1f}"
            lines.append(f"| {dataset} | {arm} | {len(completed)}/{len(subset)} | {score} | {sum(costs):.7f} | {latency} | {fallback} |")
    lines += [
        "",
        "## Cách chấm",
        "",
        "- GSM8K: so khớp số cuối với đáp án sau `####`.",
        "- VMLU: độ chính xác chữ cái A–D.",
        "- UIT‑ViQuAD 2.0: EM và token F1; giữ các đáp án gold chính thức.",
        "- Aya: đã chạy sinh câu trả lời nhưng chưa chấm điểm; cần blind judge với rubric đóng băng, không dùng exact-match với câu trả lời tự do.",
        "- MBPP: chưa chạy trong pilot này; cần chấm unit test trong sandbox Docker riêng.",
        "",
        "## Kết luận an toàn",
        "",
        "Nếu optimized có fallback, kết quả chỉ cho biết hành vi fallback của hệ thống, không chứng minh chất lượng ML Router hay savings của optimizer. Cần ML artifact hợp lệ và chạy đủ cỡ mẫu trước khi báo cáo nghiên cứu.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", default=["gsm8k", "aya", "vmlu", "viquad"], choices=["gsm8k", "aya", "vmlu", "viquad"])
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--max-usd", type=Decimal, default=Decimal("0.05"))
    parser.add_argument("--deadline-ms", type=int, default=120000)
    parser.add_argument("--request-timeout", type=float, default=150.0)
    parser.add_argument("--project-cap-usd", type=Decimal, default=Decimal("2.00"))
    parser.add_argument("--run-dir", type=Path, default=None, help="Resume an existing benchmark run directory")
    parser.add_argument("--report-only", action="store_true", help="Re-grade stored predictions and regenerate Markdown without API calls")
    args = parser.parse_args()
    if args.report_only:
        if args.run_dir is None:
            parser.error("--report-only requires --run-dir")
        cases = _load_cases(ROOT / "benchmark/data", args.datasets, args.limit)
        result_path = args.run_dir / "results.json"
        raw = json.loads(result_path.read_text(encoding="utf-8"))
        if args.run_dir.name.startswith("public-"):
            raw["generated"] = "-".join(args.run_dir.name.split("-")[1:4])
        case_by_id = {case["id"]: case for case in cases}
        for row in raw["rows"]:
            if "prediction" in row and row["case_id"] in case_by_id:
                row["grade"] = _grade(case_by_id[row["case_id"]], row["prediction"])
        result_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        output = ROOT / "benchmark/reports" / f"public-benchmark-{date.today().isoformat()}.md"
        output.write_text(_report(raw, args.run_dir), encoding="utf-8")
        print(f"Đã cập nhật report không gọi API: {output}")
        return
    output = asyncio.run(_run(args))
    print(f"Đã xuất báo cáo: {output}")


if __name__ == "__main__":
    main()
