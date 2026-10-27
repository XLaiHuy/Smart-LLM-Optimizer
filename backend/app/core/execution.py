import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.contracts.dtos import Principal, RouteDecision
from app.contracts.errors import AppError
from app.contracts.execution import ExecutionStep, RequestExecution
from app.storage.database import Database
from app.storage.models import Attempt, ExecutionEvent


class ExecutionJournal:
    def __init__(self, db: Database):
        self.db = db

    async def record(self, request_id: str, stage: str, status: str, **details: Any) -> None:
        # Observability must never change dispatch/settlement or turn a committed
        # answer into a retryable failure. Missing evidence remains unknown.
        try:
            async with self.db.write() as db:
                db.add(
                    ExecutionEvent(
                        request_id=request_id,
                        stage=stage,
                        status=status,
                        at=datetime.now(UTC).isoformat(),
                        details_json=json.dumps(details),
                    )
                )
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Execution event unavailable request=%s stage=%s", request_id, stage
            )

    async def read(self, principal: Principal, request_id: str) -> RequestExecution:
        async with self.db.sessions() as db:
            attempt = await db.get(Attempt, request_id)
            if (
                attempt is None
                or attempt.owner_user_id != principal.id
                or attempt.session_id is None
            ):
                raise AppError("TRACE_NOT_FOUND", 404, "Execution not found")
            rows = list(
                await db.scalars(
                    select(ExecutionEvent)
                    .where(ExecutionEvent.request_id == request_id)
                    .order_by(ExecutionEvent.id)
                )
            )
            route = None
            for row in rows:
                details = json.loads(row.details_json)
                if "route" in details:
                    route = RouteDecision.model_validate(details["route"])
            if route is None and attempt.response_json:
                route = RouteDecision.model_validate(json.loads(attempt.response_json)["route"])
            return RequestExecution(
                request_id=request_id,
                status=attempt.status,
                error_code=attempt.error_code,
                route=route,
                legacy=not rows,
                events=tuple(
                    ExecutionStep.model_validate(
                        dict(
                            sequence=i,
                            stage=row.stage,
                            status=row.status,
                            at=row.at,
                            details=json.loads(row.details_json),
                        )
                    )
                    for i, row in enumerate(rows, 1)
                ),
            )
