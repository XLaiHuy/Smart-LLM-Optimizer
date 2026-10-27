from datetime import UTC, datetime
from statistics import median
from time import perf_counter
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlalchemy.sql.elements import ColumnElement

from app.contracts.dtos import (
    ChatResponse,
    DerivedMemory,
    ExecutionRequest,
    Message,
    Overview,
    Principal,
    RecentRequest,
    SessionDetail,
    SessionInfo,
    SessionSnapshot,
)
from app.contracts.errors import AppError
from app.storage.database import Database
from app.storage.models import (
    Attempt,
    Conversation,
    Document,
    DocumentChunk,
    InferenceCall,
    MemoryRevision,
    OptimizationEvent,
    Reservation,
    StoredJob,
    StoredMessage,
    ToolInvocation,
)
from app.storage.progress import close_steps


def now() -> str:
    return datetime.now(UTC).isoformat()


def uid() -> str:
    return str(uuid4())


def info(row: Conversation) -> SessionInfo:
    return SessionInfo(
        id=row.id,
        title=row.title,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
        active=row.active_attempt_id is not None,
    )


class SqlSessionStore:
    def __init__(self, db: Database):
        self.db = db

    async def _owned(self, db: AsyncSession, principal: Principal, session_id: str) -> Conversation:
        row = await db.get(Conversation, session_id)
        if row is None or row.owner_user_id != principal.id:
            raise AppError("SESSION_NOT_FOUND", 404, "Session not found")
        return row

    async def create(self, principal: Principal, title: str) -> SessionInfo:
        try:
            async with self.db.write() as db:
                timestamp = now()
                row = Conversation(
                    id=uid(),
                    owner_user_id=principal.id,
                    title=title,
                    revision=0,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                db.add(row)
                return info(row)
        except Exception as exc:
            if "tool_recovery_required" in str(exc):
                async with self.db.write() as db:
                    timestamp = now()
                    session_id = uid()
                    await db.execute(
                        text(
                            "INSERT INTO sessions (id, owner_user_id, title, revision, created_at, updated_at) "
                            "VALUES (:id, :owner_user_id, :title, 0, :created_at, :updated_at)"
                        ),
                        {
                            "id": session_id,
                            "owner_user_id": principal.id,
                            "title": title,
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        },
                    )
                    return SessionInfo(
                        id=session_id,
                        title=title,
                        revision=0,
                        created_at=timestamp,
                        updated_at=timestamp,
                        active=False,
                    )
            raise

    async def list_owned(
        self, principal: Principal, offset: int = 0, limit: int = 50
    ) -> tuple[SessionInfo, ...]:
        async with self.db.sessions() as db:
            rows = await db.scalars(
                select(Conversation)
                .where(Conversation.owner_user_id == principal.id)
                .order_by(Conversation.updated_at.desc(), Conversation.id)
                .offset(offset)
                .limit(limit)
            )
            return tuple(info(row) for row in rows)

    async def detail(self, principal: Principal, session_id: str) -> SessionDetail:
        async with self.db.sessions() as db:
            row = await self._owned(db, principal, session_id)
            messages = await db.scalars(
                select(StoredMessage)
                .where(StoredMessage.session_id == session_id)
                .order_by(StoredMessage.position)
            )
            active_attempt = (
                await db.get(Attempt, row.active_attempt_id) if row.active_attempt_id else None
            )
            return SessionDetail(
                **info(row).model_dump(),
                active_client_request_id=active_attempt.client_request_id
                if active_attempt
                else None,
                messages=tuple(
                    Message(
                        id=m.id,
                        role=cast("LiteralRole", m.role),
                        content=m.content,
                        request_id=m.request_id,
                    )
                    for m in messages
                ),
            )

    async def snapshot(self, principal: Principal, session_id: str) -> SessionSnapshot:
        detail = await self.detail(principal, session_id)
        derived = await SqlMemoryStore(self.db).load(principal, session_id)
        return SessionSnapshot(
            owner_user_id=principal.id,
            session_id=session_id,
            revision=detail.revision,
            raw_turns=detail.messages,
            summaries=derived.summaries,
            facts=derived.facts,
        )

    async def purge(self, principal: Principal, session_id: str) -> None:
        async with self.db.write() as db:
            row = await self._owned(db, principal, session_id)
            if row.active_attempt_id:
                raise AppError("SESSION_BUSY", 409, "Session is busy")
            await db.execute(
                text(
                    "DELETE FROM document_fts WHERE chunk_id IN (SELECT c.id FROM document_chunks c JOIN documents d ON d.id=c.document_id WHERE d.session_id=:id)"
                ),
                {"id": session_id},
            )
            await db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id.in_(
                        select(Document.id).where(Document.session_id == session_id)
                    )
                )
            )
            await db.execute(delete(Document).where(Document.session_id == session_id))
            attempts = list(
                await db.scalars(select(Attempt).where(Attempt.session_id == session_id))
            )
            for attempt in attempts:
                await db.execute(
                    delete(ToolInvocation).where(ToolInvocation.operation_id == attempt.id)
                )
                await db.execute(delete(StoredJob).where(StoredJob.id == attempt.id))
                # Retain only minimal accounting/dedupe tombstones, purge all content.
                attempt.response_json = None
                attempt.session_id = None
                await db.execute(
                    delete(InferenceCall).where(InferenceCall.request_id == attempt.id)
                )
                await db.execute(
                    delete(OptimizationEvent).where(OptimizationEvent.request_id == attempt.id)
                )
            await db.flush()
            await db.execute(delete(StoredMessage).where(StoredMessage.session_id == session_id))
            await db.execute(delete(MemoryRevision).where(MemoryRevision.session_id == session_id))
            await db.delete(row)

    async def claim(self, req: ExecutionRequest, payload_hash: str) -> ChatResponse | None:
        async with self.db.write() as db:
            previous = await db.scalar(
                select(Attempt).where(
                    Attempt.owner_user_id == req.principal.id,
                    Attempt.client_request_id == req.request.client_request_id,
                )
            )
            if previous:
                if previous.payload_hash != payload_hash:
                    raise AppError(
                        "IDEMPOTENCY_CONFLICT", 409, "Request ID payload differs", previous.id
                    )
                if previous.status == "succeeded" and previous.response_json:
                    return ChatResponse.model_validate_json(previous.response_json)
                code = (
                    "REQUEST_IN_PROGRESS"
                    if previous.status == "running"
                    else "ATTEMPT_NOT_REPLAYABLE"
                )
                raise AppError(code, 409, "Attempt cannot be dispatched again", previous.id)
            row = await self._owned(db, req.principal, req.request.session_id)
            if row.active_attempt_id:
                raise AppError("SESSION_BUSY", 409, "Session is busy", row.active_attempt_id)
            db.add(
                Attempt(
                    id=req.request_id,
                    owner_user_id=req.principal.id,
                    session_id=row.id,
                    client_request_id=req.request.client_request_id,
                    payload_hash=payload_hash,
                    status="running",
                    dispatched=False,
                    execution_source=req.execution_source,
                    traffic_class=req.namespace,
                    created_at=now(),
                )
            )
            row.active_attempt_id = req.request_id
            return None

    async def mark_dispatched(self, request_id: str) -> None:
        async with self.db.write() as db:
            row = await db.get(Attempt, request_id)
            if row is None or row.status != "running":
                raise AppError("ATTEMPT_NOT_REPLAYABLE", 409, "Attempt not running", request_id)
            row.dispatched = True

    async def commit(self, req: ExecutionRequest, response: ChatResponse) -> ChatResponse:
        started = perf_counter()
        async with self.db.write() as db:
            row = await self._owned(db, req.principal, req.request.session_id)
            attempt = await db.get(Attempt, req.request_id)
            if (
                row.active_attempt_id != req.request_id
                or attempt is None
                or attempt.status != "running"
                or response.session_revision != row.revision + 1
            ):
                raise AppError("SESSION_BUSY", 409, "Session revision changed", req.request_id)
            position = row.revision * 2
            db.add_all(
                [
                    StoredMessage(
                        id=uid(),
                        session_id=row.id,
                        position=position,
                        role="user",
                        content=req.request.message,
                        request_id=req.request_id,
                    ),
                    StoredMessage(
                        id=uid(),
                        session_id=row.id,
                        position=position + 1,
                        role="assistant",
                        content=response.response.content,
                        request_id=req.request_id,
                    ),
                ]
            )
            for call in response.calls:
                db.add(
                    InferenceCall(
                        id=call.call_id,
                        request_id=req.request_id,
                        metadata_json=call.model_dump_json(),
                    )
                )
            for state in response.optimizations:
                db.add(
                    OptimizationEvent(
                        id=uid(), request_id=req.request_id, metadata_json=state.model_dump_json()
                    )
                )
            row.revision += 1
            row.active_attempt_id = None
            row.updated_at = now()
            job = await db.get(StoredJob, req.request_id)
            if job:
                job.progress = job.total
            await close_steps(db, req.request_id, "succeeded")
            attempt.status = "succeeded"
            if response.route.reason_code == "ROUTE_TOOL_RECOVERY" and not any(
                e.error_code in ("TOOL_ARGUMENTS_INVALID", "TOOL_NOT_ALLOWED")
                for e in response.tool_events
            ):
                row.tool_recovery_required = False
            attempt.response_json = response.model_dump_json()
            await db.flush()
            # Trace stops just before its own final update/commit. HTTP Server-Timing
            # includes the actual transaction commit; no mock trace is a research latency result.
            response = response.model_copy(
                update={
                    "timing": response.timing.model_copy(
                        update={
                            "e2e_ms": response.timing.e2e_ms + (perf_counter() - started) * 1000
                        }
                    )
                }
            )
            attempt.response_json = response.model_dump_json()
            attempt.e2e_ms = response.timing.e2e_ms
        return response

    async def fail(self, request_id: str, code: str) -> None:
        async with self.db.write() as db:
            attempt = await db.get(Attempt, request_id)
            if attempt and attempt.status == "running":
                await close_steps(db, request_id, "failed")
                attempt.status = "failed"
                attempt.error_code = code
                for reservation in await db.scalars(
                    select(Reservation).where(
                        Reservation.request_id == request_id,
                        Reservation.status.in_(("reserved", "dispatched")),
                    )
                ):
                    reservation.status = (
                        "released" if reservation.status == "reserved" else "unresolved"
                    )
                row = await db.get(Conversation, attempt.session_id) if attempt.session_id else None
                if row and row.active_attempt_id == request_id:
                    row.active_attempt_id = None

    async def recover_interrupted(self) -> None:
        async with self.db.write() as db:
            for tool in await db.scalars(
                select(ToolInvocation).where(ToolInvocation.status == "running")
            ):
                from app.contracts.dtos import ToolEvent

                event = ToolEvent.model_validate_json(tool.event_json)
                tool.status = "interrupted"
                tool.event_json = event.model_copy(
                    update={"status": "interrupted", "error_code": "PROCESS_INTERRUPTED"}
                ).model_dump_json()
        async with self.db.write() as db:
            for attempt in await db.scalars(select(Attempt).where(Attempt.status == "running")):
                await close_steps(db, attempt.id, "interrupted")
                attempt.status = "interrupted"
                attempt.error_code = "PROCESS_INTERRUPTED"
                row = await db.get(Conversation, attempt.session_id) if attempt.session_id else None
                if row and row.active_attempt_id == attempt.id:
                    row.active_attempt_id = None
                for reservation in await db.scalars(
                    select(Reservation).where(
                        Reservation.request_id == attempt.id,
                        Reservation.status.in_(("reserved", "dispatched")),
                    )
                ):
                    reservation.status = (
                        "unresolved"
                        if attempt.dispatched or reservation.status == "dispatched"
                        else "released"
                    )


class SqlMemoryStore:
    """Scoped persistence only; never extracts facts or invokes inference."""

    def __init__(self, db: Database):
        self.db = db

    async def load(self, principal: Principal, session_id: str) -> "DerivedMemory":
        async with self.db.sessions() as db:
            row = await db.get(Conversation, session_id)
            if row is None or row.owner_user_id != principal.id:
                raise AppError("SESSION_NOT_FOUND", 404, "Session not found")
            revision = await db.scalar(
                select(MemoryRevision)
                .where(
                    MemoryRevision.session_id == session_id, MemoryRevision.revision <= row.revision
                )
                .order_by(MemoryRevision.revision.desc())
                .limit(1)
            )
            return (
                DerivedMemory.model_validate_json(revision.snapshot_json)
                if revision
                else DerivedMemory(snapshot_revision=row.revision)
            )

    async def load_user_memories(
        self, execution_principal: str, exclude_session_id: str
    ) -> tuple[SessionSnapshot, ...]:
        """Load derived memories from the owner's other sessions only."""
        async with self.db.sessions() as db:
            latest = (
                select(
                    MemoryRevision.id.label("memory_id"),
                    func.row_number()
                    .over(
                        partition_by=MemoryRevision.session_id,
                        order_by=MemoryRevision.revision.desc(),
                    )
                    .label("position"),
                )
                .join(Conversation, Conversation.id == MemoryRevision.session_id)
                .where(
                    Conversation.owner_user_id == execution_principal,
                    Conversation.id != exclude_session_id,
                    MemoryRevision.revision <= Conversation.revision,
                )
                .subquery()
            )
            # One statement and one consistent read snapshot, rather than a
            # query per conversation. Filter owner and committed revision before
            # ranking so future/foreign memory cannot enter the result.
            records = await db.execute(
                select(Conversation, MemoryRevision)
                .join(MemoryRevision, MemoryRevision.session_id == Conversation.id)
                .join(latest, latest.c.memory_id == MemoryRevision.id)
                .where(latest.c.position == 1)
                .order_by(Conversation.updated_at.desc(), Conversation.id)
            )
            snapshots: list[SessionSnapshot] = []
            for session, revision in records:
                derived = DerivedMemory.model_validate_json(revision.snapshot_json)
                snapshots.append(
                    SessionSnapshot(
                        owner_user_id=execution_principal,
                        session_id=session.id,
                        revision=session.revision,
                        summaries=derived.summaries,
                        facts=derived.facts,
                    )
                )
            return tuple(snapshots)

    async def save(self, principal: Principal, session_id: str, state: "DerivedMemory") -> None:
        async with self.db.write() as db:
            row = await db.get(Conversation, session_id)
            if row is None or row.owner_user_id != principal.id:
                raise AppError("SESSION_NOT_FOUND", 404, "Session not found")
            if state.snapshot_revision != row.revision:
                raise AppError("IDEMPOTENCY_CONFLICT", 409, "Stale memory snapshot")
            committed = set(
                await db.scalars(
                    select(StoredMessage.id).where(StoredMessage.session_id == session_id)
                )
            )
            evidence = {
                message_id
                for summary in state.summaries
                for message_id in summary.covered_message_ids
            }
            evidence.update(
                message_id for fact in state.facts for message_id in fact.source_message_ids
            )
            if not evidence.issubset(committed):
                raise AppError(
                    "VALIDATION_ERROR", 422, "Memory evidence must reference committed turns"
                )
            previous = await db.scalar(
                select(MemoryRevision).where(
                    MemoryRevision.session_id == session_id,
                    MemoryRevision.revision == state.snapshot_revision,
                )
            )
            if previous:
                if previous.snapshot_json != state.model_dump_json():
                    raise AppError("IDEMPOTENCY_CONFLICT", 409, "Memory revision already committed")
                return
            db.add(
                MemoryRevision(
                    id=uid(),
                    session_id=session_id,
                    revision=state.snapshot_revision,
                    snapshot_json=state.model_dump_json(),
                )
            )


class SqlTraceStore:
    def __init__(self, db: Database):
        self.db = db

    async def get_owned(self, principal: Principal, request_id: str) -> ChatResponse:
        async with self.db.sessions() as db:
            row = await db.get(Attempt, request_id)
            if row is None or row.owner_user_id != principal.id or row.response_json is None:
                raise AppError("TRACE_NOT_FOUND", 404, "Trace not found")
            return ChatResponse.model_validate_json(row.response_json)

    async def overview(self, principal: Principal) -> Overview:
        async with self.db.sessions() as db:
            from app.analytics.epoch import current_epoch, product_attempts

            epoch = await current_epoch(db)
            filters: tuple[ColumnElement[bool], ...] = (
                Attempt.owner_user_id == principal.id, Attempt.research_run_id.is_(None)
            )
            if epoch:
                filters += (*product_attempts(), Attempt.created_at >= epoch.started_at)
            rows = list(
                await db.scalars(
                    select(Attempt)
                    .options(
                        load_only(
                            Attempt.id,
                            Attempt.session_id,
                            Attempt.status,
                            Attempt.created_at,
                            Attempt.e2e_ms,
                            Attempt.execution_source,
                        )
                    )
                    .where(*filters)
                    .order_by(Attempt.created_at.desc())
                )
            )
            timings = [r.e2e_ms for r in rows if r.e2e_ms is not None]
            recent = tuple(
                RecentRequest(
                    request_id=r.id,
                    session_id=r.session_id or "",
                    status=r.status,
                    created_at=r.created_at,
                    e2e_ms=r.e2e_ms,
                    execution_source=cast(Literal["mock", "live"], r.execution_source),
                )
                for r in rows[:20]
            )
            return Overview(
                execution_source="live"
                if any(r.execution_source == "live" for r in rows)
                else "mock",
                total_requests=len(rows),
                succeeded=sum(r.status == "succeeded" for r in rows),
                failed=sum(r.status in ("failed", "interrupted") for r in rows),
                active=sum(r.status == "running" for r in rows),
                median_latency_ms=median(timings) if timings else None,
                latency_sample_count=len(timings),
                recent_requests=recent,
            )


LiteralRole = Literal["system", "developer", "user", "assistant"]
