"""A single ledger operation across collection batches, resume, train and evaluation."""

import asyncio
import hashlib
import json
import random
import re
from collections import Counter, deque
from time import perf_counter
from typing import TYPE_CHECKING, Any

import httpx

from app.contracts.dtos import Message, Principal
from app.contracts.errors import AppError
from app.contracts.representations import EncoderSpec
from app.contracts.training import (
    GradingSpec,
    JudgeResult,
    RawTrainingSample,
    TrainingCorpus,
    TrainingJob,
    TrainingManifest,
)
from app.routing.ml.collection import collect_source, group_split, parse_corpus
from app.routing.ml.encoder import OnnxTokenEncoder, resolve_asset
from app.routing.ml.graders import GRADER_VERSION, Grade, arithmetic, grade, validate_gold
from app.routing.ml.independence import content_key
from app.routing.ml.multi import MultiRouterService
from app.routing.ml.multi_training import (
    MultiDataset,
    MultiSample,
    Observation,
    evaluate_multi,
    replay_rows,
    train_multi,
)
from app.routing.ml.sandbox import check_sandbox

if TYPE_CHECKING:
    from app.routing.ml.pipeline import RouterTrainingPipeline

PROTOCOL = "gold-pilot-v1"


def clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def frozen_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def interleave(samples: tuple[RawTrainingSample, ...]) -> tuple[RawTrainingSample, ...]:
    def balanced(split: str) -> deque[RawTrainingSample]:
        domains = {
            domain: deque(
                sorted(
                    (r for r in samples if r.split == split and r.domain == domain),
                    key=lambda r: r.task_id,
                )
            )
            for domain in sorted({r.domain for r in samples if r.split == split})
        }
        rows: deque[RawTrainingSample] = deque()
        while any(domains.values()):
            for queue in domains.values():
                if queue:
                    rows.append(queue.popleft())
        return rows

    queues = {s: balanced(s) for s in ("train", "calibration", "threshold", "holdout")}
    pattern = (
        "train",
        "train",
        "calibration",
        "train",
        "threshold",
        "train",
        "holdout",
        "calibration",
        "train",
        "holdout",
        "train",
        "threshold",
        "train",
        "calibration",
        "train",
        "holdout",
        "train",
        "calibration",
        "train",
        "threshold",
    )
    result = []
    while any(queues.values()):
        for split in pattern:
            if queues[split]:
                result.append(queues[split].popleft())
    return tuple(result)


async def prepare_samples(manifest: TrainingManifest) -> TrainingCorpus:
    buckets: dict[str, deque[RawTrainingSample]] = {}
    for index, source in enumerate(manifest.sources or (manifest.source,)):
        if manifest.split_protocol == "frozen_canonical" and source.adapter != "canonical":
            raise AppError("SOURCE_SPLIT_LEAKAGE", 409, "Frozen splits require a canonical corpus")
        if (
            not source.license_reviewed
            or not source.allow_training
            or not source.license_url
            or not source.license_url.startswith("https://")
        ):
            raise AppError(
                "SOURCE_REVIEW_REQUIRED",
                409,
                "Pilot sources require recorded license and training eligibility review",
            )
        # Public downloads/conversions are a separate pinned preparation step.
        # No generation call may depend on an unreviewed remote conversion.
        raw = await collect_source(source, False)
        parsed = parse_corpus(raw, source, 2000)
        rows = []
        for row in parsed.samples:
            spec = row.grading
            if not spec:
                raise AppError(
                    "GRADER_REQUIRED",
                    409,
                    "Every pilot case needs a versioned grading specification",
                )
            if spec.kind == "code":
                spec = spec.model_copy(update={"docker_image": manifest.docker_image})
            if spec.kind == "extractive_qa":
                row = row.model_copy(
                    update={
                        "messages": (
                            *row.messages,
                            Message(
                                role="user",
                                content='Return only JSON {"answer":"exact answer span"}. If unanswerable, return {"answer":null}.',
                            ),
                        )
                    }
                )
            validate_gold(spec, row.gold)
            if spec.synthetic:
                raise AppError(
                    "SOURCE_SPLIT_LEAKAGE",
                    409,
                    "Pilot source pool must contain original public/human cases; synthesize only after splitting",
                )
            rows.append(
                row.model_copy(
                    update={"task_id": f"source-{index}:" + row.task_id, "grading": spec}
                )
            )
        if manifest.split_protocol == "frozen_canonical":
            validate_corpus(TrainingCorpus(samples=tuple(rows)))
        buckets[str(index)] = deque(sorted(rows, key=lambda r: frozen_hash(r.task_id)))
    selected: list[RawTrainingSample] = []
    seen: set[str] = set()
    groups: set[str] = set()
    public_limit = min(500, manifest.max_samples)
    if manifest.synthesize:
        public_limit = max(16, public_limit - min(20, public_limit // 10))
    while len(selected) < public_limit and any(buckets.values()):
        for queue in buckets.values():
            if queue:
                row = queue.popleft()
                key = content_key(row.messages)
                if key in seen or row.group_id in groups:
                    continue
                seen.add(key)
                groups.add(row.group_id)
                # One original unit per family in pilot; variants are introduced later.
                selected.append(
                    row
                    if manifest.split_protocol == "frozen_canonical"
                    else row.model_copy(update={"split": group_split(row.group_id)})
                )
                if len(selected) >= public_limit:
                    break
    if any(
        sum(r.split == split for r in selected) < 4
        for split in ("train", "calibration", "threshold", "holdout")
    ):
        raise AppError("INSUFFICIENT_EVIDENCE", 409, "Need independent units in all four splits")
    return TrainingCorpus(samples=interleave(tuple(selected)))


async def check_models(pipeline: "RouterTrainingPipeline", manifest: TrainingManifest) -> None:
    if not pipeline.live_allowed(manifest):
        raise AppError("TRAINING_LIVE_DISABLED", 409, "Live pilot gate disabled")
    async with httpx.AsyncClient(timeout=30) as client:
        names: set[str] = set()
        token = None
        for _ in range(10):
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": pipeline.settings.gemini_api_key.get_secret_value()},
                params={"pageToken": token} if token else {},
            )
            if response.status_code != 200:
                raise AppError(
                    "MODEL_ACCESS_REQUIRED", 409, "Cannot validate configured model metadata"
                )
            payload = response.json()
            names.update(
                m["name"]
                for m in payload.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            )
            token = payload.get("nextPageToken")
            if not token:
                break
    if any(
        "models/" + c.model_id.removeprefix("models/") not in names for c in manifest.configurations
    ):
        raise AppError(
            "MODEL_UNAVAILABLE", 409, "Configured model missing; catalog was not changed"
        )


async def judge_open(
    pipeline: "RouterTrainingPipeline",
    user: Principal,
    job: TrainingJob,
    manifest: TrainingManifest,
    sample: RawTrainingSample,
    answers: list[Any],
) -> tuple[list[Grade], TrainingJob]:
    from app.routing.ml.pipeline import JUDGE_SYSTEM

    order = list(range(3))
    random.Random(frozen_hash(sample.task_id + manifest.version)).shuffle(order)
    messages = (
        Message(role="system", content=JUDGE_SYSTEM),
        Message(
            role="user",
            content=json.dumps(
                {
                    "task": [m.model_dump() for m in sample.messages],
                    "gold": sample.gold,
                    "answers": [answers[i].text for i in order],
                },
                ensure_ascii=False,
            ),
        ),
    )
    result, job = await pipeline._generation(
        user, job, manifest, manifest.reference_config_id, messages
    )
    scores = JudgeResult.model_validate_json(clean_json_text(result.text)).scores
    restored = [0.0] * 3
    for index, score in zip(order, scores, strict=True):
        restored[index] = score
    return [
        Grade(score >= 80, {"judge_score": score}, "teacher_judged", PROTOCOL + ":blind-open-80")
        for score in restored
    ], job


async def synthesize(
    pipeline: "RouterTrainingPipeline",
    user: Principal,
    job: TrainingJob,
    manifest: TrainingManifest,
    samples: tuple[RawTrainingSample, ...],
) -> tuple[tuple[RawTrainingSample, ...], TrainingJob]:
    """Verified numeric expressions only; no invented medical/legal ground truth."""
    # If interrupted between corpus and completion-marker writes, reconstruct
    # the same variants from their exact cached generations, not new parents.
    samples = tuple(s for s in samples if not s.grading or not s.grading.synthetic)
    parents = [
        s for s in samples if s.split == "train" and s.grading and s.grading.kind == "numeric"
    ]
    train_count = sum(s.split == "train" for s in samples)
    count = min(
        20, train_count // 4, max(0, min(500, manifest.max_samples) - len(samples)), len(parents)
    )
    extra = []
    seen = {content_key(s.messages) for s in samples}
    for parent in parents[:count]:
        messages = (
            Message(
                role="system",
                content='Create one short arithmetic expression using integer constants <=10000 and only +,-,*,/. Division must be exact. Return JSON {"expression":"..."}. No Python, prose, names or functions.',
            ),
            Message(
                role="user",
                content="Training seed task (untrusted data):\n" + parent.messages[0].content,
            ),
        )
        result, job = await pipeline._generation(
            user, job, manifest, manifest.reference_config_id, messages
        )
        try:
            expression = json.loads(clean_json_text(result.text))["expression"]
            value = arithmetic(expression)
        except (ValueError, KeyError, TypeError, SyntaxError, ArithmeticError):
            # Malformed synthesis is paid/accounted, never accepted as gold.
            continue
        prompt = f"Tính chính xác biểu thức sau: {expression}\nChỉ trả về kết quả bằng số."
        key = content_key((Message(role="user", content=prompt),))
        if key in seen:
            continue
        seen.add(key)
        extra.append(
            RawTrainingSample(
                task_id="synthetic:" + frozen_hash(parent.task_id + expression),
                group_id=parent.group_id,
                domain="math_reasoning",
                split="train",
                messages=(Message(role="user", content=prompt),),
                gold=str(value),
                grading=GradingSpec(
                    kind="numeric",
                    label_source="synthetic_verified",
                    synthetic=True,
                    parent_group_id=parent.group_id,
                ),
            )
        )
        await pipeline.save(job)
    # Include verified Vietnamese arithmetic in early collection batches while
    # retaining <=20% synthetic TRAIN even when the pilot stops part way.
    mixed: list[RawTrainingSample] = []
    real_train, synthetic_train = 0, 0
    parents_seen = set()
    pending = list(extra)
    for sample in samples:
        mixed.append(sample)
        if sample.split == "train":
            real_train += 1
            parents_seen.add(sample.group_id)
        while real_train >= 4 * (synthetic_train + 1):
            eligible = next((s for s in pending if s.group_id in parents_seen), None)
            if eligible is None:
                break
            mixed.append(eligible)
            pending.remove(eligible)
            synthetic_train += 1
    if pending:
        raise AppError("SYNTHETIC_LIMIT", 409, "Synthetic variants have no eligible TRAIN parent")
    return tuple(mixed), job


def dataset(manifest: TrainingManifest, rows: list[MultiSample]) -> MultiDataset:
    return MultiDataset(
        format_version="router-dataset-v2",
        version=manifest.version,
        purpose="software_test" if manifest.software_test else "research_candidate",
        provenance=manifest.model_dump_json(),
        grader_version=PROTOCOL + ":" + GRADER_VERSION,
        configurations=manifest.configurations,
        reference_config_id=manifest.reference_config_id,
        costs=manifest.costs,
        samples=tuple(rows),
    )


def validate_corpus(corpus: TrainingCorpus) -> None:
    groups: dict[str, str] = {}
    hashes: dict[str, str] = {}
    tasks = set()
    parents = {
        s.group_id
        for s in corpus.samples
        if s.split == "train" and s.grading and not s.grading.synthetic
    }
    synthetic = 0
    train = sum(s.split == "train" for s in corpus.samples)
    for sample in corpus.samples:
        if not sample.grading:
            raise AppError("GRADER_REQUIRED", 409, "Missing grading specification")
        validate_gold(sample.grading, sample.gold)
        key = content_key(sample.messages)
        if (
            sample.task_id in tasks
            or groups.get(sample.group_id, sample.split) != sample.split
            or key in hashes
        ):
            raise AppError("SOURCE_SPLIT_LEAKAGE", 409, "Source/content crosses splits")
        tasks.add(sample.task_id)
        groups[sample.group_id], hashes[key] = sample.split, sample.split
        spec = sample.grading
        if spec.synthetic:
            synthetic += 1
            if (
                sample.split != "train"
                or spec.parent_group_id != sample.group_id
                or sample.group_id not in parents
                or spec.label_source != "synthetic_verified"
            ):
                raise AppError(
                    "SOURCE_SPLIT_LEAKAGE",
                    409,
                    "Synthetic variants must retain a real TRAIN parent",
                )
        if sample.split == "holdout" and spec.label_source not in {
            "dataset_gold",
            "human_verified",
        }:
            raise AppError(
                "SOURCE_REVIEW_REQUIRED",
                409,
                "HOLDOUT requires public gold or human-verified targets",
            )
    if len(corpus.samples) > 500 or synthetic > train * 0.2:
        raise AppError("SYNTHETIC_LIMIT", 409, "At most 500 prompts and 20% synthetic TRAIN")


def timed_evaluate(data: MultiDataset, raw: str) -> dict[str, Any]:
    engine = MultiRouterService(raw)
    if not engine.artifact:
        raise ValueError("ARTIFACT_VALIDATION_FAILED")
    timings = {}
    replays = {}
    for row in data.samples:
        if engine.semantic:
            engine.semantic.cache.clear()
        started = perf_counter()
        replays[row.task_id] = replay_rows(data, engine, (row,))[0]
        timings[row.task_id] = (perf_counter() - started) * 1000
    report: dict[str, Any] = evaluate_multi(data, engine)
    # Conservative per-case all-candidate scoring cost; HTTP/DB serving overhead remains
    # unmeasured, so do not call this a production end-to-end benchmark.
    routed_latency, reference_latency = [], []
    outcomes = []
    for row in data.samples:
        # Reuse the same production policy path/feasibility as evaluate_multi.
        replay = replays[row.task_id]
        _, scores, feasible = replay
        selected = next(
            (
                c
                for c in feasible
                if not row.tool_recovery_required
                and scores[c]
                >= next(p.threshold for p in engine.artifact.predictors if p.config_id == c)
            ),
            data.reference_config_id,
        )
        observations = {o.config_id: o for o in row.observations}
        observation = observations[selected]
        routed_latency.append(observation.latency_ms + timings[row.task_id])
        reference_latency.append(observations[data.reference_config_id].latency_ms)
        outcomes.append(
            {
                "task_id": row.task_id,
                "group_id": row.group_id,
                "domain": row.domain,
                "selected": selected,
                "qualified": observation.qualified,
                "reference_qualified": observations[data.reference_config_id].qualified,
                "usd": float(observation.usd),
                "latency_ms": routed_latency[-1],
            }
        )
    from statistics import median

    report["routing_overhead"] = {
        "p50_ms": median(timings.values()),
        "max_ms": max(timings.values()),
        "measurement": "cold semantic cache, feasibility and all candidate scores; excludes serving HTTP/DB",
    }
    report["all_in_p50_ratio"] = median(routed_latency) / median(reference_latency)
    report["outcomes"] = outcomes
    report["regressions"] = sum(o["reference_qualified"] and not o["qualified"] for o in outcomes)
    report["guardrails_with_routing_overhead"] = bool(
        report["report"]["guardrails_observed"] and report["all_in_p50_ratio"] <= 1.1
    )
    return report


def paired_comparison(baseline: dict[str, Any], attention: dict[str, Any]) -> dict[str, Any]:
    """Paired source-group bootstrap, descriptive only; never used to tune HOLDOUT."""
    import numpy as np

    base = {r["task_id"]: r for r in baseline["outcomes"]}
    grouped: dict[str, list[list[float]]] = {}
    for row in attention["outcomes"]:
        other = base[row["task_id"]]
        grouped.setdefault(row["group_id"], []).append(
            [
                float(row["qualified"]) - float(other["qualified"]),
                row["usd"] - other["usd"],
                row["latency_ms"] - other["latency_ms"],
            ]
        )
    units = [np.asarray(rows, dtype=float) for rows in grouped.values()]
    rng = np.random.default_rng(42)
    draws = np.asarray(
        [
            np.concatenate([units[i] for i in rng.integers(0, len(units), size=len(units))]).mean(
                axis=0
            )
            for _ in range(2000)
        ]
    )
    mean = np.concatenate(units).mean(axis=0)
    return {
        "method": "paired source-group bootstrap, 2000 resamples, seed 42; descriptive, no non-inferiority claim",
        "independent_groups": len(units),
        "attention_minus_baseline": {
            name: {
                "mean": float(mean[i]),
                "ci95": [float(x) for x in np.quantile(draws[:, i], [0.025, 0.975])],
            }
            for i, name in enumerate(("pass_rate", "usd_per_prompt", "latency_ms"))
        },
    }


async def run_pilot(
    pipeline: "RouterTrainingPipeline",
    user: Principal,
    job: TrainingJob,
    manifest: TrainingManifest,
) -> TrainingJob:
    from app.routing.ml.pipeline import atomic_text

    directory = pipeline.directory(job.id)
    frozen_manifest = directory / "manifest.json"
    if not frozen_manifest.exists():
        atomic_text(frozen_manifest, manifest.model_dump_json(indent=2))
    if job.request.budget_usd > 5:
        raise AppError("PILOT_BUDGET_LIMIT", 422, "Pilot budget cannot exceed 5 USD")
    if not manifest.encoder_spec_path:
        raise AppError(
            "ATTENTION_REQUIRES_ENCODER_AND_HYBRID",
            409,
            "Pilot trains attention and requires an encoder",
        )
    spec = EncoderSpec.model_validate_json(
        resolve_asset(manifest.encoder_spec_path).read_text(encoding="utf-8")
    )
    await asyncio.to_thread(OnnxTokenEncoder, spec)
    from app.routing.ml.attention import torch_module

    await asyncio.to_thread(torch_module, spec.hidden_size)
    corpus_path = directory / "corpus.json"
    if corpus_path.exists():
        corpus = TrainingCorpus.model_validate_json(corpus_path.read_text(encoding="utf-8"))
    else:
        corpus = await prepare_samples(manifest)
        atomic_text(corpus_path, corpus.model_dump_json(indent=2))
    validate_corpus(corpus)
    corpus_hash_path = directory / "corpus.sha256"
    corpus_hash = frozen_hash(corpus.model_dump_json())
    if corpus_hash_path.exists() and corpus_hash_path.read_text(encoding="utf-8") != corpus_hash:
        raise AppError("SOURCE_HASH_MISMATCH", 409, "Frozen pilot corpus changed")
    atomic_text(corpus_hash_path, corpus_hash)
    job = job.model_copy(update={"total": len(corpus.samples)})
    await pipeline.save(job)
    for sample in corpus.samples if job.active_phase != "train" else ():
        if sample.grading and sample.grading.kind == "code":
            await asyncio.to_thread(check_sandbox, sample.grading.docker_image or "")
            break
    if job.active_phase != "train" and job.request.mode == "huggingface_gemini":
        await check_models(pipeline, manifest)
    if (
        job.active_phase != "train"
        and manifest.synthesize
        and not (directory / "synthesis.done").exists()
    ):
        samples, job = await synthesize(pipeline, user, job, manifest, corpus.samples)
        corpus = TrainingCorpus(samples=samples)
        validate_corpus(corpus)
        atomic_text(corpus_path, corpus.model_dump_json(indent=2))
        atomic_text(corpus_hash_path, frozen_hash(corpus.model_dump_json()))
        atomic_text(directory / "synthesis.done", "complete")
    checkpoint = directory / "observations.json"
    rows = (
        [MultiSample.model_validate(r) for r in json.loads(checkpoint.read_text(encoding="utf-8"))]
        if checkpoint.exists()
        else []
    )
    originals = {s.task_id: s for s in corpus.samples}
    for row in rows:
        source = originals.get(row.task_id)
        if (
            not source
            or (row.messages, row.group_id, row.split, row.domain)
            != (source.messages, source.group_id, source.split, source.domain)
            or {o.config_id for o in row.observations}
            != {c.config_id for c in manifest.configurations}
        ):
            raise AppError(
                "CHECKPOINT_MISMATCH",
                409,
                "Observation checkpoint differs from frozen corpus/catalog",
            )
    if len({r.task_id for r in rows}) != len(rows):
        raise AppError("CHECKPOINT_MISMATCH", 409, "Duplicate observation checkpoint rows")
    completed = {r.task_id for r in rows}
    job = job.model_copy(
        update={"stage": "distill", "total": len(corpus.samples), "completed": len(rows)}
    )
    await pipeline.save(job)
    review_file = directory / "review-queue.json"
    review_queue = (
        json.loads(review_file.read_text(encoding="utf-8")) if review_file.exists() else []
    )
    collection_stop = None
    batch_start = len(rows)
    if job.active_phase != "train":
        for sample in corpus.samples:
            if sample.task_id in completed:
                continue
            assert sample.grading
            try:
                answers_by_config = {}
                offset = int(frozen_hash(sample.task_id)[:8], 16) % len(manifest.configurations)
                order = manifest.configurations[offset:] + manifest.configurations[:offset]
                for config in order:
                    answer, job = await pipeline._generation(
                        user, job, manifest, config.config_id, sample.messages
                    )
                    answers_by_config[config.config_id] = answer
                    await pipeline.save(job)
                answers = [answers_by_config[c.config_id] for c in manifest.configurations]
                if sample.grading.kind == "open":
                    grades, job = await judge_open(pipeline, user, job, manifest, sample, answers)
                    if (
                        int(frozen_hash(sample.task_id)[:8], 16) % 10 == 0
                        or sample.critical
                        or not any(r["split"] == sample.split for r in review_queue)
                    ):
                        review_queue = [r for r in review_queue if r["task_id"] != sample.task_id]
                        review_queue.append(
                            {
                                "task_id": sample.task_id,
                                "split": sample.split,
                                "task": [m.model_dump() for m in sample.messages],
                                "gold": sample.gold,
                                "answers": [
                                    {
                                        "config_id": c.config_id,
                                        "text": a.text,
                                        "response_sha256": frozen_hash(a.text),
                                        "qualified": g.qualified,
                                    }
                                    for c, a, g in zip(
                                        manifest.configurations, answers, grades, strict=True
                                    )
                                ],
                            }
                        )
                        atomic_text(
                            review_file, json.dumps(review_queue, ensure_ascii=False, indent=2)
                        )
                else:
                    grades = [
                        await asyncio.to_thread(grade, sample.grading, answer.text, sample.gold)
                        for answer in answers
                    ]
            except AppError as exc:
                if exc.code != "BUDGET_EXCEEDED":
                    raise
                collection_stop = "BUDGET_EXCEEDED"
                break
            rows.append(
                MultiSample(
                    task_id=sample.task_id,
                    group_id=sample.group_id,
                    domain=sample.domain,
                    split=sample.split,
                    messages=sample.messages,
                    has_rag_context=sample.has_rag_context,
                    critical=sample.critical,
                    observations=tuple(
                        Observation(
                            config_id=c.config_id,
                            qualified=g.qualified,
                            usd=a.usd,
                            latency_ms=a.latency_ms,
                            input_tokens=a.input_tokens,
                            output_tokens=a.output_tokens,
                            label_source=g.label_source,
                            grader_version=g.grader_version,
                            grade_metrics=g.metrics,
                            response_sha256=frozen_hash(a.text),
                        )
                        for c, a, g in zip(manifest.configurations, answers, grades, strict=True)
                    ),
                )
            )
            completed.add(sample.task_id)
            # Every completed row is durable; batch boundaries are progress checkpoints,
            # never new ledger operations with a reset budget.
            atomic_text(
                checkpoint,
                json.dumps([r.model_dump(mode="json") for r in rows], ensure_ascii=False),
            )
            job = job.model_copy(
                update={"completed": len(rows), "batches_completed": len(rows) // 25}
            )
            await pipeline.save(job)
            if len(rows) - batch_start >= job.request.collection_batches * 25:
                collection_stop = "BATCH_COMPLETE" if len(rows) < len(corpus.samples) else None
                break
    reviews_path = directory / "reviews.json"
    reviews = json.loads(reviews_path.read_text(encoding="utf-8")) if reviews_path.exists() else {}
    pending_reviews = [
        r
        for r in review_queue
        if any(r["task_id"] + ":" + a["config_id"] not in reviews for a in r["answers"])
    ]
    reviewed_rows = []
    for row in rows:
        updated = []
        for observation in row.observations:
            review = reviews.get(row.task_id + ":" + observation.config_id)
            if review:
                if review["response_sha256"] != observation.response_sha256:
                    raise AppError("REVIEW_MISMATCH", 409, "Review response hash changed")
                observation = observation.model_copy(
                    update={
                        "qualified": review["qualified"],
                        "label_source": "human_verified",
                        "grader_version": PROTOCOL + ":human-review-v1",
                    }
                )
            updated.append(observation)
        reviewed_rows.append(row.model_copy(update={"observations": tuple(updated)}))
    rows = reviewed_rows
    ready = bool(rows) and all(
        sum(r.split == s for r in rows) >= 4
        for s in ("train", "calibration", "threshold", "holdout")
    )
    coverage = {
        "splits": dict(Counter(r.split for r in rows)),
        "domains": dict(Counter(r.domain for r in rows)),
        "independent_groups": len({r.group_id for r in rows}),
        "label_sources": dict(Counter(o.label_source for r in rows for o in r.observations)),
        "pending_human_review_cases": len(pending_reviews),
        "conclusion": "INSUFFICIENT_EVIDENCE",
        "import_eligible": False,
        "partial_collection": len(rows) != len(corpus.samples),
        "collection_stopped_reason": collection_stop,
        "effective_training": {
            "variants": ["ml", "ml_attention"],
            "frozen_encoder": True,
            "attention_epochs": manifest.attention_epochs,
            "batch_size": 64,
            "seed": 42,
            "domain_loss_weight": manifest.domain_loss_weight,
            "gbdt_trees": 100,
            "gbdt_depth": 3,
        },
    }
    job = job.model_copy(update={"ready_for_training": ready, "pilot_report": coverage})
    await pipeline.save(job)
    if (
        not ready
        or job.active_phase == "collect"
        or (job.active_phase == "full" and coverage["partial_collection"])
    ):
        atomic_text(directory / "report.json", json.dumps(coverage, indent=2))
        return job.model_copy(update={"status": "succeeded", "stage": "complete"})
    if pending_reviews:
        # No AI silently signs a human calibration review on the operator's behalf.
        atomic_text(directory / "report.json", json.dumps(coverage, indent=2))
        if any(r["split"] != "holdout" for r in pending_reviews):
            coverage["stopped_reason"] = "HUMAN_REVIEW_REQUIRED"
            return job.model_copy(
                update={
                    "status": "succeeded",
                    "stage": "complete",
                    "ready_for_training": False,
                    "pilot_report": coverage,
                }
            )
    data = dataset(manifest, rows)
    dev = data.model_copy(update={"samples": tuple(r for r in rows if r.split != "holdout")})
    holdout = data.model_copy(update={"samples": tuple(r for r in rows if r.split == "holdout")})
    atomic_text(directory / "dev.json", dev.model_dump_json(indent=2))
    atomic_text(directory / "holdout.json", holdout.model_dump_json(indent=2))
    frozen = directory / "frozen.json"
    if frozen.exists():
        hashes = json.loads(frozen.read_text(encoding="utf-8"))
        if hashes["dev"] != frozen_hash(dev.model_dump_json()):
            raise AppError(
                "FROZEN_DEV_CHANGED", 409, "Frozen DEV changed; HOLDOUT must not drive retraining"
            )
    else:
        job = job.model_copy(update={"stage": "train"})
        await pipeline.save(job)
        try:
            baseline = await asyncio.to_thread(train_multi, dev, hybrid=True, n_estimators=100)
            attention = await asyncio.to_thread(
                train_multi,
                dev,
                hybrid=True,
                encoder_spec=spec,
                attention_epochs=manifest.attention_epochs,
                n_estimators=100,
                domain_loss_weight=manifest.domain_loss_weight,
            )
        except ValueError as exc:
            if (
                "label" in str(exc).lower()
                or "guardrail" in str(exc).lower()
                or "independent" in str(exc).lower()
            ):
                atomic_text(directory / "report.json", json.dumps(coverage, indent=2))
                raise AppError(
                    "INSUFFICIENT_EVIDENCE",
                    409,
                    "Not enough label variation/independent evidence to fit both candidates",
                ) from exc
            raise
        atomic_text(directory / "baseline.json", baseline.model_dump_json(indent=2))
        atomic_text(directory / "artifact.json", attention.model_dump_json(indent=2))
        hashes = {
            "dev": frozen_hash(dev.model_dump_json()),
            "baseline": frozen_hash(baseline.model_dump_json(indent=2)),
            "attention": frozen_hash(attention.model_dump_json(indent=2)),
        }
        atomic_text(frozen, json.dumps(hashes, indent=2))
    raw = (directory / "artifact.json").read_text(encoding="utf-8")
    baseline_raw = (directory / "baseline.json").read_text(encoding="utf-8")
    if frozen_hash(raw) != hashes["attention"] or frozen_hash(baseline_raw) != hashes["baseline"]:
        raise AppError("ARTIFACT_HASH_MISMATCH", 409, "Frozen artifact changed")
    engine = MultiRouterService(raw)
    if engine.status != "ML_ARTIFACT_READY":
        raise AppError("ARTIFACT_VALIDATION_FAILED", 409, "Frozen candidate cannot load")
    job = job.model_copy(update={"stage": "evaluate", "artifact_hash": engine.hash})
    await pipeline.save(job)
    if pending_reviews:
        coverage["stopped_reason"] = "HUMAN_REVIEW_REQUIRED"
        return job.model_copy(
            update={"status": "succeeded", "stage": "complete", "pilot_report": coverage}
        )
    baseline_report = await asyncio.to_thread(timed_evaluate, holdout, baseline_raw)
    attention_report = await asyncio.to_thread(timed_evaluate, holdout, raw)
    ar, br = attention_report["report"], baseline_report["report"]
    baseline_dominates = (
        br["observed_pass_rate"] >= ar["observed_pass_rate"]
        and br["serving_usd"] <= ar["serving_usd"]
        and baseline_report["all_in_p50_ratio"] <= attention_report["all_in_p50_ratio"]
        and (
            br["observed_pass_rate"] > ar["observed_pass_rate"]
            or br["serving_usd"] < ar["serving_usd"]
            or baseline_report["all_in_p50_ratio"] < attention_report["all_in_p50_ratio"]
        )
    )
    eligible = bool(
        not coverage["partial_collection"]
        and job.unknown_cost_calls == 0
        and attention_report["guardrails_with_routing_overhead"]
        and not pending_reviews
        and not baseline_dominates
    )
    coverage.update(
        {
            "conclusion": "PASS_OBSERVED" if eligible else "INSUFFICIENT_EVIDENCE",
            "import_eligible": eligible,
            "unresolved_provider_calls": job.unknown_cost_calls,
            "baseline": baseline_report,
            "attention": attention_report,
            "baseline_dominates_attention": baseline_dominates,
            "paired_uncertainty": paired_comparison(baseline_report, attention_report),
            "attention_improves_cost": attention_report["report"]["serving_usd"]
            < baseline_report["report"]["serving_usd"],
            "limitations": [
                "Pilot point estimates do not prove non-inferiority",
                "Serving HTTP/DB overhead excluded",
                "Public sources may have appeared in provider pretraining",
            ],
        }
    )
    atomic_text(directory / "report.json", json.dumps(coverage, ensure_ascii=False, indent=2))
    if job.request.auto_import and eligible:
        pipeline._import(raw)
    return job.model_copy(
        update={
            "status": "succeeded",
            "stage": "complete",
            "pilot_report": coverage,
            "holdout_report": attention_report["report"],
            "imported": bool(job.request.auto_import and eligible),
        }
    )
