from typing import Any, Literal

from pydantic import Field

from app.contracts.dtos import DTO, CallRecord, RouteDecision


class ExecutionStep(DTO):
    sequence: int
    stage: str
    status: Literal["running", "succeeded", "skipped", "failed", "interrupted", "unknown"]
    at: str
    details: dict[str, Any] = Field(default_factory=dict)


class RequestExecution(DTO):
    request_id: str
    status: str
    error_code: str | None = None
    route: RouteDecision | None = None
    events: tuple[ExecutionStep, ...] = ()
    calls: tuple[CallRecord, ...] = ()
    legacy: bool = False
