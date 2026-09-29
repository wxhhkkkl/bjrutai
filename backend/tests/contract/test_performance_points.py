"""Contract tests for commission-derived point balances and redemption."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commission_result import CommissionResult
from src.models.distributor import Distributor, OrgRole
from src.models.performance_rule import RuleType
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token, seed_user


def _headers(*perms: str) -> dict:
    token = make_access_token(user_id=1, user_type="admin", permissions=list(perms))
    return {"Authorization": f"Bearer {token}"}


def _data(response):
    body = response.json()
    assert body["code"] == 0
    return body["data"]


async def _seed_commission(
    db: AsyncSession,
    period: str = "2026-08",
    status: SettlementStatus = SettlementStatus.REVIEWED,
) -> CommissionResult:
    org = await organization_service.create_org(
        db, OrgCreate(name="积分测试组织", orgType="headquarters")
    )
    user_id = await seed_user(
        db, openid=f"points_{period}_{status.value}", user_type="distributor", name="测试员工"
    )
    distributor = Distributor(user_id=user_id, org_id=org.id, org_role=OrgRole.MEMBER)
    db.add(distributor)
    await db.flush()
    db.add(PerformanceSettlement(period=period, status=status))
    commission = CommissionResult(
        period=period,
        distributor_id=distributor.id,
        org_id=org.id,
        rule_type=RuleType.INTRA_ORG,
        base_cent=123456,
        ratio="0.100000",
        commission_cent=12346,
        computed_at=datetime(2026, 8, 31),
    )
    db.add(commission)
    await db.flush()
    await db.refresh(commission)
    return commission


@pytest.mark.asyncio
async def test_frozen_estimate_shows_points_and_redeemed_balance(
    client: AsyncClient, db_session: AsyncSession
):
    commission = await _seed_commission(db_session)
    response = await client.get(
        "/api/v1/admin/performance/estimates",
        params={"period": commission.period, "orgId": commission.org_id},
        headers=_headers("sharing_rules.read"),
    )
    item = _data(response)["intraOrg"][0]
    assert item["commissionCent"] == 12346
    assert item["pointsBalance"] == 123.46
    assert item["pointsRedeemed"] is False


@pytest.mark.asyncio
async def test_redeem_points_zeros_balance_but_preserves_commission(
    client: AsyncClient, db_session: AsyncSession
):
    commission = await _seed_commission(db_session)
    url = (
        f"/api/v1/admin/performance/settlements/{commission.period}/points/"
        f"{commission.distributor_id}/intra_org/redeem"
    )

    response = await client.post(url, headers=_headers("performance.settle"))
    data = _data(response)
    assert data["redeemedPoints"] == 123.46
    assert data["pointsBalance"] == 0

    await db_session.refresh(commission)
    assert commission.commission_cent == 12346
    assert commission.redeemed_points_x100 == 12346
    assert commission.points_redeemed_by == 1
    assert commission.points_redeemed_at is not None

    refreshed = _data(await client.get(
        "/api/v1/admin/performance/estimates",
        params={"period": commission.period, "orgId": commission.org_id},
        headers=_headers("sharing_rules.read"),
    ))["intraOrg"][0]
    assert refreshed["commissionCent"] == 12346
    assert refreshed["pointsBalance"] == 0
    assert refreshed["pointsRedeemed"] is True

    duplicate = await client.post(url, headers=_headers("performance.settle"))
    assert duplicate.json()["code"] == 40000


@pytest.mark.asyncio
async def test_only_reviewed_settlements_can_redeem_points(
    client: AsyncClient, db_session: AsyncSession
):
    commission = await _seed_commission(
        db_session, period="2026-07", status=SettlementStatus.PENDING
    )
    response = await client.post(
        f"/api/v1/admin/performance/settlements/{commission.period}/points/"
        f"{commission.distributor_id}/intra_org/redeem",
        headers=_headers("performance.settle"),
    )
    assert response.json()["code"] == 40000
    await db_session.refresh(commission)
    assert commission.points_redeemed_at is None
    assert commission.commission_cent == 12346


@pytest.mark.asyncio
async def test_redeem_points_requires_settlement_permission(
    client: AsyncClient, db_session: AsyncSession
):
    commission = await _seed_commission(db_session)
    response = await client.post(
        f"/api/v1/admin/performance/settlements/{commission.period}/points/"
        f"{commission.distributor_id}/intra_org/redeem",
        headers=_headers("sharing_rules.read"),
    )
    assert response.json()["code"] == 40300
