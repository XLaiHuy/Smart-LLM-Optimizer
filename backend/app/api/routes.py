import json
from collections import deque
from collections.abc import AsyncIterator
from time import monotonic
from typing import Annotated, cast

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.composition import Container
from app.contracts.dtos import (
    ChatRequest,
    ChatResponse,
    LoginRequest,
    ModelConfiguration,
    Overview,
    PlatformInfo,
    Principal,
    PublicModel,
    SessionCreate,
    SessionDetail,
    SessionInfo,
    ToolEvent,
)
from app.contracts.errors import AppError
from app.contracts.feedback import FeedbackRequest, FeedbackResult
from app.contracts.progress import RequestProgress

router = APIRouter(prefix="/v1")
COOKIE_NAME = "smartllm_session"


def container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(container)]


async def principal(
    c: ContainerDep, smartllm_session: Annotated[str | None, Cookie()] = None
) -> Principal:
    return await c.auth.resolve(smartllm_session)


UserDep = Annotated[Principal, Depends(principal)]


@router.get("/platform-info")
def platform_info(c: ContainerDep) -> PlatformInfo:
    allowlist = (
        ("gpt-6-luna", "GPT-6 Luna"),
        ("gpt-5.6-luna", "GPT-5.6 Luna"),
        ("gpt-5.6-terra", "GPT-5.6 Terra"),
    )
    configured = {m.model_id for m in c.registry.configurations if m.execution_source == "live"}
    return PlatformInfo(
        execution_mode=c.settings.provider_mode,
        models=tuple(
            PublicModel(name=name, status="configured" if model in configured else "planned")
            for model, name in allowlist
        ),
        tools_available=c.settings.provider_mode == "mock" or c.settings.tools_live_approved,
    )


@router.get("/sessions/{session_id}/progress")
async def progress(
    session_id: str,
    c: ContainerDep,
    user: UserDep,
    client_request_id: str = Query(min_length=1, max_length=128),
) -> RequestProgress:
    return await c.progress.read(user, session_id, client_request_id=client_request_id)


@router.get("/sessions/{session_id}/requests/{request_id}/progress")
async def saved_progress(
    session_id: str, request_id: str, c: ContainerDep, user: UserDep
) -> RequestProgress:
    return await c.progress.read(user, session_id, request_id=request_id)


@router.get("/sessions/{session_id}/tool-activity")
async def tool_activity(
    session_id: str,
    c: ContainerDep,
    user: UserDep,
    client_request_id: str = Query(min_length=1, max_length=128),
) -> tuple[ToolEvent, ...]:
    return await c.tools.activity(user, session_id, client_request_id)


@router.post("/auth/login", response_model=Principal)
async def login(
    body: LoginRequest, request: Request, response: Response, c: ContainerDep
) -> Principal:
    # Local single-worker throttle; expire buckets and cap cardinality.
    buckets: dict[str, deque[float]] = request.app.state.login_buckets
    timestamp = monotonic()
    for key in list(buckets):
        while buckets[key] and timestamp - buckets[key][0] >= 60:
            buckets[key].popleft()
        if not buckets[key]:
            del buckets[key]
    key = request.client.host if request.client else "local"
    if len(buckets) >= 4096 and key not in buckets:
        raise AppError("RATE_LIMITED", 429, "Too many login attempts")
    attempts = buckets.setdefault(key, deque())
    if len(attempts) >= 10:
        raise AppError("RATE_LIMITED", 429, "Too many login attempts")
    attempts.append(timestamp)
    user, token = await c.auth.login(body.username, body.password)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=c.settings.cookie_secure,
        max_age=c.settings.auth_session_hours * 3600,
        path="/",
    )
    return user


@router.post("/auth/logout", status_code=204)
async def logout(
    response: Response, c: ContainerDep, smartllm_session: Annotated[str | None, Cookie()] = None
) -> None:
    await c.auth.logout(smartllm_session)
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=c.settings.cookie_secure
    )


@router.get("/auth/me", response_model=Principal)
async def me(user: UserDep) -> Principal:
    return user


@router.get("/models", response_model=tuple[ModelConfiguration, ...])
async def models(c: ContainerDep, user: UserDep) -> tuple[ModelConfiguration, ...]:
    return c.registry.configurations


@router.post("/sessions", response_model=SessionInfo, status_code=201)
async def create_session(body: SessionCreate, c: ContainerDep, user: UserDep) -> SessionInfo:
    return await c.sessions.create(user, body.title)


@router.get("/sessions", response_model=tuple[SessionInfo, ...])
async def list_sessions(
    c: ContainerDep,
    user: UserDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> tuple[SessionInfo, ...]:
    return await c.sessions.list_owned(user, offset, limit)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, c: ContainerDep, user: UserDep) -> SessionDetail:
    return await c.sessions.detail(user, session_id)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, c: ContainerDep, user: UserDep) -> None:
    await c.sessions.purge(user, session_id)


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, c: ContainerDep, user: UserDep) -> ChatResponse:
    return await c.orchestrator.execute(user, body)


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    c: ContainerDep,
    user: UserDep,
) -> StreamingResponse:
    async def sse_generator() -> AsyncIterator[str]:
        try:
            async for event in c.orchestrator.execute_stream(
                user, body, is_disconnected=request.is_disconnected
            ):
                event_name = event.get("event", "message")
                payload = json.dumps(event.get("data", {}), ensure_ascii=False)
                yield f"event: {event_name}\ndata: {payload}\n\n"
        except AppError as exc:
            err_data = json.dumps({"code": exc.code, "message": exc.message}, ensure_ascii=False)
            yield f"event: error\ndata: {err_data}\n\n"
        except Exception as exc:
            err_data = json.dumps({"code": "INTERNAL_ERROR", "message": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {err_data}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/traces/{request_id}", response_model=ChatResponse)
async def trace(request_id: str, c: ContainerDep, user: UserDep) -> ChatResponse:
    return await c.traces.get_owned(user, request_id)


@router.get("/overview", response_model=Overview)
async def overview(c: ContainerDep, user: UserDep) -> Overview:
    return await c.traces.overview(user)


@router.post("/traces/{request_id}/feedback")
async def router_feedback(
    request_id: str, body: FeedbackRequest, c: ContainerDep, user: UserDep
) -> FeedbackResult:
    return await c.router_feedback.feedback(user, request_id, body)
