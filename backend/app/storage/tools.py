import hashlib

from sqlalchemy import select

from app.contracts.dtos import ExecutionRequest, Principal, ToolCall, ToolEvent
from app.contracts.errors import AppError
from app.storage.database import Database
from app.storage.models import Attempt, Conversation, ToolInvocation
from app.storage.repositories import now, uid


class SqlToolStore:
    def __init__(self, db: Database):
        self.db = db

    async def recovery_required(self, principal: Principal, session_id: str) -> bool:
        async with self.db.sessions() as db:
            row = await db.get(Conversation, session_id)
            if not row or row.owner_user_id != principal.id:
                raise AppError("SESSION_NOT_FOUND", 404, "Session not found")
            return row.tool_recovery_required

    async def claim(self, execution: ExecutionRequest, call: ToolCall) -> ToolEvent | None:
        if not call.call_id or len(call.call_id) > 128 or len(call.name) > 100:
            raise AppError("TOOL_ARGUMENTS_INVALID", 422, "Invalid tool call identity")
        digest = hashlib.sha256((call.name + "\n" + call.arguments).encode()).hexdigest()
        async with self.db.write() as db:
            owner = await db.get(Conversation, execution.request.session_id)
            attempt = await db.get(Attempt, execution.request_id)
            if (
                not owner
                or owner.owner_user_id != execution.principal.id
                or not attempt
                or owner.active_attempt_id != attempt.id
            ):
                raise AppError("SESSION_BUSY", 409, "Tool operation is not active")
            old = await db.scalar(
                select(ToolInvocation).where(
                    ToolInvocation.operation_id == execution.request_id,
                    ToolInvocation.call_id == call.call_id,
                )
            )
            if old:
                if old.payload_hash != digest:
                    raise AppError("TOOL_IDEMPOTENCY_CONFLICT", 409, "Tool call ID payload differs")
                if old.status in ("running", "interrupted"):
                    raise AppError("ATTEMPT_NOT_REPLAYABLE", 409, "Tool work cannot be replayed")
                return ToolEvent.model_validate_json(old.event_json)
            event = ToolEvent(
                call_id=call.call_id,
                name=call.name,
                status="running",
                arguments_json=call.arguments,
            )
            db.add(
                ToolInvocation(
                    id=uid(),
                    operation_id=execution.request_id,
                    session_id=execution.request.session_id,
                    call_id=call.call_id,
                    name=call.name,
                    payload_hash=digest,
                    event_json=event.model_dump_json(),
                    status="running",
                    created_at=now(),
                )
            )
        return None

    async def finish(self, execution: ExecutionRequest, event: ToolEvent) -> None:
        async with self.db.write() as db:
            row = await db.scalar(
                select(ToolInvocation).where(
                    ToolInvocation.operation_id == execution.request_id,
                    ToolInvocation.call_id == event.call_id,
                )
            )
            if not row:
                raise AppError("ATTEMPT_NOT_REPLAYABLE", 409, "Tool invocation missing")
            row.status, row.event_json = event.status, event.model_dump_json()
            if event.error_code in ("TOOL_ARGUMENTS_INVALID", "TOOL_NOT_ALLOWED"):
                conversation = await db.get(Conversation, execution.request.session_id)
                assert conversation
                conversation.tool_recovery_required = True

    async def activity(
        self, principal: Principal, session_id: str, client_request_id: str
    ) -> tuple[ToolEvent, ...]:
        await self.recovery_required(principal, session_id)
        async with self.db.sessions() as db:
            rows = await db.scalars(
                select(ToolInvocation)
                .join(Attempt, Attempt.id == ToolInvocation.operation_id)
                .where(
                    ToolInvocation.session_id == session_id,
                    Attempt.owner_user_id == principal.id,
                    Attempt.client_request_id == client_request_id,
                )
                .order_by(ToolInvocation.created_at, ToolInvocation.id)
            )
            return tuple(ToolEvent.model_validate_json(r.event_json) for r in rows)
