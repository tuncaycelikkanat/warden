"""In-memory sliding window rate limiting middleware for WARDEN API."""

import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter tracking request timestamps per client key."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_key: str) -> tuple[bool, int]:
        """Checks if client is within rate limits.

        Returns:
            (allowed: bool, retry_after: int)
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old timestamps
        timestamps = [ts for ts in self._history[client_key] if ts > window_start]
        self._history[client_key] = timestamps

        if len(timestamps) >= self.max_requests:
            oldest = timestamps[0]
            retry_after = max(1, int(oldest + self.window_seconds - now))
            return False, retry_after

        self._history[client_key].append(now)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware enforcing sliding-window rate limits per client IP."""

    EXEMPT_PREFIXES = (
        "/api/v1/health",
        "/dashboard",
        "/docs",
        "/openapi.json",
        "/redoc",
    )

    def __init__(
        self,
        app: Any = None,
        max_requests: int = 120,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.limiter = SlidingWindowRateLimiter(max_requests=max_requests, window_seconds=window_seconds)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Bypass rate limits for health check, docs, and static dashboard assets
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = self.limiter.is_allowed(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Please retry after {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
