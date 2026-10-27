import logging
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.extended import router as extended_router
from app.api.middleware import RequestBoundaryMiddleware
from app.api.research import router as research_router
from app.api.routes import router
from app.composition import Container
from app.config import Settings
from app.contracts.dtos import ErrorDetail, ErrorEnvelope
from app.contracts.errors import AppError


def error_response(
    code: str,
    status: int,
    message: str,
    request_id: str | None = None,
    retry_after_seconds: float | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code=code,
                message=message,
                request_id=request_id,
                retry_after_seconds=retry_after_seconds,
            )
        ).model_dump(mode="json"),
        headers={"Retry-After": str(max(1, math.ceil(retry_after_seconds)))}
        if retry_after_seconds is not None
        else None,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    services = Container(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=config.log_level)
        try:
            async with services.db.sessions() as session:
                await session.execute(text("SELECT version_num FROM alembic_version"))
                integrity = await session.execute(text("PRAGMA quick_check"))
                if integrity.scalars().all() != ["ok"]:
                    raise RuntimeError(
                        "Database integrity check failed; restore a verified snapshot"
                    )
            await services.sessions.recover_interrupted()
        except OperationalError as exc:
            await services.db.close()
            raise RuntimeError(
                "Database not migrated. Run npm run db:migrate from repository root."
            ) from exc
        await services.router_feedback.start()
        await services.documents.start()
        await services.research.start()
        try:
            yield
        finally:
            await services.training.close()
            await services.research.close()
            await services.documents.close()
            if services.live:
                await services.live.close()
            await services.db.close()

    app = FastAPI(
        title="Smart LLM Optimizer",
        version="0.2.0",
        lifespan=lifespan,
        responses={
            s: {"model": ErrorEnvelope} for s in (401, 403, 404, 409, 413, 422, 429, 502, 503, 504)
        },
    )
    app.state.container = services
    app.state.login_buckets = {}

    app.add_middleware(
        RequestBoundaryMiddleware,
        allowed_origins=config.allowed_origins,
        max_upload_bytes=config.max_file_bytes + 65536,
    )

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            exc.code, exc.status, exc.message, exc.request_id, exc.retry_after_seconds
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response("VALIDATION_ERROR", 422, "Invalid request fields or policy/flags")

    @app.exception_handler(SQLAlchemyError)
    async def storage_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # A failed error-persistence transaction must still return the API envelope.
        # Never release reservations or infer that a provider call was free here.
        logging.getLogger(__name__).error("Storage request failed: %s", type(exc).__name__)
        return error_response("DEPENDENCY_UNAVAILABLE", 503, "Storage is unavailable")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(
            "VALIDATION_ERROR" if exc.status_code == 422 else "HTTP_ERROR",
            exc.status_code,
            "Request not accepted",
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "provider_mode": config.provider_mode, "version": "0.2.0"}

    app.include_router(router)
    app.include_router(extended_router)
    app.include_router(research_router)
    return app


app = create_app()
