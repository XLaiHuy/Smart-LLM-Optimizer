"""Pause the old collector at its existing pre-dispatch fence, never kill it.

Maintenance markers explicitly have no call/reservation ID. Cleanup requires the
worker lock to be free and the operation ledger to contain no uncertain calls.
Existing dispatch markers are never modified or removed by this tool.
"""

import argparse
import fcntl
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from app.contracts.dtos import Message
from app.contracts.training import TrainingManifest
from app.routing.ml.pipeline import cache_key


def main(args):
    directory = args.directory
    job_id = json.loads((directory / "job.json").read_text())["job_id"]
    run = directory / "runs" / job_id
    journal = directory / args.journal_name
    cache = directory / "runs/cache"
    if args.cleanup:
        with (directory / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with sqlite3.connect("file:/app/runtime-db/smartllm.db?mode=ro", uri=True) as db:
                records = [json.loads(r[0]) for r in db.execute(
                    "SELECT record_json FROM usage_records WHERE operation_id = ?", (job_id,)
                )]
            if any(r["cost"].get("serving_usd") is None for r in records):
                raise ValueError("Uncertain operation call: keep all fences and stop")
            for name in json.loads(journal.read_text())["markers"]:
                path = cache / name
                if not path.exists() and path.with_name(name.replace(".dispatch.json", ".json")).exists():
                    continue  # A lane had already admitted this call and completed it.
                doc = json.loads(path.read_text())
                if doc != {"maintenance_pause": "parallel-switch-v1", "operation_id": job_id}:
                    raise ValueError("Marker changed: do not remove it")
                path.unlink()
            print(json.dumps({"cleaned": True, "known_calls": len(records)}), flush=True)
        return
    if journal.exists() and not args.wait_until_paused:
        raise ValueError("Maintenance already requested; inspect the journal")
    recorded = json.loads(journal.read_text())["markers"] if journal.exists() else []
    manifest = TrainingManifest.model_validate_json((run / "manifest.json").read_bytes())
    for _ in range(80):
        if args.wait_until_paused:
            with (directory / "worker.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    print(json.dumps({"worker_stopped": True}), flush=True)
                    return
        paths = sorted((run / "prepared").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if paths:
            doc = json.loads(paths[0].read_text())
            messages = tuple(Message.model_validate(m) for m in doc["messages"])
            created = []
            for config in manifest.configurations:
                key = cache_key(manifest, config.config_id, messages)
                if (cache / f"{key}.json").exists():
                    continue
                marker = cache / f"{key}.dispatch.json"
                try:
                    with marker.open("x") as handle:
                        json.dump({"maintenance_pause": "parallel-switch-v1", "operation_id": job_id}, handle)
                    created.append(marker.name)
                except FileExistsError:
                    pass  # Real in-flight dispatch fence belongs to the worker.
            if created:
                recorded.extend(n for n in created if n not in recorded)
                journal.write_text(json.dumps({"job_id": job_id, "markers": recorded,
                    "task_hash": hashlib.sha256(doc["task_id"].encode()).hexdigest(),
                    "reason": "Pre-dispatch maintenance fence; no provider call or reservation created"}, indent=2))
                print(json.dumps({"pause_requested": True, "markers": len(created)}), flush=True)
                if not args.wait_until_paused:
                    return
        time.sleep(.25)
    raise ValueError("No safe boundary found; worker was left running")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("/app/data/router-task-family-v1-20261027"))
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--wait-until-paused", action="store_true")
    parser.add_argument("--journal-name", choices=("parallel-switch-maintenance.json", "stop-target-maintenance.json"), default="parallel-switch-maintenance.json")
    main(parser.parse_args())
