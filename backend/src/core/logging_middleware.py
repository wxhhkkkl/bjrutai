"""Logging middleware (T185).

Logs request_id, method, path, user_id (extracted from JWT), status_code, duration_ms.
Uses standard logging with a consistent format. Suitable for production.
"""

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("bjrutai.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with structured metadata.

    Log format:
        requestId=xxx method=GET path=/api/v1/... user_id=123 status=200 duration=15ms
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()

        # Extract user_id from JWT if present
        user_id = "-"
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header[len("Bearer "):]
                from jose import jwt as jose_jwt

                # Decode without verification to extract sub (user_id)
                claims = jose_jwt.get_unverified_claims(token)
                sub = claims.get("sub")
                if sub:
                    user_id = str(sub)
            except Exception:
                pass

        response = await call_next(request)

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "requestId=%s method=%s path=%s user_id=%s status=%s duration=%dms",
            request_id,
            request.method,
            request.url.path,
            user_id,
            response.status_code,
            duration_ms,
        )

        # Add request_id to response headers for traceability
        response.headers["X-Request-Id"] = request_id

        return response
