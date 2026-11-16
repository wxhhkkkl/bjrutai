"""A durable mall job can be reclaimed only after its lease expires."""

from datetime import timedelta

import pytest

from src.models.mall_base import utc_now


@pytest.mark.asyncio
async def test_failed_job_backs_off_then_requires_manual_review(db_session):
    from src.services.mall_job_service import claim_next_mall_job, enqueue_mall_job, fail_mall_job

    job = await enqueue_mall_job(
        db_session,
        kind="test",
        entity_type="test",
        entity_id=1,
        entity_version=1,
        dedupe_key="retry-test",
    )
    await claim_next_mall_job(db_session, worker_id="a", lease_seconds=30)
    assert not await fail_mall_job(
        db_session, job_id=job.id, worker_id="wrong", entity_version=1, error_code="timeout"
    )
    assert await fail_mall_job(
        db_session,
        job_id=job.id,
        worker_id="a",
        entity_version=1,
        error_code="timeout",
        max_attempts=2,
    )
    assert job.status == "retry" and job.next_run_at > utc_now()
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.flush()
    await claim_next_mall_job(db_session, worker_id="b", lease_seconds=30)
    assert await fail_mall_job(
        db_session,
        job_id=job.id,
        worker_id="b",
        entity_version=1,
        error_code="timeout",
        max_attempts=2,
    )
    assert job.status == "manual" and job.lease_owner is None


@pytest.mark.asyncio
async def test_job_dedupe_lease_recovery_and_old_version_finish_are_safe(db_session):
    from src.services.mall_job_service import claim_next_mall_job, enqueue_mall_job, finish_mall_job

    first = await enqueue_mall_job(
        db_session,
        kind="payment_query",
        entity_type="mall_payment",
        entity_id=18,
        entity_version=4,
        dedupe_key="payment:18:v4:query",
    )
    duplicate = await enqueue_mall_job(
        db_session,
        kind="payment_query",
        entity_type="mall_payment",
        entity_id=18,
        entity_version=4,
        dedupe_key="payment:18:v4:query",
    )
    assert first.id == duplicate.id

    claimed = await claim_next_mall_job(db_session, worker_id="worker-a", lease_seconds=30)
    assert claimed is not None and claimed.lease_owner == "worker-a"
    claimed.lease_until = utc_now() - timedelta(seconds=1)
    await db_session.flush()

    reclaimed = await claim_next_mall_job(db_session, worker_id="worker-b", lease_seconds=30)
    assert reclaimed is not None and reclaimed.id == claimed.id
    assert reclaimed.lease_owner == "worker-b"
    reclaimed.lease_until = utc_now() - timedelta(seconds=1)
    await db_session.flush()
    assert not await finish_mall_job(
        db_session,
        job_id=reclaimed.id,
        worker_id="worker-b",
        entity_version=4,
    )
    reclaimed.lease_until = utc_now() + timedelta(seconds=30)
    await db_session.flush()
    assert not await finish_mall_job(
        db_session,
        job_id=reclaimed.id,
        worker_id="worker-b",
        entity_version=5,
    )
    assert await finish_mall_job(
        db_session,
        job_id=reclaimed.id,
        worker_id="worker-b",
        entity_version=4,
    )
