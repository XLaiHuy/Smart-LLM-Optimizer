from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.contracts.dtos import ErrorDetail, ErrorEnvelope


class RequestBoundaryMiddleware:
    """Bound request bodies before JSON parsing; retain no raw-body logs."""

    def __init__(self, app: ASGIApp, allowed_origins: tuple[str, ...]):
        self.app = app
        self.allowed_origins = allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        headers = Headers(scope=scope)
        source = receive
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE"):
            origin = headers.get("origin")
            if (origin and origin not in self.allowed_origins) or headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                await self.reject(
                    scope, receive, send, 403, "FORBIDDEN_ACTION", "Origin not allowed"
                )
                return
            chunks: list[bytes] = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > 512000:
                    await self.reject(
                        scope, receive, send, 413, "VALIDATION_ERROR", "Payload exceeds limit"
                    )
                    return
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            source = replay

        async def measured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                output = MutableHeaders(scope=message)
                output["Cache-Control"] = "no-store"
                output["X-Content-Type-Options"] = "nosniff"
                output["Server-Timing"] = f"app;dur={(perf_counter() - started) * 1000:.3f}"
            await send(message)

        await self.app(scope, source, measured_send)

    @staticmethod
    async def reject(
        scope: Scope, receive: Receive, send: Send, status: int, code: str, message: str
    ) -> None:
        response = JSONResponse(
            ErrorEnvelope(error=ErrorDetail(code=code, message=message)).model_dump(mode="json"),
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)
