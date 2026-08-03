"""Health check endpoint (T188).

GET /health – DB connectivity check (SELECT 1), Rutai API status (HEAD request), memory usage.
"""

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from ...core.config import get_settings
from ...core.database import async_session

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> dict:
    """Comprehensive health check: DB, external API, and memory."""
    db_status = "error"
    db_message = ""
    db_latency_ms = 0

    # DB connectivity check
    try:
        start = __import__("time").monotonic()
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        db_latency_ms = int((__import__("time").monotonic() - start) * 1000)
        db_status = "ok"
        db_message = "connected"
    except Exception as exc:
        db_status = "error"
        db_message = str(exc)[:200]
        logger.error("Health check DB error: %s", exc)

    # Rutai API status (HEAD request). Skip the live connectivity probe when
    # the external 互联网医院 API is mocked for dev/acceptance.
    rutai_status = "ok"
    rutai_message = "mocked" if settings.rutai_mock else ""
    if not settings.rutai_mock:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(
                    settings.rutai_api_base_url,
                    headers={
                        "Authorization": f"Bearer {settings.rutai_api_key}",
                    },
                )
                if resp.status_code < 500:
                    rutai_status = "ok"
                    rutai_message = f"HTTP {resp.status_code}"
                else:
                    rutai_status = "degraded"
                    rutai_message = f"HTTP {resp.status_code}"
        except Exception as exc:
            rutai_status = "error"
            rutai_message = str(exc)[:200]
            logger.error("Health check Rutai API error: %s", exc)

    # Memory usage (cross-platform)
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        memory_mb = round(usage.ru_maxrss / 1024, 1)
    except Exception:
        memory_mb = 0
    memory_pct = 0

    overall = "ok" if db_status == "ok" else "degraded"

    return {
        "code": 0,
        "message": "success",
        "data": {
            "status": overall,
            "service": "bjrutai-api",
            "version": "1.0.0",
            "checks": {
                "database": {
                    "status": db_status,
                    "message": db_message,
                    "latencyMs": db_latency_ms,
                },
                "rutaiApi": {
                    "status": rutai_status,
                    "message": rutai_message,
                },
                "memory": {
                    "rssMb": memory_mb,
                    "percent": memory_pct,
                },
            },
        },
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
