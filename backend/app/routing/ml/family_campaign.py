"""Measured research collection on the existing ledger/provider path.

One deduplicated operation, at most two calls, atomic checkpoints. No training,
serving activation or paid replay is hidden in this collector.
"""

import asyncio
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import select

from app.contracts.dtos import (
    CallRecord,
    ChatRequest,
    ContextBudgets,
    ContextFeatures,
    ExecutionRequest,
    FeatureFlags,
    Message,
    Principal,
    SessionSnapshot,
)
from app.contracts.errors import AppError
from app.contracts.training import TrainingCorpus, TrainingJob, TrainingManifest
from app.routing.ml.graders import grade
from app.routing.ml.multi_training import MultiSample, Observation
from app.routing.ml.pipeline import RouterTrainingPipeline, atomic_text, cache_key
from app.storage.models import UsageRecord

VERSION = "task-family-v1-20261027"


def stop_requested(directory, completed: int) -> bool:
    control = directory / "collection-control.json"
    if not control.exists():
        return False
    limit = json.loads(control.read_text())["stop_after_completed"]
    if type(limit) is not int or not 0 <= limit <= 900:
        raise ValueError("Invalid collection stop boundary")
    return completed >= limit


def continuation_approval(
    directory: Path, job: TrainingJob, source_sha256: str, unknown_ids: set[str]
) -> dict[str, Any] | None:
    path = directory / "bounded-continuation-approval.json"
    if not path.exists():
        if unknown_ids:
            raise ValueError("No explicit exception for unresolved dispatch")
        return None
    approval = json.loads(path.read_text())
    if (
        approval["job_id"] != job.id
        or approval["source_sha256"] != source_sha256
        or approval["start_completed"] != 440
        or approval["stop_after_completed"] != 450
        or approval["maximum_new_calls"] != 30
        or approval["api_calls_at_approval"] != 1323
        or approval["retain_unresolved_reserve"] is not True
        or approval["retry_unresolved"] is not False
        or job.api_calls > 1353
        or job.completed > 450
        or unknown_ids - set(approval["allowed_unknown_call_ids"])
    ):
        raise ValueError("Continuation exceeds the explicit ten-question exception")
    return approval


def deferred_call(cache_directory, manifest, messages, allowed_ids: set[str]) -> bool:
    for config in manifest.configurations:
        marker = cache_directory / (
            cache_key(manifest, config.config_id, messages) + ".dispatch.json"
        )
        if marker.exists() and json.loads(marker.read_text()).get("call_id") in allowed_ids:
            return True
    return False


class _CallLane(RouterTrainingPipeline):
    async def save(self, job: TrainingJob) -> None:
        # The coordinator owns the operation checkpoint. Per-call lanes must
        # never overwrite it with a stale copy; ledger writes remain atomic.
        pass


class _DispatchGate:
    def __init__(self, provider: Any):
        self.provider = provider
        self.lock = asyncio.Lock()
        self.last_call = 0.0
        self.stopped = False
        self.interval = 0.0

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        async with self.lock:
            await asyncio.sleep(max(0, self.interval - (perf_counter() - self.last_call)))
            if self.stopped:
                raise AppError(
                    "FAMILY_COLLECTION_HALTED",
                    409,
                    "No further dispatch after a failed call",
                    dispatch_state="not_dispatched",
                )
            self.last_call = perf_counter()
        try:
            return await self.provider.generate(*args, **kwargs)
        except BaseException:
            self.stopped = True
            raise


def validate_source(corpus: TrainingCorpus) -> None:
    required = {"train": 100, "calibration": 50, "threshold": 50, "holdout": 100}
    families = {"exact_arithmetic", "structured_extraction", "vietnamese_qa"}
    if len(corpus.samples) != 900 or {s.domain for s in corpus.samples} != families:
        raise ValueError("Exactly three frozen 300-group families required")
    if (
        len({s.group_id for s in corpus.samples}) != 900
        or len({s.task_id for s in corpus.samples}) != 900
    ):
        raise ValueError("Repeated source group")
    for family in families:
        if Counter(s.split for s in corpus.samples if s.domain == family) != required:
            raise ValueError("Source split mismatch")
    for row in corpus.samples:
        if (
            not row.grading
            or row.grading.synthetic
            or row.grading.label_source != "dataset_gold"
            or len(row.messages) != 1
        ):
            raise ValueError("Independent original source gold and single user turn required")


class FamilyCollection(RouterTrainingPipeline):
    @staticmethod
    def _job(row: Any) -> TrainingJob:
        saved = TrainingJob.model_validate_json(row.response_json or "{}")
        if row.status == "interrupted" and saved.error_code == "USER_REQUESTED_PAUSE":
            return saved
        return RouterTrainingPipeline._job(row)

    def __init__(self, container: Any):
        super().__init__(
            container.settings, container.db, container.ledger, lambda _: None, container.live
        )
        self.container = container
        self.dispatch_gate = _DispatchGate(container.live)

    async def _accounted_job(self, job: TrainingJob) -> TrainingJob:
        async with self.db.sessions() as db:
            records = list(
                await db.scalars(
                    select(UsageRecord.record_json).where(UsageRecord.operation_id == job.id)
                )
            )
        calls = [CallRecord.model_validate_json(r) for r in records]
        return job.model_copy(
            update={
                "api_calls": len(calls),
                "spent_usd": sum((c.cost.serving_usd or Decimal(0) for c in calls), Decimal(0)),
                "unknown_cost_calls": sum(c.cost.serving_usd is None for c in calls),
            }
        )

    async def _collect_answers(self, user, job, manifest, order, messages):
        self.dispatch_gate.interval = manifest.min_interval_seconds
        semaphore = asyncio.Semaphore(2)
        answers = {}
        hits = 0

        async def one(config):
            nonlocal hits
            async with semaphore:
                if self.dispatch_gate.stopped:
                    raise AppError("FAMILY_COLLECTION_HALTED", 409, "Collection stopped")
                lane = _CallLane(
                    self.settings, self.db, self.ledger, lambda _: None, self.dispatch_gate
                )
                try:
                    answer, updated = await lane._generation(
                        user, job, manifest, config.config_id, messages
                    )
                    hits += updated.cache_hits - job.cache_hits
                    answers[config.config_id] = answer
                except BaseException:
                    self.dispatch_gate.stopped = True
                    raise

        # Drain already admitted calls on failure. Cancelling peers here would
        # create unknown dispatches and lose otherwise recoverable responses.
        outcomes = await asyncio.gather(*(one(c) for c in order), return_exceptions=True)
        job = await self._accounted_job(job)
        job = job.model_copy(update={"cache_hits": job.cache_hits + hits})
        await self.save(job)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
        return answers, job

    async def _run(self, user: Principal, job: TrainingJob, manifest: TrainingManifest) -> None:
        directory = self.directory(job.id)
        try:
            job = await self._accounted_job(job)
            async with self.db.sessions() as db:
                records = list(
                    await db.scalars(
                        select(UsageRecord.record_json).where(UsageRecord.operation_id == job.id)
                    )
                )
            unknown_ids = {
                r.call_id
                for raw_record in records
                if (r := CallRecord.model_validate_json(raw_record)).cost.serving_usd is None
            }
            try:
                approval = continuation_approval(
                    directory.parent.parent, job, manifest.source.sha256, unknown_ids
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise AppError(
                    "DISPATCH_REVIEW_REQUIRED",
                    409,
                    "Reconcile dispatch or provide a bounded explicit exception",
                ) from exc
            if (
                manifest.version != VERSION
                or job.active_phase != "collect"
                or job.request.budget_usd > 1.5
            ):
                raise ValueError("Frozen collection-only campaign with 1.50 USD cap required")
            from app.routing.ml.collection import collect_source

            raw = await collect_source(manifest.source, False)
            corpus = TrainingCorpus.model_validate_json(raw)
            validate_source(corpus)
            atomic_text(directory / "manifest.json", manifest.model_dump_json(indent=2))
            atomic_text(directory / "corpus.json", corpus.model_dump_json(indent=2))
            checkpoint = directory / "observations.json"
            rows = json.loads(checkpoint.read_text()) if checkpoint.exists() else []
            done = {r["task_id"] for r in rows}
            deferred = []
            job = job.model_copy(update={"stage": "distill", "total": 900, "completed": len(rows)})
            await self.save(job)
            # DEV first. HOLDOUT labels are never consumed by fit; separate files below.
            ordered = sorted(
                corpus.samples,
                key=lambda r: (
                    r.split == "holdout",
                    hashlib.sha256(r.task_id.encode()).hexdigest(),
                ),
            )
            for sample in ordered:
                if stop_requested(directory.parent.parent, len(rows)):
                    job = job.model_copy(
                        update={"status": "interrupted", "error_code": "USER_REQUESTED_PAUSE"}
                    )
                    break
                if sample.task_id in done:
                    continue
                prepared_path = (
                    directory
                    / "prepared"
                    / (hashlib.sha256(sample.task_id.encode()).hexdigest() + ".json")
                )
                if prepared_path.exists():
                    prepared_doc = json.loads(prepared_path.read_text())
                    messages = tuple(Message.model_validate(m) for m in prepared_doc["messages"])
                else:
                    started = perf_counter()
                    text = sample.messages[0].content
                    request = ChatRequest(
                        session_id="family-offline-context",
                        client_request_id=sample.task_id,
                        message=text,
                        mode="optimized",
                        flags=FeatureFlags(router=True, rewrite=True, context=True, memory=True),
                    )
                    execution = ExecutionRequest(
                        request_id=job.id,
                        principal=user,
                        request=request,
                        namespace="eval",
                        execution_source="live",
                    )
                    snapshot = SessionSnapshot(
                        owner_user_id=user.id, session_id=request.session_id, revision=0
                    )
                    # Certified envelope is a fresh, single user turn with no
                    # retrieved facts. Do not leak an operator's chat into data.
                    context = await self.container.orchestrator._prepare_context(
                        snapshot,
                        ContextBudgets(),
                        ContextFeatures(
                            current_turn=sample.messages[0], flags=request.flags or FeatureFlags()
                        ),
                    )
                    rewrite = await self.container.orchestrator.prompt.optimize(
                        execution, context, request.flags
                    )
                    messages = self.container.orchestrator._replace_current_user_message(
                        context.messages, rewrite.proposed
                    )
                    prepared_doc = {
                        "task_id": sample.task_id,
                        "messages": [m.model_dump(mode="json") for m in messages],
                        "original_messages": [m.model_dump(mode="json") for m in sample.messages],
                        "rewrite": rewrite.state.model_dump(mode="json"),
                        "context": context.state.model_dump(mode="json"),
                        "prepare_ms": (perf_counter() - started) * 1000,
                    }
                    atomic_text(prepared_path, json.dumps(prepared_doc, ensure_ascii=False))
                if approval and deferred_call(
                    directory.parent / "cache",
                    manifest,
                    messages,
                    set(approval["allowed_unknown_call_ids"]),
                ):
                    deferred.append(sample.task_id)
                    continue  # Never retry, relabel, or erase the unresolved sample.
                if approval and job.api_calls + len(manifest.configurations) > 1353:
                    raise AppError(
                        "BOUNDED_CONTINUATION_COMPLETE", 409, "No additional calls authorized"
                    )
                offset = int(hashlib.sha256(sample.task_id.encode()).hexdigest()[:8], 16) % 3
                order = manifest.configurations[offset:] + manifest.configurations[:offset]
                answers, job = await self._collect_answers(user, job, manifest, order, messages)
                observations = []
                for config in manifest.configurations:
                    answer = answers[config.config_id]
                    assert sample.grading is not None
                    outcome = grade(sample.grading, answer.text, sample.gold)
                    observations.append(
                        Observation(
                            config_id=config.config_id,
                            qualified=outcome.qualified,
                            usd=answer.usd,
                            latency_ms=answer.latency_ms,
                            input_tokens=answer.input_tokens,
                            output_tokens=answer.output_tokens,
                            label_source=outcome.label_source,
                            grader_version=outcome.grader_version,
                            response_sha256=hashlib.sha256(answer.text.encode()).hexdigest(),
                            grade_metrics=outcome.metrics,
                        )
                    )
                row = MultiSample(
                    task_id=sample.task_id,
                    group_id=sample.group_id,
                    domain=sample.domain,
                    split=sample.split,
                    messages=messages,
                    observations=tuple(observations),
                )
                rows.append(row.model_dump(mode="json"))
                atomic_text(checkpoint, json.dumps(rows, ensure_ascii=False))
                for name, subset in (
                    ("dev", [r for r in rows if r["split"] != "holdout"]),
                    ("holdout", [r for r in rows if r["split"] == "holdout"]),
                ):
                    atomic_text(
                        directory / (name + "-observations.json"),
                        json.dumps(subset, ensure_ascii=False),
                    )
                job = job.model_copy(
                    update={
                        "completed": len(rows),
                        "pilot_report": {
                            "phase": "family_collection",
                            "complete_corpus": len(rows) == 900,
                            "frozen_engine": True,
                            "family_counts": dict(Counter(r["domain"] for r in rows)),
                            "deferred_unresolved_task_ids": deferred,
                        },
                    }
                )
                await self.save(job)
            if job.status != "interrupted":
                job = job.model_copy(update={"status": "succeeded", "stage": "complete"})
        except asyncio.CancelledError:
            job = job.model_copy(
                update={"status": "interrupted", "error_code": "PROCESS_INTERRUPTED"}
            )
            await asyncio.shield(self.save(job))
            raise
        except Exception as exc:
            saved = await self.get(user, job.id)
            job = (await self._accounted_job(job)).model_copy(
                update={
                    "api_calls": max(job.api_calls, saved.api_calls),
                    "status": "failed",
                    "error_code": exc.code if isinstance(exc, AppError) else type(exc).__name__,
                }
            )
        await self.save(job)
        atomic_text(directory / "collection-status.json", job.model_dump_json(indent=2))
