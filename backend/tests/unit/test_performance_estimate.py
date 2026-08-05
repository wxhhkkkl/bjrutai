"""Unit tests for admin performance estimate helper (008, US1, SC-002)."""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.distributor import Distributor, OrgRole
from src.models.performance_rule import PerformanceRule, RuleStatus, RuleType
from src.schemas.organization import OrgCreate
from src.services import commission_service, organization_service
from tests.conftest import seed_user


async def _seed_org(db: AsyncSession) -> int:
    return (await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))).id


async def _seed_distributor(db: AsyncSession, org_id: int) -> int:
    user_id = await seed_user(db, openid="openid_e", user_type="distributor", name="推广员A")
    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole.MEMBER)
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return d.id


async def _seed_customer(db: AsyncSession, distributor_id: int) -> int:
    c = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000", phone_masked="138****8000",
        id_card_encrypted="x", id_card_masked="y", binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


async def _seed_bill(db: AsyncSession, customer_id: int, paid_cent: int, txn_id: str) -> None:
    b = Bill(
        customer_id=customer_id, transaction_id=txn_id, transaction_time=datetime(2026, 7, 15),
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent, transaction_status=TransactionStatus.PAID,
    )
    db.add(b)
    await db.flush()


async def _seed_rule(db: AsyncSession, org_id: int, tiers: list, version: int = 1) -> None:
    db.add(PerformanceRule(org_id=org_id, rule_type=RuleType.INTRA_ORG, tiers=tiers, status=RuleStatus.ACTIVE, version=version))
    await db.flush()


@pytest.mark.asyncio
async def test_estimate_matches_current_rule_tiers(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 800000, "txn_1")
    tiers = [{"minCent": 0, "maxCent": 1000000, "ratio": 0.05}, {"minCent": 1000000, "maxCent": None, "ratio": 0.08}]
    await _seed_rule(db_session, org_id, tiers, version=2)

    est = await commission_service.estimate_distributor(db_session, dist, "2026-07")
    assert est is not None
    assert est["baseCent"] == 800000
    assert est["ratio"] == 0.05
    assert est["commissionCent"] == 40000

    # Crossing into the next tier
    await _seed_bill(db_session, cid, 300000, "txn_2")
    est2 = await commission_service.estimate_distributor(db_session, dist, "2026-07")
    assert est2["baseCent"] == 1100000
    assert est2["ratio"] == 0.08
    assert est2["commissionCent"] == 88000


@pytest.mark.asyncio
async def test_estimate_none_when_no_rule(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 500000, "txn_1")

    est = await commission_service.estimate_distributor(db_session, dist, "2026-07")
    assert est is None  # unconfigured org -> no commission estimate
