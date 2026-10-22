from typing import Literal

from app.contracts.dtos import DTO


class FeedbackRequest(DTO):
    event: Literal["dislike", "retry"]


class FeedbackResult(DTO):
    request_id: str
    recorded: bool = True
