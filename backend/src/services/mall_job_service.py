"""Database-backed work leases for recoverable mall background work."""

import re
from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mall_base import utc_now
from ..models.mall_operations import MallJob


async def locked_mall_lease(db, item):
    """Domain handlers lock their parent entity first, then fence their job lease."""
    job = await db.scalar(
        select(MallJob)
        .where(MallJob.id == item.job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        job is None
        or job.status != "running"
        or job.lease_owner != item.lease_owner
        or job.entity_version != item.entity_version
        or job.entity_id != item.entity_id
        or job.entity_type != item.entity_type
        or job.kind != item.kind
        or job.lease_until is None
        or job.lease_until <= utc_now()
    ):
        return None
    return job


async def defer_mall_job(db, *, job_id, worker_id, entity_version, next_run_at):
    """A successful nonterminal poll waits without consuming the failure budget."""
    if next_run_at <= utc_now():
        raise ValueError("continuation must be in the future")
    job = await db.scalar(
        select(MallJob)
        .where(MallJob.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        job is None
        or job.status != "running"
        or job.lease_owner != worker_id
        or job.entity_version != entity_version
        or job.lease_until is None
        or job.lease_until <= utc_now()
    ):
        return False
    job.status, job.next_run_at, job.attempts = "retry", next_run_at, 0
    job.lease_owner = job.lease_until = job.last_error_code = None
    await db.flush()
    return True


async def fail_mall_job(
    db: AsyncSession,
    *,
    job_id: int,
    worker_id: str,
    entity_version: int,
    error_code: str,
    max_attempts: int = 5,
) -> bool:
    """Release a valid lease into bounded backoff or an explicit manual queue."""
    if max_attempts < 1 or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", error_code):
        raise ValueError("a safe error code and positive attempt limit are required")
    job = (
        await db.execute(
            select(MallJob)
            .where(MallJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    now = utc_now()
    if (
        job is None
        or job.status != "running"
        or job.lease_owner != worker_id
        or job.entity_version != entity_version
        or job.lease_until is None
        or job.lease_until <= now
    ):
        return False
    job.status = "manual" if job.attempts >= max_attempts else "retry"
    job.next_run_at = now + timedelta(seconds=min(30 * 2 ** min(job.attempts - 1, 7), 3600))
    job.last_error_code = error_code
    job.lease_owner = None
    job.lease_until = None
    await db.flush()
    return True


async def enqueue_mall_job(
    db: AsyncSession,
    *,
    kind: str,
    entity_type: str,
    entity_id: int,
    entity_version: int,
    dedupe_key: str,
    next_run_at=None,
) -> MallJob:
    """Enqueue once per deterministic dedupe key without a process-local cache."""
    existing = (
        await db.execute(select(MallJob).where(MallJob.dedupe_key == dedupe_key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    job = MallJob(
        kind=kind,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_version=entity_version,
        dedupe_key=dedupe_key,
        status="ready",
        attempts=0,
        next_run_at=next_run_at or utc_now(),
    )
    try:
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except IntegrityError:
        return (
            await db.execute(
                select(MallJob)
                .where(MallJob.dedupe_key == dedupe_key)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
    return job


async def claim_next_mall_job(
    db: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int,
    kinds: tuple[str, ...] | None = None,
) -> MallJob | None:
    """Lease one due job; MySQL applies SKIP LOCKED only to this queue claim."""
    now = utc_now()
    eligible = or_(
        and_(MallJob.status.in_(("ready", "retry")), MallJob.next_run_at <= now),
        and_(MallJob.status == "running", MallJob.lease_until < now),
    )
    if kinds is not None:
        eligible = and_(eligible, MallJob.kind.in_(kinds))
    # An OR + filesort locking scan can lock more rows than LIMIT on InnoDB.
    # Read candidate IDs first, then acquire exact PK locks and recheck eligibility.
    candidates = (
        (
            await db.execute(
                select(MallJob.id)
                .where(eligible)
                .order_by(MallJob.next_run_at, MallJob.id)
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    job = None
    for candidate in candidates:
        job = (
            await db.execute(
                select(MallJob)
                .where(MallJob.id == candidate, eligible)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if job is not None:
            break
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    job.lease_owner = worker_id
    job.lease_until = now + timedelta(seconds=lease_seconds)
    job.started_at = now
    db.add(job)
    await db.flush()
    return job


async def finish_mall_job(
    db: AsyncSession,
    *,
    job_id: int,
    worker_id: str,
    entity_version: int,
) -> bool:
    """Finish only the current worker lease and current entity version."""
    job = (
        await db.execute(
            select(MallJob)
            .where(MallJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if (
        job is None
        or job.status != "running"
        or job.lease_owner != worker_id
        or job.entity_version != entity_version
        or job.lease_until is None
        or job.lease_until <= utc_now()
    ):
        return False
    job.status = "done"
    job.lease_owner = None
    job.lease_until = None
    job.finished_at = utc_now()
    db.add(job)
    await db.flush()
    return True
