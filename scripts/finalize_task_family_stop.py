"""Wait for the 450-question stop, reconcile and diagnose DEV. No paid imports/calls."""

import argparse
import fcntl
import hashlib
import json
import sqlite3
import time
from decimal import Decimal
from pathlib import Path

from app.routing.family_postcollection import diagnose


def main(
    directory: Path,
    wait: bool,
    allow_failed_stop: bool = False,
    output_name: str = "stopped-analysis",
):
    with (directory / "postcollection.lock").open("a") as own_lock:
        fcntl.flock(own_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output = directory / output_name
        if (output / "report.json").exists():
            print("Analysis already saved; no repeated actions", flush=True)
            return
        while True:
            status = json.loads((directory / "status.json").read_text())
            if status["status"] != "running" and status["completed"] >= 450:
                break
            if status["status"] in ("failed", "interrupted"):
                if allow_failed_stop:
                    break
                raise ValueError(
                    "Worker stopped before target; do not resume or dispatch"
                )
            if not wait:
                raise ValueError("450-question stop has not completed")
            time.sleep(5)
        if not allow_failed_stop and (
            status["completed"] != 450 or status["error_code"] != "USER_REQUESTED_PAUSE"
        ):
            raise ValueError("Unexpected stop boundary; review without further calls")
        # Status can be written shortly before the worker releases its lock.
        with (directory / "worker.lock").open("a") as worker_lock:
            fcntl.flock(worker_lock, fcntl.LOCK_EX)
            job = json.loads((directory / "job.json").read_text())["job_id"]
            run = directory / "runs" / job
            raw = (run / "dev-observations.json").read_bytes()
            rows = json.loads(raw)
            if len(rows) != status["completed"] or len(rows) > 450:
                raise ValueError("Checkpoint count does not match stop")
            manifest = json.loads((run / "manifest.json").read_text())
            report = diagnose(
                rows, {c["config_id"] for c in manifest["configurations"]}
            )
            with sqlite3.connect(
                "file:/app/runtime-db/smartllm.db?mode=ro", uri=True
            ) as db:
                calls = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT record_json FROM usage_records WHERE operation_id=?",
                        (job,),
                    )
                ]
                reservations = list(
                    db.execute(
                        "SELECT status,reserved_usd FROM budget_reservations WHERE request_id=?",
                        (job,),
                    )
                )
            unresolved = any(
                c["cost"].get("serving_usd") is None for c in calls
            ) or any(
                r[0] in ("reserved", "dispatched", "unresolved") for r in reservations
            )
            if unresolved and not allow_failed_stop:
                raise ValueError("Unresolved billing retained: stop and ask for review")
            report.update(
                job_id=job,
                known_api_calls=sum(
                    c["cost"].get("serving_usd") is not None for c in calls
                ),
                total_api_calls=len(calls),
                unknown_api_calls=sum(
                    c["cost"].get("serving_usd") is None for c in calls
                ),
                all_costs_resolved=not unresolved,
                unresolved_reserve_usd=str(
                    sum(
                        (
                            Decimal(r[1])
                            for r in reservations
                            if r[0] in ("reserved", "dispatched", "unresolved")
                        ),
                        Decimal(0),
                    )
                ),
                stop_reason=status["error_code"],
                requested_stop=450,
                known_usd=str(
                    sum(
                        (
                            Decimal(c["cost"]["serving_usd"])
                            for c in calls
                            if c["cost"].get("serving_usd") is not None
                        ),
                        Decimal(0),
                    )
                ),
                dev_file_sha256=hashlib.sha256(raw).hexdigest(),
                source_sha256=manifest["source"]["sha256"],
                stop_confirmed=True,
                next_step="Retain frozen splits. Complete missing DEV and independent HOLDOUT only after Huy authorizes collection to resume. No partial-data live qualification.",
            )
            output.mkdir(exist_ok=True)
            temp = output / "report.tmp"
            temp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            temp.replace(output / "report.json")
            (output / "README.md").write_text(
                f"# Đã dừng ở {len(rows)}/900 câu; mốc yêu cầu 450\n\nreport.json phân tích lỗi trên DEV; không đọc HOLDOUT.\n"
                f"Chi phí đã đối soát hết: {not unresolved}. Khoản chưa rõ vẫn giữ nguyên trong ledger, không gọi lại.\n"
                "Chưa train/hiệu chỉnh: cần đủ 600 DEV đúng split đã đóng băng. Chưa bật ngưỡng live mới.\n"
                "Luồng đã chuẩn bị: calibrate_task_families.py → evaluate_task_family_holdout.py → pilot có kiểm soát → package → triển khai có backup.\n"
                "Không chạy bước tiếp theo hoặc thu API thêm khi chưa có chỉ đạo mới.\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "stop_confirmed": True,
                        "completed": len(rows),
                        "report": str(output / "report.json"),
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
    parser.add_argument("--wait", action="store_true")
    parser.add_argument(
        "--output-name",
        choices=("stopped-analysis", "stopped-analysis-after-ten"),
        default="stopped-analysis",
    )
    parser.add_argument(
        "--allow-failed-stop",
        action="store_true",
        help="Read-only diagnosis of a stopped failed job; never resolves billing or resumes calls",
    )
    args = parser.parse_args()
    main(args.directory, args.wait, args.allow_failed_stop, args.output_name)
