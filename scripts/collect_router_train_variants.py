"""Meter known TRAIN variants through the existing provider/quota/ledger pipeline.

No teacher invents model success. Only recorded provider outputs are graded.
No HOLDOUT, import, auto-retry or training occurs in this collector.
"""

import asyncio
import hashlib
import json

import run_router_pilot as runner
from app.contracts.errors import AppError
from app.contracts.training import TrainingCorpus
from app.routing.ml.graders import grade
from app.routing.ml.multi_training import MultiSample, Observation
from app.routing.ml.pilot import validate_corpus
from app.routing.ml.pipeline import RouterTrainingPipeline, atomic_text


def training_variants(corpus):
    validate_corpus(corpus)
    if any(s.split == "holdout" for s in corpus.samples):
        raise ValueError("Variant source must be DEV only")
    variants = tuple(s for s in corpus.samples if s.grading.synthetic)
    if not variants or any(s.split != "train" for s in variants):
        raise ValueError("Only verified TRAIN variants may be collected")
    return variants


class TrainVariantPipeline(RouterTrainingPipeline):
    async def _run(self, user, job, manifest):
        try:
            if job.active_phase != "collect" or job.request.auto_import:
                raise ValueError(
                    "Explicit collect-only mode and auto_import=false required"
                )
            directory = self.directory(job.id)
            atomic_text(directory / "manifest.json", manifest.model_dump_json(indent=2))
            source = manifest.source
            from pathlib import Path

            raw = Path(source.local_path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != source.sha256:
                raise ValueError("Variant source hash mismatch")
            corpus = TrainingCorpus.model_validate_json(raw)
            variants = training_variants(corpus)
            atomic_text(directory / "corpus.json", corpus.model_dump_json(indent=2))
            checkpoint = directory / "observations.json"
            rows = (
                [
                    MultiSample.model_validate(s)
                    for s in json.loads(checkpoint.read_text(encoding="utf-8"))
                ]
                if checkpoint.exists()
                else []
            )
            originals = {s.task_id: s for s in variants}
            for row in rows:
                source_row = originals.get(row.task_id)
                if not source_row or (row.messages, row.group_id, row.split) != (
                    source_row.messages,
                    source_row.group_id,
                    source_row.split,
                ):
                    raise ValueError("Variant checkpoint mismatch")
            if len({s.task_id for s in rows}) != len(rows):
                raise ValueError("Duplicate variant checkpoint")
            completed = {s.task_id for s in rows}
            job = job.model_copy(
                update={
                    "total": len(variants),
                    "completed": len(rows),
                    "stage": "distill",
                }
            )
            await self.save(job)
            for sample in variants:
                if sample.task_id in completed:
                    continue
                observations = []
                offset = int(
                    hashlib.sha256(sample.task_id.encode()).hexdigest()[:8], 16
                ) % len(manifest.configurations)
                order = (
                    manifest.configurations[offset:] + manifest.configurations[:offset]
                )
                for config in order:
                    response, job = await self._generation(
                        user, job, manifest, config.config_id, sample.messages
                    )
                    result = grade(sample.grading, response.text, sample.gold)
                    observations.append(
                        Observation(
                            config_id=config.config_id,
                            qualified=result.qualified,
                            usd=response.usd,
                            latency_ms=response.latency_ms,
                            input_tokens=response.input_tokens,
                            output_tokens=response.output_tokens,
                            label_source=result.label_source,
                            grader_version=result.grader_version,
                            grade_metrics=result.metrics,
                            response_sha256=hashlib.sha256(
                                response.text.encode()
                            ).hexdigest(),
                        )
                    )
                aligned = {o.config_id: o for o in observations}
                rows.append(
                    MultiSample(
                        task_id=sample.task_id,
                        group_id=sample.group_id,
                        domain=sample.domain,
                        split="train",
                        messages=sample.messages,
                        observations=tuple(
                            aligned[c.config_id] for c in manifest.configurations
                        ),
                    )
                )
                atomic_text(
                    checkpoint,
                    json.dumps(
                        [r.model_dump(mode="json") for r in rows],
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
                job = job.model_copy(update={"completed": len(rows)})
                await self.save(job)
            job = job.model_copy(
                update={
                    "status": "succeeded",
                    "stage": "complete",
                    "ready_for_training": True,
                    "pilot_report": {
                        "conclusion": "MEASURED_TRAIN_VARIANTS_ONLY",
                        "import_eligible": False,
                        "independent_parent_groups": len({r.group_id for r in rows}),
                    },
                }
            )
        except asyncio.CancelledError:
            job = job.model_copy(
                update={"status": "interrupted", "error_code": "PROCESS_INTERRUPTED"}
            )
        except Exception as exc:  # noqa: BLE001 -- durable failure at worker boundary
            job = job.model_copy(
                update={
                    "status": "failed",
                    "error_code": exc.code
                    if isinstance(exc, AppError)
                    else "VARIANT_COLLECTION_FAILED",
                    "pilot_report": {
                        "conclusion": "INCOMPLETE_TRAIN_AUGMENTATION",
                        "import_eligible": False,
                    },
                }
            )
        await self.finish_job(job)


if __name__ == "__main__":
    runner.RouterTrainingPipeline = TrainVariantPipeline
    runner.main()
