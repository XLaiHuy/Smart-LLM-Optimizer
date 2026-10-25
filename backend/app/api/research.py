from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.analytics.service import administrator
from app.api.routes import ContainerDep, UserDep
from app.contracts.errors import AppError
from app.contracts.research import (
    AblationRequest,
    AblationRunResponse,
    LabModule,
    OptimizerLabInfo,
    ReconcileRequest,
    ResearchConfigs,
    ResearchPreflight,
    ResearchRequest,
    ResearchRunInfo,
    ResearchSummary,
    TrialResult,
)
from app.contracts.training import (
    TrainingInfo,
    TrainingJob,
    TrainingRequest,
    TrainingResume,
    TrainingReviewCase,
    TrainingReviews,
)
from app.routing.experiments.exports import encode_export

router = APIRouter(prefix="/v1")


@router.get("/research/training")
def training_info(c: ContainerDep, user: UserDep) -> TrainingInfo:
    return c.training.info(user)


@router.get("/research/training/latest")
async def latest_training(c: ContainerDep, user: UserDep) -> TrainingJob | None:
    return await c.training.latest(user)


@router.post("/research/training/jobs", status_code=202)
async def start_training(body: TrainingRequest, c: ContainerDep, user: UserDep) -> TrainingJob:
    return await c.training.start(user, body)


@router.get("/research/training/jobs/{job_id}")
async def training_job(job_id: str, c: ContainerDep, user: UserDep) -> TrainingJob:
    return await c.training.get(user, job_id)


@router.post("/research/training/jobs/{job_id}/import")
async def import_training(job_id: str, c: ContainerDep, user: UserDep) -> TrainingJob:
    return await c.training.import_job(user, job_id)


@router.post("/research/training/jobs/{job_id}/resume", status_code=202)
async def resume_training(
    job_id: str, body: TrainingResume, c: ContainerDep, user: UserDep
) -> TrainingJob:
    return await c.training.resume(user, job_id, body)


@router.get("/research/training/jobs/{job_id}/reviews")
async def training_reviews(job_id: str, c: ContainerDep, user: UserDep) -> list[TrainingReviewCase]:
    return [
        TrainingReviewCase.model_validate(r) for r in await c.training.review_queue(user, job_id)
    ]


@router.post("/research/training/jobs/{job_id}/reviews")
async def submit_training_reviews(
    job_id: str, body: TrainingReviews, c: ContainerDep, user: UserDep
) -> TrainingJob:
    return await c.training.review(user, job_id, body)


@router.get("/research/training/jobs/{job_id}/artifact")
async def training_artifact(job_id: str, c: ContainerDep, user: UserDep) -> Response:
    raw = await c.training.artifact(user, job_id)
    return Response(
        raw,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="router-candidate.json"'},
    )


@router.get("/research/lab")
def optimizer_lab(user: UserDep) -> OptimizerLabInfo:
    administrator(user)
    return OptimizerLabInfo(
        modules=(
            LabModule(id="router", implemented=True, status="requires_qualified_data"),
            LabModule(id="prompt", implemented=False, status="not_implemented"),
            LabModule(id="memory", implemented=False, status="not_implemented"),
        ),
    )


@router.post("/research/ablation")
def run_ablation(body: AblationRequest, user: UserDep) -> AblationRunResponse:
    administrator(user)
    raise AppError("BENCHMARK_NOT_READY", 409, "A qualified paired evaluation runner is required")


@router.get("/research/configs")
def configs(
    c: ContainerDep,
    user: UserDep,
    suite_id: Literal[
        "huy-router-fixtures-v1", "huy-router-fixtures-v2"
    ] = "huy-router-fixtures-v1",
) -> ResearchConfigs:
    return c.research.configs(user, suite_id)


@router.post("/research/preflight")
def preflight(body: ResearchRequest, c: ContainerDep, user: UserDep) -> ResearchPreflight:
    return c.research.preflight(user, body)


@router.post("/research/runs", status_code=201)
async def create_run(body: ResearchRequest, c: ContainerDep, user: UserDep) -> ResearchRunInfo:
    return await c.research.create(user, body)


@router.get("/research/runs")
async def list_runs(
    c: ContainerDep,
    user: UserDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> tuple[ResearchRunInfo, ...]:
    return await c.research.list_runs(user, offset, limit)


@router.get("/research/runs/{run_id}")
async def get_run(run_id: str, c: ContainerDep, user: UserDep) -> ResearchRunInfo:
    return await c.research.get(user, run_id)


@router.get("/research/runs/{run_id}/trials")
async def trials(
    run_id: str,
    c: ContainerDep,
    user: UserDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> tuple[TrialResult, ...]:
    return await c.research.trials(user, run_id, offset, limit)


@router.post("/research/runs/{run_id}/cancel")
async def cancel(run_id: str, c: ContainerDep, user: UserDep) -> ResearchRunInfo:
    return await c.research.cancel(user, run_id)


@router.get("/research/runs/{run_id}/summary")
async def summary(run_id: str, c: ContainerDep, user: UserDep) -> ResearchSummary:
    return await c.research.summary(user, run_id)


@router.get("/research/runs/{run_id}/export")
async def export(
    run_id: str, c: ContainerDep, user: UserDep, format: Literal["csv", "jsonl"] = "jsonl"
) -> Response:
    run = await c.research.get(user, run_id)
    rows = await c.research.trials(user, run_id, 0, 1000)
    content = encode_export(run, rows, format)
    return Response(
        content,
        media_type="text/csv" if format == "csv" else "application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="research-{run_id}.{format}"'},
    )


@router.get("/admin/billing/unresolved")
async def unresolved(
    c: ContainerDep,
    user: UserDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, str]]:
    return await c.ledger.unresolved(user, offset, limit)


@router.post("/admin/billing/{reservation_id}/reconcile")
async def reconcile(
    reservation_id: str, body: ReconcileRequest, c: ContainerDep, user: UserDep
) -> dict[str, str]:
    audit = await c.ledger.reconcile(
        user, reservation_id, body.actual_usd, body.reason, body.evidence_reference
    )
    return {"reconciliation_id": audit}
