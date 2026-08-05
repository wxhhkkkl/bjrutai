"""Unit tests for mini-program performance view service (008, US3, FR-004/FR-009)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commission_result import CommissionResult
from src.models.performance_rule import RuleType
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.models.distributor import Distributor, OrgRole
from src.schemas.organization import OrgCreate
from src.services import organization_service, performance_view_service
from tests.conftest import seed_user


async def _seed_org(db: AsyncSession) -> int:
    return (await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))).id


async def _seed_distributor(db: AsyncSession, org_id: int, user_id: int) -> int:
    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole.MEMBER)
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return d.id


@pytest.mark.asyncio
async def test_confirmed_months_only_reviewed(db_session: AsyncSession):
    """FR-004: confirmed list must contain only periods whose settlement is reviewed."""
    org_id = await _seed_org(db_session)
    user_id = await seed_user(db_session, openid="openid_u", user_type="distributor", name="推广员A")
    dist = await _seed_distributor(db_session, org_id, user_id)

    # reviewed month
    db_session.add(CommissionResult(period="2026-06", distributor_id=dist, org_id=org_id, rule_type=RuleType.INTRA_ORG, base_cent=600000, ratio="0.050000", commission_cent=30000))
    db_session.add(PerformanceSettlement(period="2026-06", status=SettlementStatus.REVIEWED))
    # rejected month
    db_session.add(CommissionResult(period="2026-05", distributor_id=dist, org_id=org_id, rule_type=RuleType.INTRA_ORG, base_cent=500000, ratio="0.050000", commission_cent=25000))
    db_session.add(PerformanceSettlement(period="2026-05", status=SettlementStatus.REJECTED, reject_reason="有误"))
    # pending month
    db_session.add(PerformanceSettlement(period="2026-04", status=SettlementStatus.PENDING))
    await db_session.flush()

    months = await performance_view_service._confirmed_month_items(db_session, distributor_id=dist)
    assert [m["month"] for m in months] == ["2026-06"]
    assert months[0]["intraOrg"]["commissionCent"] == 30000
