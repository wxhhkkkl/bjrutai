"""The approved performance snapshot must reject stale source input."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException
from src.models.mall_consumption import MallConsumption
from src.models.performance_evidence import PerformancePeriodVersion
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.services import settlement_service
from tests.mall_consumption_fixtures import (
    add_mall_source,
    add_performance_rule,
    performance_context,
)


@pytest.mark.asyncio
async def test_source_change_between_capture_and_review_cannot_freeze_stale_input(
    db_session: AsyncSession,
):
    from src.services.performance_evidence_service import capture_period_evidence

    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15)
    )
    await add_performance_rule(db_session, context)
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING))
    await db_session.flush()
    from src.services.commission_service import compute_commission

    await compute_commission(db_session, "2026-07")

    await capture_period_evidence(db_session, "2026-07")
    source.performance_base_cent = 250000
    source.source_version += 1
    await db_session.flush()

    with pytest.raises(ConflictException) as error:
        await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)

    assert error.value.status_code == 409
    settlement = await db_session.scalar(
        select(PerformanceSettlement).where(PerformanceSettlement.period == "2026-07")
    )
    assert settlement.status == SettlementStatus.PENDING
    period_version = await db_session.get(PerformancePeriodVersion, "2026-07")
    assert period_version is None or period_version.status != "frozen"
    stored_source = await db_session.get(MallConsumption, source.id)
    assert stored_source.performance_base_cent == 250000

