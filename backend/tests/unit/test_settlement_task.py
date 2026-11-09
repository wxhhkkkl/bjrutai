"""Monthly settlement jobs capture evidence while holding the period lock."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.models.performance_evidence import PerformanceEvidence, PerformancePeriodVersion
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.tasks import settlement_task
from tests.mall_consumption_fixtures import add_bill, add_performance_rule, performance_context


@pytest.mark.asyncio
async def test_monthly_job_records_results_and_evidence_under_period_revision(
    db_session, monkeypatch
):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    await add_performance_rule(db_session, context)

    class FrozenDateTime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 8, 1, tzinfo=timezone.utc)

    class SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(settlement_task, "datetime", FrozenDateTime)
    monkeypatch.setattr(settlement_task, "async_session", SessionContext)
    await settlement_task.monthly_settlement_job()

    settlement = await db_session.scalar(
        select(PerformanceSettlement).where(PerformanceSettlement.period == "2026-07")
    )
    version = await db_session.get(PerformancePeriodVersion, "2026-07")
    evidence = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == "2026-07",
            PerformanceEvidence.distributor_id == context["distributorId"],
        )
    )
    assert settlement.status == SettlementStatus.PENDING
    assert version.recomputed_revision == version.revision == 0
    assert evidence is not None and evidence.original_commission_cent == 64000


@pytest.mark.asyncio
async def test_monthly_job_does_not_recompute_reviewed_period(db_session, monkeypatch):
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.REVIEWED))
    await db_session.flush()

    class FrozenDateTime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 8, 1, tzinfo=timezone.utc)

    class SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(settlement_task, "datetime", FrozenDateTime)
    monkeypatch.setattr(settlement_task, "async_session", SessionContext)
    await settlement_task.monthly_settlement_job()

    version = await db_session.get(PerformancePeriodVersion, "2026-07")
    assert version.status == "frozen"
    assert version.revision == 0
    assert (
        await db_session.scalar(
            select(PerformanceEvidence.id).where(PerformanceEvidence.period == "2026-07")
        )
        is None
    )
