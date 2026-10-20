from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.routes import ContainerDep, UserDep
from app.contracts.research import (
    ReconcileRequest,
    ResearchConfigs,
    ResearchPreflight,
    ResearchRequest,
    ResearchRunInfo,
    ResearchSummary,
    TrialResult,
)
from app.routing.experiments.exports import encode_export

router = APIRouter(prefix="/v1")


@router.get("/research/configs")
def configs(c: ContainerDep, user: UserDep) -> ResearchConfigs:
    return c.research.configs(user)


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
