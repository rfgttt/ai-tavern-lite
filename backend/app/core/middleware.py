from __future__ import annotations

import base64
import json
import time
from collections import defaultdict, deque

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings
from .security import secure_equals


def _json_response(status: int, detail: str, extra_headers: list[tuple[bytes, bytes]] | None = None):
    payload = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(payload)).encode("ascii")),
        (b"cache-control", b"no-store"),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    return payload, headers


async def _send_json(send: Send, status: int, detail: str, extra_headers=None) -> None:
    payload, headers = _json_response(status, detail, extra_headers)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


class BasicAuthMiddleware:
    """Protect the application with HTTP Basic auth when enabled."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.auth_enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if path in settings.auth_exempt_paths or method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        authorization = Headers(scope=scope).get("authorization", "")
        valid = False
        if authorization.lower().startswith("basic "):
            try:
                decoded = base64.b64decode(authorization.split(" ", 1)[1], validate=True).decode("utf-8")
                username, password = decoded.split(":", 1)
                configured_password = settings.auth_password.get_secret_value()
                valid = secure_equals(username, settings.auth_username) and secure_equals(
                    password, configured_password
                )
            except (ValueError, UnicodeDecodeError):
                valid = False

        if not valid:
            await _send_json(
                send,
                401,
                "需要登录后访问",
                [(b"www-authenticate", b'Basic realm="AI Tavern", charset="UTF-8"')],
            )
            return

        await self.app(scope, receive, send)


class RequestSizeLimitMiddleware:
    """Reject oversized JSON and multipart requests before parsing them."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "").lower()
        content_length = headers.get("content-length")
        limit = settings.max_request_body_bytes
        if "application/json" in content_type:
            limit = settings.max_json_body_bytes
        elif "multipart/form-data" in content_type:
            if scope.get("path", "") == "/api/backups/restore":
                limit = settings.max_backup_size_mb * 1024 * 1024 + 1024 * 1024
            else:
                limit = settings.max_upload_size_mb * 1024 * 1024 + 1024 * 1024

        if content_length:
            try:
                if int(content_length) > limit:
                    await _send_json(send, 413, "请求体过大")
                    return
            except ValueError:
                await _send_json(send, 400, "Content-Length 无效")
                return

        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await _send_json(send, 413, "请求体过大")


class RequestBodyTooLarge(Exception):
    pass


class InMemoryRateLimitMiddleware:
    """Single-worker sliding-window limiter for API and generation endpoints."""

    def __init__(self, app: ASGIApp):
        self.app = app
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._last_cleanup = 0.0

    @staticmethod
    def _client_key(scope: Scope) -> str:
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    def _allow(self, key: tuple[str, str], limit: int, window: int, now: float) -> tuple[bool, int]:
        bucket = self._buckets[key]
        cutoff = now - window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window - (now - bucket[0])) + 1)
            return False, retry_after
        bucket.append(now)
        return True, 0

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        stale_before = now - max(settings.rate_limit_window_seconds, settings.ai_rate_limit_window_seconds)
        for key in list(self._buckets):
            bucket = self._buckets[key]
            while bucket and bucket[0] <= stale_before:
                bucket.popleft()
            if not bucket:
                self._buckets.pop(key, None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if method == "OPTIONS" or path in settings.auth_exempt_paths:
            await self.app(scope, receive, send)
            return
        if not settings.auth_enabled and not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        self._cleanup(now)
        client = self._client_key(scope)
        allowed, retry_after = self._allow(
            (client, "api"),
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
            now,
        )
        if not allowed:
            await _send_json(
                send,
                429,
                "请求过于频繁，请稍后重试",
                [(b"retry-after", str(retry_after).encode("ascii"))],
            )
            return

        if path in settings.ai_rate_limit_paths:
            allowed, retry_after = self._allow(
                (client, "ai"),
                settings.ai_rate_limit_requests,
                settings.ai_rate_limit_window_seconds,
                now,
            )
            if not allowed:
                await _send_json(
                    send,
                    429,
                    "模型请求过于频繁，请稍后重试",
                    [(b"retry-after", str(retry_after).encode("ascii"))],
                )
                return

        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
                headers.setdefault(
                    "Content-Security-Policy",
                    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                    "script-src 'self'; connect-src 'self'; font-src 'self' data:; object-src 'none'; "
                    "base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
                )
                if settings.is_production:
                    headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
                if scope.get("path", "").startswith("/api/"):
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)
