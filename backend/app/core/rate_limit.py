from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.redis import get_redis


class FixedWindowRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, exempt_paths: set[str] | None = None):
        super().__init__(app)
        self.exempt_paths = exempt_paths or {"/health", "/ready"}
        self._memory_counts: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.RATE_LIMIT_ENABLED or request.url.path in self.exempt_paths:
            return await call_next(request)

        limit = settings.RATE_LIMIT_REQUESTS
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        client_id = self._client_id(request)
        window_id = int(time.time() // window)
        retry_after = self._retry_after(window)

        try:
            allowed, remaining = await self._check_redis(client_id, window_id, limit, window)
        except Exception:
            allowed, remaining = self._check_memory(client_id, window_id, limit)

        if not allowed:
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
        return response

    async def _check_redis(self, client_id: str, window_id: int, limit: int, window: int) -> tuple[bool, int]:
        key = f"{settings.RATE_LIMIT_REDIS_PREFIX}:{client_id}:{window_id}"
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window + 1)
        return count <= limit, limit - count

    def _check_memory(self, client_id: str, window_id: int, limit: int) -> tuple[bool, int]:
        key = f"{client_id}:{window_id}"
        current_window, count = self._memory_counts[key]
        if current_window != window_id:
            current_window, count = window_id, 0
        count += 1
        self._memory_counts[key] = (current_window, count)
        return count <= limit, limit - count

    def _client_id(self, request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _retry_after(self, window: int) -> int:
        return max(1, window - int(time.time() % window))
