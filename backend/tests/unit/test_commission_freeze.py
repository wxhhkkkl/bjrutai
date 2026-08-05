"""Unit tests for commission freeze + rule snapshot (008, FR-006/FR-007)."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.commission_result import CommissionResult
from src.models.distributor import Distributor, OrgRole
from src.models.performance_rule import PerformanceRule, RuleStatus, RuleType
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.schemas.organization import OrgCreate
from src.services import commission_service, organization_service
from tests.conftest import seed_user


async def _seed_org(db: AsyncSession) -> int:
    return (await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))).id


async def _seed_distributor(db: AsyncSession, org_id: int) -> int:
    user_id = await seed_user(db, openid="openid_x", user_type="distributor", name="推广员A")
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


async def _seed_rule(db: AsyncSession, org_id: int, tiers: list, version: int = 1) -> PerformanceRule:
    r = PerformanceRule(org_id=org_id, rule_type=RuleType.INTRA_ORG, tiers=tiers, status=RuleStatus.ACTIVE, version=version)
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return r


@pytest.mark.asyncio
async def test_compute_commission_skips_reviewed_period(db_session: AsyncSession):
    """FR-006: a reviewed (frozen) period must not be recomputed."""
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 800000, "txn_1")
    await _seed_rule(db_session, org_id, [{"minCent": 0, "maxCent": None, "ratio": 0.05}])

    db_session.add(CommissionResult(
        period="2026-07", distributor_id=dist, org_id=org_id, rule_type=RuleType.INTRA_ORG,
        base_cent=1, ratio="0.010000", commission_cent=1, rule_snapshot={"old": True},
    ))
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.REVIEWED))
    await db_session.flush()

    result = await commission_service.compute_commission(db_session, "2026-07")
    assert result.get("frozen") is True

    rows = (await db_session.execute(select(CommissionResult))).scalars().all()
    assert len(rows) == 1
    assert rows[0].base_cent == 1  # unchanged


@pytest.mark.asyncio
async def test_compute_commission_writes_rule_snapshot(db_session: AsyncSession):
    """FR-007: result rows carry the rule tiers/version used at computation."""
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 800000, "txn_1")
    tiers = [{"minCent": 0, "maxCent": 1000000, "ratio": 0.05}, {"minCent": 1000000, "maxCent": None, "ratio": 0.08}]
    await _seed_rule(db_session, org_id, tiers, version=3)

    await commission_service.compute_commission(db_session, "2026-07")

    rows = (await db_session.execute(select(CommissionResult))).scalars().all()
    assert len(rows) == 1
    assert rows[0].base_cent == 800000
    assert rows[0].commission_cent == 40000
    snap = rows[0].rule_snapshot
    assert snap["ruleType"] == "intra_org"
    assert snap["version"] == 3
    assert snap["tiers"] == tiers

    # Pending settlement batch created for the period
    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.period == "2026-07"
    assert s.status == SettlementStatus.PENDING


@pytest.mark.asyncio
async def test_recompute_rejected_returns_to_pending(db_session: AsyncSession):
    """FR-008: recomputing a rejected period clears the reject and goes back to pending."""
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 500000, "txn_1")
    await _seed_rule(db_session, org_id, [{"minCent": 0, "maxCent": None, "ratio": 0.05}])

    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.REJECTED, reject_reason="有误"))
    await db_session.flush()

    await commission_service.compute_commission(db_session, "2026-07")
    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.status == SettlementStatus.PENDING
    assert s.reject_reason is None
