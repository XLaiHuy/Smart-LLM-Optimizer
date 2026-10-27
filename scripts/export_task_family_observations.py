"""Export actual paired DEV responses; no providers, training or HOLDOUT reads."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from app.contracts.dtos import Message
from app.contracts.training import TrainingManifest
from app.routing.ml.pipeline import cache_key


def cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def run(directory):
    status = json.loads((directory / "status.json").read_text())
    if status["status"] == "running" or status["completed"] != 450:
        raise ValueError("Wait for the bounded 450-case stop")
    job_id = json.loads((directory / "job.json").read_text())["job_id"]
    run_dir = directory / "runs" / job_id
    manifest = TrainingManifest.model_validate_json(
        (run_dir / "manifest.json").read_bytes()
    )
    rows = json.loads((run_dir / "dev-observations.json").read_text())
    if len(rows) != 450 or any(r["split"] == "holdout" for r in rows):
        raise ValueError("Complete bounded DEV checkpoint required")
    output = directory / "stopped-analysis-after-ten"
    report = json.loads((output / "report.json").read_text())
    target = output / "prompt-response-model.csv"
    if target.exists():
        raise ValueError("Export already saved")
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        fields = [
            "task_id",
            "family",
            "split",
            "prompt",
            "response",
            "model",
            "config_id",
            "qualified",
            "input_tokens",
            "output_tokens",
            "usd",
            "provider_ms",
            "preparation_ms",
            "measurement",
        ]
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for row in rows:
            prepared = json.loads(
                (
                    run_dir
                    / "prepared"
                    / (hashlib.sha256(row["task_id"].encode()).hexdigest() + ".json")
                ).read_text()
            )
            messages = tuple(Message.model_validate(m) for m in row["messages"])
            for observation in row["observations"]:
                config_id = observation["config_id"]
                config = next(
                    c for c in manifest.configurations if c.config_id == config_id
                )
                key = cache_key(manifest, config_id, messages)
                cached = json.loads(
                    (directory / "runs/cache" / (key + ".json")).read_text()
                )
                if (
                    hashlib.sha256(cached["text"].encode()).hexdigest()
                    != observation["response_sha256"]
                ):
                    raise ValueError("Response cache/observation mismatch")
                writer.writerow(
                    {
                        k: cell(v)
                        for k, v in dict(
                            task_id=row["task_id"],
                            family=row["domain"],
                            split=row["split"],
                            prompt=prepared["original_messages"][0]["content"],
                            response=cached["text"],
                            model=config.model_id,
                            config_id=config_id,
                            qualified=observation["qualified"],
                            input_tokens=observation["input_tokens"],
                            output_tokens=observation["output_tokens"],
                            usd=observation["usd"],
                            provider_ms=observation["latency_ms"],
                            preparation_ms=prepared["prepare_ms"],
                            measurement="paired_provider_DEV_not_auto_route_or_E2E",
                        ).items()
                    }
                )
    lines = [
        "# Kết quả 450 câu DEV",
        "",
        "Đây là số liệu thăm dò DEV, chưa phải kiểm định HOLDOUT hoặc chứng nhận live.",
        "",
        "| Nhóm | Cấu hình | Đúng / đã đo |",
        "|---|---|---|",
    ]
    for key, metric in sorted(report["model_diagnostics"].items()):
        family, config = key.split("/", 1)
        lines.append(
            f"| {family} | {config} | {metric['correct']}/{metric['observed']} |"
        )
    lines += [
        "",
        f"Chi phí đã biết toàn job: {report['known_usd']} USD; dự phòng chưa đối soát: {report['unresolved_reserve_usd']} USD.",
        "",
        "CSV chứa 1.350 phản hồi thực tế (450 câu × 3 model), token và chi phí. Độ trễ là của provider và bước chuẩn bị; không gọi là latency toàn chat.",
        "Các ô có thể là công thức spreadsheet được thêm dấu nháy để mở CSV an toàn; bản gốc trong cache không bị đổi.",
        "",
        "Bước tiếp: giữ dữ liệu và đối soát lượt cũ; cần đủ 600 DEV và 300 HOLDOUT đúng protocol trước khi hiệu chỉnh/chứng nhận mới. Không tự thu thêm hoặc bật ngưỡng.",
    ]
    (output / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "rows": 1350,
                "csv": str(target),
                "trained": False,
                "serving_changed": False,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("/app/data/router-task-family-v1-20261027"),
    )
    args = parser.parse_args()
    run(args.directory)
