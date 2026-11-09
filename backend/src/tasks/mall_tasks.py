"""Bounded mall dispatch; no external handlers are registered at import time."""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta

from ..services.mall_job_service import (
    claim_next_mall_job,
    defer_mall_job,
    fail_mall_job,
    finish_mall_job,
)


@dataclass(frozen=True)
class MallJobContinuation:
    delay_seconds: int = 30


@dataclass(frozen=True)
class MallWorkItem:
    job_id: int
    kind: str
    entity_type: str
    entity_id: int
    entity_version: int
    lease_owner: str


# Domain handlers are added by their owning stories.  Each must recheck the
# entity version and use stable external identities/idempotent business effects.
MALL_HANDLERS: dict[str, Callable[[MallWorkItem], Awaitable[None | MallJobContinuation]]] = {}
logger = logging.getLogger(__name__)


async def run_mall_worker_once(
    session_factory,
    *,
    handlers: Mapping[str, Callable[[MallWorkItem], Awaitable[None | MallJobContinuation]]],
    enabled: bool = False,
    timeout_seconds: float = 20,
) -> bool:
    if not enabled or not handlers:
        return False
    if not 0 < timeout_seconds <= 50:
        raise ValueError("handler timeout must be between 0 and 50 seconds")
    # Unique per attempt, so a late invocation can never finish a newer lease.
    owner = uuid.uuid4().hex
    async with session_factory() as db:
        job = await claim_next_mall_job(
            db, worker_id=owner, lease_seconds=60, kinds=tuple(handlers)
        )
        if job is None:
            return False
        item = MallWorkItem(
            job.id, job.kind, job.entity_type, job.entity_id, job.entity_version, owner
        )
        await db.commit()

    # No database transaction or row lock is held during a handler's I/O.
    error, result = None, None
    try:
        result = await asyncio.wait_for(handlers[item.kind](item), timeout=timeout_seconds)
    except TimeoutError:
        error = "handler_timeout"
    except Exception:
        error = "handler_failed"
    async with session_factory() as db:
        if error:
            await fail_mall_job(
                db,
                job_id=item.job_id,
                worker_id=owner,
                entity_version=item.entity_version,
                error_code=error,
            )
        elif isinstance(result, MallJobContinuation):
            from ..models.mall_base import utc_now

            await defer_mall_job(
                db,
                job_id=item.job_id,
                worker_id=owner,
                entity_version=item.entity_version,
                next_run_at=utc_now() + timedelta(seconds=result.delay_seconds),
            )
        else:
            await finish_mall_job(
                db, job_id=item.job_id, worker_id=owner, entity_version=item.entity_version
            )
        await db.commit()
    return True


async def mall_worker_job():
    from ..core.config import get_settings
    from ..core.database import async_session
    from ..services.mall_export_service import finance_export_handlers
    from ..services.mall_logistics_service import logistics_handlers
    from ..services.mall_notification_service import (
        mall_notification_handlers,
        schedule_overdue_funds_responsibilities,
    )
    from ..services.mall_order_expiry_service import order_handlers
    from ..services.mall_payment_runtime import payment_handlers
    from ..services.mall_receipt_service import fulfillment_handlers
    from ..services.mall_refund_runtime import refund_handlers

    settings = get_settings()
    if not settings.mall_worker_enabled:
        return
    # This scheduler has its own short transaction. An escalation/notice outage
    # cannot roll back a buyer transaction or block unrelated queue handlers.
    async with async_session() as db:
        try:
            await schedule_overdue_funds_responsibilities(db)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("mall_funds_responsibility_scan_failed")
    handlers = {
        **MALL_HANDLERS,
        **mall_notification_handlers(async_session),
        **finance_export_handlers(async_session),
        **order_handlers(async_session),
        **payment_handlers(async_session),
        **refund_handlers(async_session),
        **fulfillment_handlers(async_session),
        **logistics_handlers(async_session),
    }
    await run_mall_worker_once(async_session, handlers=handlers, enabled=True, timeout_seconds=40)
