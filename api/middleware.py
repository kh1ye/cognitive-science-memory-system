"""Bound request buffering and preserve the service's cache policy."""

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_SIZE = 1_000_000


class RequestPolicyMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith("/api/")

        async def send_with_cache(message: Message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = (
                    "no-store" if is_api else "no-cache"
                )
            await send(message)

        async def reject(message: str):
            response = JSONResponse(
                {"error": "validation_error", "message": message}, status_code=400
            )
            await response(scope, receive, send_with_cache)

        if not is_api:
            await self.app(scope, receive, send_with_cache)
            return
        try:
            length = int(Headers(scope=scope).get("content-length", "0"))
        except ValueError:
            await reject("Content-Length 无效")
            return
        if length < 0:
            await reject("Content-Length 无效")
            return
        if length > MAX_BODY_SIZE:
            await reject("请求体过大")
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY_SIZE:
                await reject("请求体过大")
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay_body():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay_body, send_with_cache)
