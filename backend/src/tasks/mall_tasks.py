"""Bounded mall dispatch; no external handlers are registered at import time."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from ..services.mall_job_service import claim_next_mall_job, fail_mall_job, finish_mall_job


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
MALL_HANDLERS: dict[str, Callable[[MallWorkItem], Awaitable[None]]] = {}


async def run_mall_worker_once(
    session_factory,
    *,
    handlers: Mapping[str, Callable[[MallWorkItem], Awaitable[None]]],
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
    error = None
    try:
        await asyncio.wait_for(handlers[item.kind](item), timeout=timeout_seconds)
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
        else:
            await finish_mall_job(
                db, job_id=item.job_id, worker_id=owner, entity_version=item.entity_version
            )
        await db.commit()
    return True


async def mall_worker_job():
    from ..core.config import get_settings
    from ..core.database import async_session

    settings = get_settings()
    await run_mall_worker_once(
        async_session, handlers=MALL_HANDLERS, enabled=settings.mall_worker_enabled
    )
