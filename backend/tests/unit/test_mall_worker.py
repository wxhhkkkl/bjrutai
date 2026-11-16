"""Worker commits its lease before invoking a handler in another transaction."""

import pytest

from src.models.mall_operations import MallJob
from src.services.mall_job_service import enqueue_mall_job
from tests.conftest import TestAsyncSession


@pytest.mark.asyncio
async def test_worker_commits_lease_before_handler_and_finishes(db_session):
    from src.tasks.mall_tasks import run_mall_worker_once

    job = await enqueue_mall_job(
        db_session,
        kind="probe",
        entity_type="test",
        entity_id=1,
        entity_version=2,
        dedupe_key="worker-probe",
    )
    await db_session.commit()
    calls = []

    async def handler(item):
        async with TestAsyncSession() as reader:
            persisted = await reader.get(MallJob, item.job_id)
            assert persisted.status == "running"
            assert persisted.lease_owner == item.lease_owner
        calls.append(item.entity_version)

    assert await run_mall_worker_once(TestAsyncSession, handlers={"probe": handler}, enabled=True)
    async with TestAsyncSession() as reader:
        assert (await reader.get(MallJob, job.id)).status == "done"
    assert calls == [2]


@pytest.mark.asyncio
async def test_worker_disabled_unknown_kind_and_handler_failure(db_session):
    from src.tasks.mall_tasks import run_mall_worker_once

    job = await enqueue_mall_job(
        db_session,
        kind="probe",
        entity_type="test",
        entity_id=1,
        entity_version=2,
        dedupe_key="worker-failure",
    )
    await db_session.commit()

    async def handler(_item):
        raise RuntimeError("private credentials must never enter job errors")

    assert not await run_mall_worker_once(TestAsyncSession, handlers={"probe": handler})
    assert not await run_mall_worker_once(TestAsyncSession, handlers={}, enabled=True)
    assert await run_mall_worker_once(TestAsyncSession, handlers={"probe": handler}, enabled=True)
    async with TestAsyncSession() as reader:
        result = await reader.get(MallJob, job.id)
        assert result.status == "retry"
        assert result.last_error_code == "handler_failed"
