import csv
import io
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, File, Query, Response, UploadFile

from app.analytics.impact import BenchmarkImpact, benchmark_impact
from app.api.routes import ContainerDep, UserDep
from app.contracts.dtos import (
    AdminUser,
    Analytics,
    DocumentDetail,
    DocumentInfo,
    DocumentJob,
    JobRequest,
    QuotaUpdate,
)

router = APIRouter(prefix="/v1")


@router.post("/sessions/{session_id}/documents", response_model=DocumentInfo, status_code=201)
async def upload(
    session_id: str, user: UserDep, c: ContainerDep, file: Annotated[UploadFile, File()]
) -> DocumentInfo:
    return await c.documents.upload(user, session_id, file)


@router.get("/sessions/{session_id}/documents", response_model=tuple[DocumentInfo, ...])
async def documents(
    session_id: str,
    user: UserDep,
    c: ContainerDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> tuple[DocumentInfo, ...]:
    return await c.documents.list_owned(user, session_id, offset, limit)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def document(document_id: str, user: UserDep, c: ContainerDep) -> DocumentDetail:
    return await c.documents.detail(user, document_id)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, user: UserDep, c: ContainerDep) -> None:
    await c.documents.delete(user, document_id)


@router.post("/sessions/{session_id}/document-jobs", response_model=DocumentJob, status_code=202)
async def create_job(
    session_id: str, body: JobRequest, user: UserDep, c: ContainerDep
) -> DocumentJob:
    return await c.documents.create_job(user, session_id, body)


@router.get("/document-jobs/{job_id}", response_model=DocumentJob)
async def job(job_id: str, user: UserDep, c: ContainerDep) -> DocumentJob:
    return await c.documents.get_job(user, job_id)


@router.get("/usage", response_model=Analytics)
async def usage(
    user: UserDep,
    c: ContainerDep,
    start: date | None = None,
    end: date | None = None,
    project: bool = False,
    source: Literal["mock", "live"] | None = None,
    granularity: Literal["auto", "hour", "day", "month"] = "auto",
    model_id: str | None = None,
    session_id: str | None = None,
) -> Analytics:
    return await c.analytics.report(
        user,
        start,
        end,
        project,
        source,
        granularity=granularity,
        model_id=model_id,
        session_id=session_id,
    )


@router.get("/usage/export")
async def usage_export(
    user: UserDep,
    c: ContainerDep,
    start: date | None = None,
    end: date | None = None,
    project: bool = False,
    source: Literal["mock", "live"] | None = None,
    granularity: Literal["auto", "hour", "day", "month"] = "auto",
    model_id: str | None = None,
    session_id: str | None = None,
    format: Literal["json", "csv"] = "json",
    user_id: str | None = None,
) -> Response:
    report = await c.analytics.report(
        user,
        start,
        end,
        project,
        source,
        user_id=user_id,
        granularity=granularity,
        model_id=model_id,
        session_id=session_id,
    )
    if format == "json":
        return Response(
            report.model_dump_json(),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=usage.json"},
        )
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "dimension",
            "key",
            "calls",
            "input_tokens",
            "output_tokens",
            "usd",
            "known_subtotal_usd",
            "unknown_calls",
            "p50_ms",
            "p95_ms",
            "timing_samples",
            "reconciled_calls",
        ]
    )
    for dimension, rows in (
        ("total", (report.totals,)),
        ("timeseries_" + report.granularity, report.timeseries),
        ("model", report.models),
        ("category", report.categories),
        ("session", report.sessions),
    ):
        for row in rows:
            key = "'" + row.key if row.key.startswith(("=", "+", "-", "@", "\t", "\r")) else row.key
            writer.writerow(
                [
                    dimension,
                    key,
                    row.calls,
                    row.input_tokens,
                    row.output_tokens,
                    row.usd,
                    row.known_subtotal_usd,
                    row.unknown_calls,
                    row.p50_ms,
                    row.p95_ms,
                    row.timing_samples,
                    row.reconciled_calls,
                ]
            )
    return Response(
        "\ufeff" + buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage.csv"},
    )


@router.get("/admin/users", response_model=tuple[AdminUser, ...])
async def users(
    user: UserDep,
    c: ContainerDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> tuple[AdminUser, ...]:
    return await c.analytics.users(user, offset, limit)


@router.patch("/admin/users/{user_id}/quota", status_code=204)
async def quota(user_id: str, body: QuotaUpdate, user: UserDep, c: ContainerDep) -> None:
    await c.analytics.quota(user, user_id, body)


@router.get("/sessions/{session_id}/document-jobs", response_model=tuple[DocumentJob, ...])
async def jobs(
    session_id: str,
    user: UserDep,
    c: ContainerDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> tuple[DocumentJob, ...]:
    from sqlalchemy import select

    from app.storage.models import Attempt, StoredJob

    await c.documents.owned(user, session_id)
    async with c.db.sessions() as db:
        ids = list(
            await db.scalars(
                select(Attempt.id)
                .join(StoredJob, StoredJob.id == Attempt.id)
                .where(Attempt.session_id == session_id, Attempt.owner_user_id == user.id)
                .order_by(Attempt.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
    return tuple([await c.documents.get_job(user, id) for id in ids])


@router.get("/admin/users/{user_id}/usage", response_model=Analytics)
async def user_usage(
    user_id: str,
    user: UserDep,
    c: ContainerDep,
    start: date | None = None,
    end: date | None = None,
    source: Literal["mock", "live"] | None = None,
    granularity: Literal["auto", "hour", "day", "month"] = "auto",
    model_id: str | None = None,
) -> Analytics:
    return await c.analytics.report(
        user, start, end, source=source, user_id=user_id, granularity=granularity, model_id=model_id
    )


@router.get("/admin/benchmark-impact", response_model=BenchmarkImpact)
async def impact(
    user: UserDep,
    c: ContainerDep,
    start: date | None = None,
    end: date | None = None,
    user_id: str | None = None,
) -> BenchmarkImpact:
    return await benchmark_impact(c.db, c.settings, user, start, end, user_id)
