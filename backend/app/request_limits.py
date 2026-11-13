"""Bound request bodies before FastAPI parses JSON and multipart uploads."""

from starlette.responses import JSONResponse


class RequestSizeLimitMiddleware:
    def __init__(self, app, default_limit: int = 2 * 1024 * 1024,
                 import_limit: int = 45 * 1024 * 1024):
        self.app = app
        self.default_limit = default_limit
        self.import_limit = import_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        limit = self.import_limit if path == "/admin/tasks/import" else self.default_limit
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    response = JSONResponse({"error": "Размер запроса превышает допустимый лимит"}, status_code=413)
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse({"error": "Некорректный Content-Length"}, status_code=400)
                await response(scope, receive, send)
                return

        chunks = []
        size = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                response = JSONResponse({"error": "Размер запроса превышает допустимый лимит"}, status_code=413)
                await response(scope, receive, send)
                return
            chunks.append(chunk)
            more_body = message.get("more_body", False)

        body = b"".join(chunks)
        delivered = False

        async def replay_body():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            # FileResponse and other streaming responses listen for a real
            # disconnect after consuming the request body. Do not synthesize
            # one here or the response stream is cancelled before its body.
            return await receive()

        await self.app(scope, replay_body, send)
