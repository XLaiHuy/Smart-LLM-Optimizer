"""Owned, deduplicated serving feedback; separate rolling windows per artifact/model."""

from collections import OrderedDict
from threading import RLock

from sqlalchemy import select

from app.contracts.dtos import ExecutionRequest, Principal, RouteDecision
from app.contracts.errors import AppError
from app.contracts.feedback import FeedbackRequest, FeedbackResult
from app.storage.database import Database
from app.storage.models import Attempt, RouterOutcome
from app.storage.repositories import now


class RoutingDrift:
    def __init__(
        self,
        window: int = 200,
        warmup: int = 20,
        error_threshold: float = 0.03,
        max_shift: float = 0.15,
    ):
        if not 1 <= warmup <= window or not 0 <= error_threshold <= 1 or not 0 <= max_shift <= 1:
            raise ValueError("Invalid drift window/threshold configuration")
        self.window, self.warmup = window, warmup
        self.error_threshold, self.max_shift = error_threshold, max_shift
        self.windows: OrderedDict[tuple[str, str], OrderedDict[str, bool]] = OrderedDict()
        self.lock = RLock()

    def record(self, artifact: str, config: str, request_id: str, failed: bool) -> None:
        with self.lock:
            values = self.windows.setdefault((artifact, config), OrderedDict())
            if len(self.windows) > 64:
                self.windows.popitem(last=False)
            # Repeated feedback updates one observation without making it a new request.
            values[request_id] = failed
            while len(values) > self.window:
                values.popitem(last=False)

    def shift(self, artifact: str, config: str) -> float:
        with self.lock:
            values: dict[str, bool] = self.windows.get((artifact, config), {})
            if len(values) < self.warmup:
                return 0.0
            return min(
                self.max_shift,
                max(0, sum(values.values()) / len(values) - self.error_threshold) * 2,
            )


class RouterFeedbackService:
    def __init__(self, db: Database, drift: RoutingDrift):
        self.db, self.drift = db, drift

    async def start(self) -> None:
        async with self.db.sessions() as db:
            rows = list(
                await db.scalars(
                    select(RouterOutcome).order_by(RouterOutcome.created_at.desc()).limit(12800)
                )
            )
        for row in reversed(rows):
            self.drift.record(
                row.artifact_hash,
                row.config_id,
                row.request_id,
                row.failed or row.tool_error or row.dislike or row.retry,
            )

    async def observe(
        self,
        execution: ExecutionRequest,
        route: RouteDecision,
        *,
        success: bool,
        tool_error: bool = False,
    ) -> None:
        if (
            execution.namespace != "chat"
            or execution.execution_source != "live"
            or not route.ml_artifact_hash
            or not route.stages
        ):
            return
        async with self.db.write() as db:
            row = await db.get(RouterOutcome, execution.request_id)
            if row is None:
                row = RouterOutcome(
                    request_id=execution.request_id,
                    owner_user_id=execution.principal.id,
                    artifact_hash=route.ml_artifact_hash,
                    config_id=route.config_id,
                    failed=not success,
                    tool_error=tool_error,
                    dislike=False,
                    retry=False,
                    created_at=now(),
                )
                db.add(row)
            else:
                row.failed, row.tool_error = row.failed or not success, row.tool_error or tool_error
            failed = row.failed or row.tool_error or row.dislike or row.retry
        self.drift.record(route.ml_artifact_hash, route.config_id, execution.request_id, failed)

    async def feedback(
        self, user: Principal, request_id: str, body: FeedbackRequest
    ) -> FeedbackResult:
        if body.event not in ("dislike", "retry"):
            raise AppError("VALIDATION_ERROR", 422, "Feedback event must be dislike or retry")
        async with self.db.write() as db:
            attempt = await db.get(Attempt, request_id)
            row = await db.get(RouterOutcome, request_id)
            if (
                not attempt
                or attempt.owner_user_id != user.id
                or not row
                or row.owner_user_id != user.id
            ):
                raise AppError("TRACE_NOT_FOUND", 404, "Serving observation not found")
            if body.event == "dislike":
                row.dislike = True
            else:
                row.retry = True
            key = row.artifact_hash, row.config_id
        async with self.db.sessions() as db:
            recent = list(
                await db.scalars(
                    select(RouterOutcome)
                    .where(RouterOutcome.artifact_hash == key[0], RouterOutcome.config_id == key[1])
                    .order_by(RouterOutcome.created_at.desc(), RouterOutcome.request_id.desc())
                    .limit(self.drift.window)
                )
            )
        with self.drift.lock:
            self.drift.windows[key] = OrderedDict(
                (r.request_id, r.failed or r.tool_error or r.dislike or r.retry)
                for r in reversed(recent)
            )
        return FeedbackResult(request_id=request_id)
