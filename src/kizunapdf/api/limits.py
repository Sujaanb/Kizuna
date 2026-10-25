"""Bound raw multipart requests before Starlette parses/spools uploaded files."""

import asyncio

from starlette.responses import JSONResponse


class UploadLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes
        self.slots = asyncio.Semaphore(2)

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/api/v1/documents"
        ):
            return await self.app(scope, receive, send)
        async with self.slots:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.max_bytes:
                    return await JSONResponse(
                        {"detail": "Upload body exceeds limit"}, status_code=413
                    )(scope, receive, send)
                if not message.get("more_body", False):
                    break
            sent = False

            async def bounded_receive():
                nonlocal sent
                if sent:
                    return await receive()
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, bounded_receive, send)
