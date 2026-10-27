"""Explicitly bounded serving-path pilot; never changes the ordinary chat router.

Research-only candidate admission applies to this in-process instance. Every actual
generation still uses the production ledger, provider quota and durable history.
"""

import argparse
import asyncio
import json
from decimal import Decimal
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

import httpx
from app.config import Settings
from app.contracts.dtos import ChatRequest, Constraints, Principal
from app.routing.ml.graders import grade
from app.routing.ml.multi_training import MultiDataset
from app.routing.ml.pilot import timed_evaluate
from app.routing.ml.pipeline import atomic_text
from app.routing.ml.qualification import qualify
from app.routing.ml.service import MLRouterService
from app.routing.policies import PolicyRouter
from app.storage.models import User
from sqlalchemy import select


def validate_frozen_pilot_input(directory: Path, holdout: MultiDataset) -> None:
    """Spend only after the complete frozen quality study passes every offline gate."""
    from app.contracts.training import TrainingCorpus

    corpus = TrainingCorpus.model_validate_json(
        (directory / "corpus.json").read_text(encoding="utf-8")
    )
    planned = {r.task_id for r in corpus.samples if r.split == "holdout"}
    if {r.task_id for r in holdout.samples} != planned:
        raise ValueError("Complete frozen HOLDOUT required before paid serving pilot")
    missing_report = directory / "__missing_e2e_preflight__.json"
    if missing_report.exists():
        raise ValueError("Preflight requires an absent E2E report")
    result, _ = qualify(
        directory / "dev.json",
        directory / "holdout.json",
        directory / "artifact.json",
        directory / "baseline.json",
        missing_report,
        "automated offline preflight; not live approval",
    )
    missing_e2e = {
        "MEASURED_E2E_PILOT_REQUIRED",
        "E2E_ARTIFACT_HASH_MISMATCH",
        "E2E_LATENCY_GUARD_FAILED",
        "E2E_CRITICAL_REGRESSION",
    }
    failures = set(result["issues"]) - missing_e2e
    if failures:
        raise ValueError(
            "Offline qualification blocks paid pilot: " + ", ".join(sorted(failures))
        )


async def run(args):
    settings = Settings(
        adaptive_prompt_enabled=False,
        hybrid_context_enabled=False,
        memory_retrieval_enabled=False,
    )
    if (
        settings.app_env == "test"
        or not settings.research_live_enabled
        or settings.provider_mode != "live"
    ):
        raise ValueError("Explicit live research configuration required")
    if args.report.exists():
        raise ValueError("Report already exists; do not repeat a paid pilot")
    holdout = MultiDataset.model_validate_json(
        (args.directory / "holdout.json").read_text(encoding="utf-8")
    )
    validate_frozen_pilot_input(args.directory, holdout)
    attention_path, ml_path = (
        args.directory / "artifact.json",
        args.directory / "baseline.json",
    )
    # Stop before spending if the frozen replay already rejects quality/latency.
    replay = timed_evaluate(holdout, attention_path.read_text(encoding="utf-8"))
    if not replay["guardrails_with_routing_overhead"]:
        raise ValueError(
            "Frozen HOLDOUT already fails observed guardrails; no paid pilot dispatched"
        )
    from app.api.routes import principal as principal_dependency
    from app.main import create_app

    app = create_app(settings)
    container = app.state.container
    assert container.live and container.metering.catalog
    async with container.db.sessions() as db:
        user = await db.scalar(
            select(User).where(User.username == args.owner, User.role == "admin")
        )
        if not user:
            raise ValueError("Existing admin owner required")
        principal = Principal(
            id=user.id,
            username=user.username,
            role=user.role,
            quota_usd=Decimal(user.quota_usd),
        )
    app.dependency_overrides[principal_dependency] = lambda: principal

    @app.post("/internal-qualification/chat")
    async def evaluate_chat(body: ChatRequest):
        return await container.orchestrator.execute(principal, body, namespace="eval")

    rows = sorted(holdout.samples, key=lambda r: r.task_id)
    # Balanced predetermined cases, independent of observed model correctness.
    rows = [
        r
        for domain in sorted({r.domain for r in rows})
        for r in [x for x in rows if x.domain == domain][:6]
    ]
    if len(rows) != 12:
        raise ValueError("Need twelve stratified serving cases")
    corpus = json.loads((args.directory / "corpus.json").read_text(encoding="utf-8"))
    from app.contracts.training import TrainingCorpus

    raw_cases = {r.task_id: r for r in TrainingCorpus.model_validate(corpus).samples}
    records, call_ids = [], []

    class ResearchRouter:
        def __init__(self, engine):
            self.ml = engine
            self.inner = PolicyRouter(
                engine,
                admission_input_rates=container.metering.catalog.admission_input_rates(),
            )

        def select(self, profile, prepared, registry, costs, policy, remaining):
            return self.inner.select(
                profile,
                prepared,
                registry,
                costs,
                policy.model_copy(update={"sandbox": True}),
                remaining,
            )

    runtimes = {
        "attention": MLRouterService.load(attention_path),
        "ml": MLRouterService.load(ml_path),
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://research-pilot"
        ) as client:
            for index, row in enumerate(rows):
                variants = ["reference", "ml", "attention"]
                variants = variants[index % 3 :] + variants[: index % 3]
                for variant in variants:
                    container.orchestrator.router = ResearchRouter(
                        runtimes["ml" if variant == "reference" else variant]
                    )
                    session = await container.sessions.create(
                        principal, "ML qualification serving pilot"
                    )
                    body = {
                        "session_id": session.id,
                        "client_request_id": "qualification-pilot-" + str(uuid4()),
                        "message": row.messages[-1].content,
                        "mode": "baseline" if variant == "reference" else "optimized",
                        "flags": {
                            "router": variant != "reference",
                            "rewrite": False,
                            "context": False,
                            "memory": False,
                        },
                        "constraints": Constraints(
                            max_total_usd=Decimal(".01"), deadline_ms=60000
                        ).model_dump(mode="json"),
                    }
                    started = perf_counter()
                    response = await client.post(
                        "/internal-qualification/chat", json=body
                    )
                    duration = (perf_counter() - started) * 1000
                    response.raise_for_status()
                    payload = response.json()
                    # DTO is parsed so field drift cannot accidentally fabricate a pass.
                    from app.contracts.dtos import ChatResponse

                    result = ChatResponse.model_validate(payload)
                    if variant != "reference" and (
                        not result.route.ml_executed
                        or (
                            variant == "attention"
                            and not result.route.attention_executed
                        )
                    ):
                        raise ValueError(
                            "Measured pilot did not execute the intended router"
                        )
                    source = raw_cases[row.task_id]
                    assert source.grading
                    qualified = grade(
                        source.grading, result.response.content, source.gold
                    ).qualified
                    calls = await container.metering.owned_records(
                        principal, result.request_id
                    )
                    call_ids.extend(c.call_id for c in calls)
                    records.append(
                        {
                            "task_id": row.task_id,
                            "domain": row.domain,
                            "variant": variant,
                            "latency_ms": duration,
                            "qualified": qualified,
                            "request_id": result.request_id,
                            "model_id": result.route.model_id,
                        }
                    )
                    atomic_text(
                        args.report.with_suffix(".progress.json"),
                        json.dumps(records, indent=2),
                    )
        reference = {r["task_id"]: r for r in records if r["variant"] == "reference"}
        optimized = [r for r in records if r["variant"] == "attention"]
        report = {
            "execution_source": "live",
            "configuration_hashes": runtimes[
                "attention"
            ].multi.artifact.configuration_hashes,
            "provider_call_ids": call_ids,
            "attention_artifact_hash": runtimes["attention"].hash,
            "ml_artifact_hash": runtimes["ml"].hash,
            "p50_latency_ratio": median(r["latency_ms"] for r in optimized)
            / median(r["latency_ms"] for r in reference.values()),
            "critical_regressions": sum(
                reference[r["task_id"]]["qualified"] and not r["qualified"]
                for r in optimized
            ),
            "samples": len(rows),
            "records": records,
            "measurement": "in-process ASGI HTTP response includes route/provider/ledger/history; excludes TCP/TLS/browser",
            "limits": "12 cases x 3 variants x .01 USD upper request cap; existing user/project budgets apply",
        }
        atomic_text(args.report, json.dumps(report, indent=2))
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in ("samples", "p50_latency_ratio", "critical_regressions")
                }
            ),
            flush=True,
        )
    finally:
        await container.live.close()
        await container.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--report", type=Path, required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
