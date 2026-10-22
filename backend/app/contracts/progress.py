from typing import Literal

from .dtos import DTO

ProgressStage = Literal[
    "history", "documents", "prepare", "route", "generate", "calculate", "search"
]
ProgressStatus = Literal["running", "succeeded", "skipped", "failed", "interrupted"]


class ProcessingStep(DTO):
    sequence: int
    stage: ProgressStage
    status: ProgressStatus
    started_at: str
    finished_at: str | None = None


class RequestProgress(DTO):
    request_id: str | None = None
    status: str = "pending"
    current_stage: ProgressStage | None = None
    events: tuple[ProcessingStep, ...] = ()
