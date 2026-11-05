"""Two independent InnoDB workers exercise durable command/queue behavior."""

import asyncio
from datetime import timedelta

from sqlalchemy import select

from src.api.mall_deps import MallActor
from src.models.mall_base import utc_now
from src.models.mall_operations import MallCommand, MallJob
from src.services.mall_command_service import reserve_mall_command
from src.services.mall_job_service import claim_next_mall_job, enqueue_mall_job, finish_mall_job


async def test_two_workers_claim_distinct_jobs_and_expired_worker_cannot_finish(
    mall_mysql_sessions,
):
    async with mall_mysql_sessions() as setup:
        for number in (1, 2):
            await enqueue_mall_job(
                setup,
                kind="test_probe",
                entity_type="test",
                entity_id=number,
                entity_version=1,
                dedupe_key=f"reliability-probe-{number}",
            )
        await setup.commit()

    async with mall_mysql_sessions() as first, mall_mysql_sessions() as second:
        one = await claim_next_mall_job(first, worker_id="worker-a", lease_seconds=30)
        # Keep the first transaction locked while another worker claims.
        two = await asyncio.wait_for(
            claim_next_mall_job(second, worker_id="worker-b", lease_seconds=30),
            timeout=5,
        )
        assert one and two and one.id != two.id
        await first.commit()
        await second.commit()
        job_id = one.id

    async with mall_mysql_sessions() as setup:
        job = await setup.get(MallJob, job_id)
        job.lease_until = utc_now() - timedelta(seconds=1)
        await setup.commit()

    async with mall_mysql_sessions() as recovered:
        job = await claim_next_mall_job(recovered, worker_id="worker-c", lease_seconds=30)
        assert job and job.id == job_id
        await recovered.commit()

    async with mall_mysql_sessions() as stale:
        assert not await finish_mall_job(
            stale, job_id=job_id, worker_id="worker-a", entity_version=1
        )
        await stale.rollback()
    async with mall_mysql_sessions() as current:
        assert await finish_mall_job(current, job_id=job_id, worker_id="worker-c", entity_version=1)
        await current.commit()


async def test_two_workers_replay_one_durable_command(mall_mysql_sessions):
    async def reserve():
        async with mall_mysql_sessions() as session:
            result = await reserve_mall_command(
                session,
                actor=MallActor("user", 987, frozenset()),
                action="reliabilityProbe",
                key="mysql-command-probe",
                payload={"quantity": 1},
            )
            await session.commit()
            return result.command.id, result.created

    results = await asyncio.wait_for(asyncio.gather(reserve(), reserve()), timeout=10)
    assert results[0][0] == results[1][0]
    assert sum(created for _, created in results) == 1
    async with mall_mysql_sessions() as session:
        commands = (
            (
                await session.execute(
                    select(MallCommand).where(
                        MallCommand.action == "reliabilityProbe",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(commands) == 1
