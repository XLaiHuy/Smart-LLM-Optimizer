from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.dtos import Principal
from app.contracts.errors import AppError
from app.contracts.progress import ProcessingStep, ProgressStage, ProgressStatus, RequestProgress
from app.storage.database import Database
from app.storage.models import Attempt, Conversation, ProcessingEvent


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


async def close_steps(db: AsyncSession, request_id: str, status: ProgressStatus) -> None:
    await db.execute(
        update(ProcessingEvent)
        .where(ProcessingEvent.request_id == request_id, ProcessingEvent.status == "running")
        .values(status=status, finished_at=timestamp())
    )


class SqlProgressStore:
    def __init__(self, db: Database):
        self.db = db

    async def start(self, request_id: str, stage: ProgressStage) -> None:
        async with self.db.write() as db:
            attempt = await db.get(Attempt, request_id)
            if attempt is None or attempt.status != "running" or not attempt.session_id:
                return
            await close_steps(db, request_id, "succeeded")
            db.add(
                ProcessingEvent(
                    request_id=request_id,
                    session_id=attempt.session_id,
                    stage=stage,
                    status="running",
                    started_at=timestamp(),
                )
            )

    async def finish(self, request_id: str, status: ProgressStatus) -> None:
        async with self.db.write() as db:
            await close_steps(db, request_id, status)

    async def read(
        self,
        principal: Principal,
        session_id: str,
        *,
        client_request_id: str | None = None,
        request_id: str | None = None,
    ) -> RequestProgress:
        async with self.db.sessions() as db:
            owned = await db.get(Conversation, session_id)
            if owned is None or owned.owner_user_id != principal.id:
                raise AppError("NOT_FOUND", 404, "Session not found")
            query = select(Attempt).where(
                Attempt.session_id == session_id, Attempt.owner_user_id == principal.id
            )
            query = (
                query.where(Attempt.id == request_id)
                if request_id
                else query.where(Attempt.client_request_id == client_request_id)
            )
            attempt = await db.scalar(query)
            if attempt is None:
                return RequestProgress()
            rows = await db.scalars(
                select(ProcessingEvent)
                .where(ProcessingEvent.request_id == attempt.id)
                .order_by(ProcessingEvent.id)
            )
            events = tuple(
                ProcessingStep.model_validate(
                    dict(
                        sequence=i,
                        stage=row.stage,
                        status=row.status,
                        started_at=row.started_at,
                        finished_at=row.finished_at,
                    )
                )
                for i, row in enumerate(rows, 1)
            )
            return RequestProgress(
                request_id=attempt.id,
                status=attempt.status,
                current_stage=next(
                    (e.stage for e in reversed(events) if e.status == "running"), None
                ),
                events=events,
            )
