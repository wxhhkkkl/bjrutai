"""Real InnoDB race between changing a performance source and freezing its month."""

import asyncio
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.exceptions import ConflictException
from src.models.mall_consumption import MallConsumption
from src.models.performance_evidence import PerformancePeriodVersion
from src.models.performance_rule import PerformanceRule, RuleStatus
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.services.performance_period_service import bump_period
from src.services.settlement_service import review_settlement, settle
from tests.mall_consumption_fixtures import (
    add_mall_source,
    add_performance_rule,
    performance_context,
)


@pytest.mark.asyncio
async def test_source_write_wins_lock_race_and_review_refuses_stale_snapshot(mall_mysql_sessions):
    period = "2026-06"
    async with mall_mysql_sessions() as setup:
        context = await performance_context(setup)
        _, source = await add_mall_source(
            setup, context, 300000, datetime(2026, 6, 15)
        )
        rule = await add_performance_rule(setup, context)
        rule_id = rule.id
        await settle(setup, period, operator_id=1)
        source_id = source.id
        await setup.commit()

    source_locked = asyncio.Event()
    review_started = asyncio.Event()

    async def change_source():
        async with mall_mysql_sessions() as writer:
            await bump_period(writer, period)
            source = await writer.get(MallConsumption, source_id)
            source.performance_base_cent = 250000
            source.source_version += 1
            source.version += 1
            await writer.flush()
            source_locked.set()
            await asyncio.sleep(0.2)
            await writer.commit()

    async def review():
        async with mall_mysql_sessions() as reviewer:
            review_started.set()
            try:
                await review_settlement(reviewer, period, operator_id=2)
                await reviewer.commit()
                return "frozen"
            except ConflictException:
                await reviewer.rollback()
                return "stale"

    writer_task = asyncio.create_task(change_source())
    reviewer_task = None
    try:
        await asyncio.wait_for(source_locked.wait(), timeout=5)
        reviewer_task = asyncio.create_task(review())
        await asyncio.wait_for(review_started.wait(), timeout=5)
        # The reviewer has started while the writer owns the month lock. It
        # must wait for the source update to commit before checking evidence.
        done, _ = await asyncio.wait({reviewer_task}, timeout=0.05)
        assert not done
        await asyncio.wait_for(writer_task, timeout=10)
        assert await asyncio.wait_for(reviewer_task, timeout=10) == "stale"
    finally:
        for task in (writer_task, reviewer_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (writer_task, reviewer_task) if task),
            return_exceptions=True,
        )
        # MySQL test modules share the runner-owned schema. Leaving this active
        # test rule behind would create evidence obligations in unrelated months.
        async with mall_mysql_sessions() as cleanup:
            rule = await cleanup.get(PerformanceRule, rule_id)
            if rule is not None:
                rule.status = RuleStatus.INACTIVE
                await cleanup.commit()

    async with mall_mysql_sessions() as check:
        version = await check.get(PerformancePeriodVersion, period)
        settlement = await check.scalar(
            select(PerformanceSettlement).where(PerformanceSettlement.period == period)
        )
        source = await check.get(MallConsumption, source_id)
        assert version.status == "open"
        assert version.revision == 1
        assert settlement.status == SettlementStatus.PENDING
        assert source.performance_base_cent == 250000
        assert source.source_version == 2
