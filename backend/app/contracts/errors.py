from typing import Literal


class AppError(Exception):
    def __init__(
        self,
        code: str,
        status: int,
        message: str,
        request_id: str | None = None,
        *,
        upstream_status: int | None = None,
        retry_after_seconds: float | None = None,
        dispatch_state: Literal["unknown", "not_dispatched", "rejected"] = "unknown",
    ):
        self.code = code
        self.status = status
        self.message = message
        self.request_id = request_id
        self.upstream_status = upstream_status
        self.retry_after_seconds = retry_after_seconds
        self.dispatch_state = dispatch_state
        super().__init__(message)

    @property
    def status_code(self) -> int:
        return self.status
