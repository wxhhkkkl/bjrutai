"""Rate limiter (T186).

In-memory rate limiter: configurable requests/min per IP on auth endpoints.
Returns 429 with Retry-After header when exceeded.

Controlled by settings:
  - RATE_LIMIT_ENABLED (default True)
  - RATE_LIMIT_REQUESTS_PER_MINUTE (default 10)

Production note: Replace with Redis-based limiter for multi-process deployments.
"""

import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import get_settings

# Endpoints subject to rate limiting (prefix-based)
RATE_LIMITED_PREFIXES = (
    "/api/v1/auth/",
)

# In-memory store: {ip: [(timestamp,), ...]}
_rate_store: dict[str, list[float]] = defaultdict(list)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit requests on auth endpoints.

    Non-auth endpoints pass through without checks.
    When exceeded, returns 429 with Retry-After header.
    """

    def __init__(self, app):
        super().__init__(app)
        settings = get_settings()
        self._enabled = settings.rate_limit_enabled
        self._max_requests = settings.rate_limit_requests_per_minute
        self._window_seconds = 60

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting when disabled
        if not self._enabled:
            return await call_next(request)

        # Only rate-limit specific prefixes
        path = request.url.path
        if not any(path.startswith(prefix) for prefix in RATE_LIMITED_PREFIXES):
            return await call_next(request)

        # Extract client IP
        client_ip = request.client.host if request.client else "unknown"

        # Clean up old entries for this IP
        now = time.monotonic()
        cutoff = now - self._window_seconds
        _rate_store[client_ip] = [ts for ts in _rate_store[client_ip] if ts > cutoff]

        if len(_rate_store[client_ip]) >= self._max_requests:
            retry_after = self._window_seconds
            return JSONResponse(
                status_code=429,
                content={
                    "code": 42900,
                    "message": "Too many requests. Please retry later.",
                    "data": None,
                    "requestId": "",
                    "serverTime": "",
                },
                headers={"Retry-After": str(retry_after)},
            )

        # Record this request
        _rate_store[client_ip].append(now)

        return await call_next(request)
