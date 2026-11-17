from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings


class BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        maximum = (
            self.settings.max_upload_mb * 1024 * 1024 + 65536
            if scope["path"] == "/documents" and scope["method"] == "POST"
            else 262144
        )

        async def reject() -> None:
            response = JSONResponse(
                status_code=413,
                media_type="application/problem+json",
                content={
                    "type": "urn:pathya:error:too_large",
                    "title": "File or request too large",
                    "status": 413,
                    "detail": "Send a smaller chapter or request.",
                    "code": "too_large",
                },
            )
            await response(scope, receive, send)

        length = Headers(scope=scope).get("content-length")
        if length is not None:
            try:
                if int(length) < 0 or int(length) > maximum:
                    await reject()
                    return
            except ValueError:
                await reject()
                return
        received = 0
        started = False
        overflowed = False

        async def limited_receive() -> Message:
            nonlocal received, overflowed
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > maximum:
                    overflowed = True
                    raise BodyTooLarge()
            return message

        async def track_send(message: Message) -> None:
            nonlocal started
            if overflowed:
                raise BodyTooLarge()
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, track_send)
        except BodyTooLarge:
            if started:
                raise
            await reject()
