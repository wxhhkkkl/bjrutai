"""Two independent InnoDB workers exercise durable command/queue behavior."""

import asyncio
from datetime import timedelta

from sqlalchemy import select

from src.api.mall_deps import MallActor
from src.models.mall_base import utc_now
from src.models.mall_operations import MallCommand, MallJob
from src.models.performance_evidence import PerformancePeriodVersion
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.services.mall_command_service import reserve_mall_command
from src.services.mall_job_service import claim_next_mall_job, enqueue_mall_job, finish_mall_job
from src.services.performance_period_service import bump_unfrozen_periods
from src.services.settlement_service import review_settlement


async def test_two_innodb_writers_lock_periods_in_sorted_order(mall_mysql_sessions):
    periods = ["2099-10", "2099-11"]
    async with mall_mysql_sessions() as setup:
        for period in periods:
            version = await setup.get(PerformancePeriodVersion, period)
            if version is None:
                setup.add(PerformancePeriodVersion(period=period, revision=0, status="open"))
            else:
                version.revision = 0
                version.status = "open"
        await setup.commit()

    async def bump(requested_periods):
        async with mall_mysql_sessions() as session:
            changed = await bump_unfrozen_periods(session, requested_periods)
            await session.commit()
            return changed

    changed = await asyncio.wait_for(
        asyncio.gather(bump(periods), bump(list(reversed(periods)))), timeout=10
    )
    assert changed == [set(periods), set(periods)]

    async with mall_mysql_sessions() as check:
        revisions = {
            row.period: row.revision
            for row in (
                await check.execute(
                    select(PerformancePeriodVersion).where(
                        PerformancePeriodVersion.period.in_(periods)
                    )
                )
            ).scalars()
        }
    assert revisions == {period: 2 for period in periods}


async def test_review_freeze_serializes_before_later_innodb_input_change(mall_mysql_sessions):
    period = "2099-12"
    async with mall_mysql_sessions() as setup:
        setup.add(PerformancePeriodVersion(period=period, revision=0, status="open"))
        settlement = PerformanceSettlement(period=period, status=SettlementStatus.PENDING)
        setup.add(settlement)
        await setup.flush()
        settlement_id = settlement.id
        await setup.commit()

    writer_started = asyncio.Event()

    async def write_input():
        async with mall_mysql_sessions() as writer:
            writer_started.set()
            changed = await bump_unfrozen_periods(writer, [period])
            await writer.commit()
            return changed

    pending_writer = None
    try:
        async with mall_mysql_sessions() as reviewer:
            await review_settlement(reviewer, period, operator_id=1)
            pending_writer = asyncio.create_task(write_input())
            await asyncio.wait_for(writer_started.wait(), timeout=5)
            done, _ = await asyncio.wait({pending_writer}, timeout=0.1)
            assert not done
            await reviewer.commit()
            assert await asyncio.wait_for(pending_writer, timeout=5) == set()
    finally:
        if pending_writer and not pending_writer.done():
            await asyncio.wait_for(pending_writer, timeout=5)

    async with mall_mysql_sessions() as check:
        version = await check.get(PerformancePeriodVersion, period)
        settlement = await check.get(PerformanceSettlement, settlement_id)
        assert version.status == "frozen" and version.revision == 0
        assert settlement.status == SettlementStatus.REVIEWED


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
