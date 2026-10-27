"""Explicit paid paired pilot after frozen HOLDOUT passes; never auto-promotes.

Runs the actual HTTP/DB/orchestrator pipeline in process, isolated eval namespace.
Persist-before-dispatch markers fence unknown outcomes. Cap: 0.50 USD including
every call, escalation and unresolved reserve; account/project caps still apply.
"""

import argparse
import asyncio
import fcntl
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from time import perf_counter

import httpx
from app.config import Settings
from app.contracts.dtos import ChatRequest, Principal
from app.contracts.errors import AppError
from app.contracts.training import TrainingCorpus
from app.main import create_app
from app.memory.memory_manager import NoOpMemoryManager
from app.routing.ml.graders import grade
from app.routing.ml.pipeline import atomic_text
from app.routing.family_pilot import checkpoint_spend
from app.routing.task_groups import TaskGroupPolicy, content_hash
from app.storage.models import User
from sqlalchemy import select


async def run(args):
    directory = args.directory
    with (directory / "pilot-worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        frozen = json.loads((directory / "calibration/frozen.json").read_text())
        raw = (directory / "calibration/candidate.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != frozen["candidate_file_sha256"]:
            raise ValueError("Frozen candidate mismatch")
        bundle = json.loads(raw)
        holdout = json.loads(
            (directory / "calibration/holdout-report.json").read_text()
        )
        eligible = {f for f, r in holdout["reports"].items() if r["offline_pass"]}
        if not eligible or holdout["candidate_sha256"] != content_hash(bundle):
            raise ValueError("Offline HOLDOUT pass required before paid pilot")
        collection = json.loads((directory / "status.json").read_text())
        if collection["status"] != "succeeded" or collection["completed"] != 900:
            raise ValueError("Collection must finish before pilot")
        corpus = TrainingCorpus.model_validate_json(
            (directory / "corpus.json").read_bytes()
        )
        rows = [
            r
            for family in sorted(eligible)
            for r in sorted(
                (
                    r
                    for r in corpus.samples
                    if r.domain == family and r.split == "holdout"
                ),
                key=lambda r: hashlib.sha256(r.task_id.encode()).hexdigest(),
            )[:20]
        ]
        output = directory / "serving-pilot"
        output.mkdir(exist_ok=True)
        if (output / "report.json").exists():
            raise ValueError("Pilot already finalized; do not repeat")
        settings = Settings()
        if (
            not args.live
            or settings.provider_mode != "live"
            or settings.app_env == "test"
            or not settings.research_live_enabled
        ):
            raise ValueError("Explicit live research gate required")
        app = create_app(settings)
        c = app.state.container
        if c.ml_router.hash != frozen["ml_artifact_hash"]:
            raise ValueError("Serving ML changed")
        async with c.db.sessions() as db:
            owner = await db.scalar(
                select(User).where(User.role == "admin").order_by(User.id)
            )
            if owner is None:
                raise ValueError("Existing admin required")
            user = Principal(
                id=owner.id,
                username=owner.username,
                role="admin",
                quota_usd=Decimal(owner.quota_usd),
            )
        old_policy = c.orchestrator.group_policy
        candidate = TaskGroupPolicy(
            Path("__absent_offline_pilot_policy__"), c.ml_router
        )
        # Candidate execution is explicitly restricted to this in-process eval
        # pilot. The live server cannot load it before final evidence passes.
        candidate.bundle = bundle
        c.orchestrator.memory = NoOpMemoryManager()
        c.orchestrator.outcomes = None

        @app.post("/internal-family-pilot/{variant}")
        async def chat(variant: str, body: ChatRequest):
            if variant not in ("prior", "policy"):
                raise AppError("NOT_FOUND", 404, "Unknown variant")
            c.orchestrator.group_policy = (
                old_policy if variant == "prior" else candidate
            )
            return await c.orchestrator.execute(user, body, namespace="eval")

        # Reconcile the entire directory before ANY new dispatch, including a
        # marker left later in iteration order. Never count replayed files twice.
        spent = checkpoint_spend(output, content_hash(bundle))
        pairs = []
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://family-pilot",
                timeout=130,
            ) as client:
                for sample in rows:
                    pair = {
                        "pair_id": sample.task_id,
                        "family": sample.domain,
                        "critical_regression": False,
                    }
                    order = (
                        ("prior", "policy")
                        if int(
                            hashlib.sha256(sample.task_id.encode()).hexdigest()[:2], 16
                        )
                        % 2
                        else ("policy", "prior")
                    )
                    for variant in order:
                        prefix = hashlib.sha256(
                            (sample.task_id + variant).encode()
                        ).hexdigest()
                        final = output / (prefix + ".result.json")
                        marker = output / (prefix + ".dispatch.json")
                        if final.exists():
                            record = json.loads(final.read_text())
                        else:
                            if marker.exists():
                                raise ValueError(
                                    "Unknown previous pilot dispatch; stop without replay"
                                )
                            if spent + Decimal(".01") > Decimal(
                                ".50"
                            ) or spent + Decimal(collection["spent_usd"]) + Decimal(
                                ".01"
                            ) > Decimal(2):
                                raise ValueError("Pilot/additional budget exhausted")
                            session = await c.sessions.create(
                                user, "Family paired serving pilot"
                            )
                            body = ChatRequest(
                                session_id=session.id,
                                client_request_id="family-pilot-" + prefix,
                                message=sample.messages[0].content,
                                mode="optimized",
                                constraints={
                                    "max_total_usd": ".01",
                                    "deadline_ms": 120000,
                                },
                            )
                            atomic_text(marker, body.model_dump_json(indent=2))
                            start = perf_counter()
                            response = await client.post(
                                "/internal-family-pilot/" + variant,
                                json=body.model_dump(mode="json"),
                            )
                            elapsed = (perf_counter() - start) * 1000
                            data = response.json()
                            rid = (
                                data["request_id"]
                                if response.status_code == 200
                                else data.get("error", {}).get("request_id")
                            )
                            if not rid:
                                raise ValueError(
                                    "Pilot failed without known operation ID; keep dispatch fence"
                                )
                            calls = await c.metering.records(rid)
                            if not calls or any(
                                call.cost.serving_usd is None
                                or call.cost.status == "unknown"
                                or call.dispatch_state == "unknown"
                                for call in calls
                            ):
                                raise ValueError(
                                    "New pilot cost/dispatch unresolved; stop all paid calls"
                                )
                            usd = sum(
                                (call.cost.serving_usd for call in calls), Decimal(0)
                            )
                            assert sample.grading is not None
                            passed = (
                                response.status_code == 200
                                and grade(
                                    sample.grading,
                                    data["response"]["content"],
                                    sample.gold,
                                ).qualified
                            )
                            record = {
                                "candidate_sha256": content_hash(bundle),
                                "usd": str(usd),
                                "ms": elapsed,
                                "pass": passed,
                                "http_status": response.status_code,
                                "response": data,
                                "calls": [
                                    call.model_dump(mode="json") for call in calls
                                ],
                            }
                            atomic_text(final, json.dumps(record, ensure_ascii=False))
                            marker.unlink()
                            spent += usd
                        if variant == "policy" and (
                            record["http_status"] != 200
                            or record["response"].get("route", {}).get("ml_executed")
                            is not True
                            or record["response"]
                            .get("route", {})
                            .get("attention_executed")
                            is not True
                        ):
                            raise ValueError(
                                "Pilot has no verified ML+Attention execution; stop paid calls"
                            )
                        pair[variant + "_usd"] = record["usd"]
                        pair[variant + "_ms"] = record["ms"]
                        pair[variant + "_pass"] = record["pass"]
                        if variant == "policy":
                            route = record["response"]["route"]
                            pair["profile_applied"] = (
                                route.get("group_profile_applied") is True
                                and route.get("task_family") == sample.domain
                            )
                    pair["critical_regression"] = (
                        sample.critical
                        and pair["prior_pass"]
                        and not pair["policy_pass"]
                    )
                    pairs.append(pair)
                    atomic_text(
                        output / "checkpoint.json",
                        json.dumps({"pairs": pairs, "spent_usd": str(spent)}, indent=2),
                    )
            from statistics import median

            families = {}
            for family in sorted(eligible):
                subset = [p for p in pairs if p["family"] == family]
                ratio = median(p["policy_ms"] for p in subset) / median(
                    p["prior_ms"] for p in subset
                )
                profile = bundle["profiles"][family]
                payload = {
                    k: v
                    for k, v in profile.items()
                    if k not in ("evidence_path", "evidence_sha256")
                }
                families[family] = {
                    "pairs": subset,
                    "all_costs_resolved": True,
                    "profile_sha256": content_hash(payload),
                    "classifier_sha256": content_hash(bundle["classifier"]),
                    "all_in_p50_ratio": ratio,
                    "passed": len(subset) >= 20
                    and any(p["profile_applied"] for p in subset)
                    and ratio <= 1.10
                    and not any(
                        p["prior_pass"] and not p["policy_pass"] for p in subset
                    )
                    and sum(Decimal(p["policy_usd"]) for p in subset)
                    < sum(Decimal(p["prior_usd"]) for p in subset),
                }
            atomic_text(
                output / "report.json",
                json.dumps(
                    {
                        "families": families,
                        "spent_usd": str(spent),
                        "activation": False,
                        "measurement_scope": "HTTP ASGI + serving orchestrator/database; excludes external browser/proxy network",
                    },
                    indent=2,
                ),
            )
        finally:
            c.orchestrator.group_policy = old_policy
            if c.live:
                await c.live.close()
            await c.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("/app/data/router-task-family-v1-20261027"),
    )
    parser.add_argument("--live", action="store_true")
    asyncio.run(run(parser.parse_args()))
