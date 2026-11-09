"""Unit tests for settlement state machine (008, FR-003/FR-012/FR-013)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BadRequestException, NotFoundException
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.services import settlement_service


async def _seed(db: AsyncSession, period: str, status: SettlementStatus = SettlementStatus.PENDING) -> int:
    s = PerformanceSettlement(period=period, status=status)
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return s.id


@pytest.mark.asyncio
async def test_review_pending_marks_reviewed(db_session: AsyncSession):
    await _seed(db_session, "2026-07")
    data = await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)
    assert data["status"] == "reviewed"
    assert data["reviewedBy"] == 1
    assert data["reviewedAt"] is not None

    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.status == SettlementStatus.REVIEWED
    assert s.reviewed_by == 1


@pytest.mark.asyncio
async def test_review_reviewed_raises(db_session: AsyncSession):
    await _seed(db_session, "2026-07", SettlementStatus.REVIEWED)
    with pytest.raises(BadRequestException):
        await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)


@pytest.mark.asyncio
async def test_review_missing_settlement_raises(db_session: AsyncSession):
    with pytest.raises(NotFoundException):
        await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)


@pytest.mark.asyncio
async def test_reject_pending_records_reason(db_session: AsyncSession):
    await _seed(db_session, "2026-07")
    data = await settlement_service.reject_settlement(db_session, "2026-07", operator_id=1, reason="核对有误")
    assert data["status"] == "rejected"
    assert data["rejectReason"] == "核对有误"

    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.status == SettlementStatus.REJECTED
    assert s.reject_reason == "核对有误"


@pytest.mark.asyncio
async def test_reject_requires_reason(db_session: AsyncSession):
    await _seed(db_session, "2026-07")
    with pytest.raises(BadRequestException):
        await settlement_service.reject_settlement(db_session, "2026-07", operator_id=1, reason="  ")


@pytest.mark.asyncio
async def test_reject_reviewed_raises(db_session: AsyncSession):
    await _seed(db_session, "2026-07", SettlementStatus.REVIEWED)
    with pytest.raises(BadRequestException):
        await settlement_service.reject_settlement(db_session, "2026-07", operator_id=1, reason="x")


@pytest.mark.asyncio
async def test_recompute_rejected_returns_pending(db_session: AsyncSession):
    """recompute delegates to commission engine; rejected period goes back to pending."""
    await _seed(db_session, "2026-07", SettlementStatus.REJECTED)
    data = await settlement_service.recompute_settlement(db_session, "2026-07")
    assert data["status"] == "pending"

    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.status == SettlementStatus.PENDING
    assert s.reject_reason is None


@pytest.mark.asyncio
async def test_recompute_reviewed_raises(db_session: AsyncSession):
    await _seed(db_session, "2026-07", SettlementStatus.REVIEWED)
    with pytest.raises(BadRequestException):
        await settlement_service.recompute_settlement(db_session, "2026-07")


# ──────────────────────────────────────────────────────────────────
# US1 (010): settleable_periods + settle
# ──────────────────────────────────────────────────────────────────
async def _seed_bill_period(db: AsyncSession, period: str, txn_id: str) -> int:
    """Seed a minimal bill whose transaction_time falls in the given period."""
    from datetime import datetime, timezone

    from src.models.bill import Bill, TransactionStatus
    from src.models.binding import BindingStatus, Customer
    from src.models.organization import Organization

    org = Organization(name="总部", org_type="headquarters", level=1, sort_order=0)
    db.add(org)
    await db.flush()
    await db.refresh(org)

    cust = Customer(
        distributor_id=1, name="患者", phone="13800138000",
        phone_masked="138****8000", id_card_masked="110***********1234",
        binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(cust)
    await db.flush()
    await db.refresh(cust)

    bill = Bill(
        customer_id=cust.id, transaction_id=txn_id,
        transaction_time=datetime(int(period[:4]), int(period[5:7]), 15, tzinfo=timezone.utc),
        paid_amount_cent=100, total_amount_cent=100, transaction_status=TransactionStatus.PAID,
    )
    db.add(bill)
    await db.flush()
    await db.refresh(bill)
    return bill.id


@pytest.mark.asyncio
async def test_settleable_periods_derives_from_bills(db_session: AsyncSession):
    """settleable_periods lists months with bill data."""
    await _seed_bill_period(db_session, "2026-07", "txn_s1")
    periods = await settlement_service.settleable_periods(db_session)
    assert "2026-07" in periods


@pytest.mark.asyncio
async def test_settleable_periods_excludes_pending_and_reviewed(db_session: AsyncSession):
    """pending/reviewed months are not settleable; rejected months are (FR-002)."""
    await _seed_bill_period(db_session, "2026-06", "txn_s2")
    await _seed_bill_period(db_session, "2026-07", "txn_s3")
    await _seed(db_session, "2026-06", SettlementStatus.REVIEWED)
    await _seed(db_session, "2026-07", SettlementStatus.PENDING)

    periods = await settlement_service.settleable_periods(db_session)
    assert "2026-06" not in periods  # reviewed -> frozen
    assert "2026-07" not in periods  # pending -> in flow

    # rejected month becomes settleable again
    await _seed(db_session, "2026-05", SettlementStatus.REJECTED)
    await _seed_bill_period(db_session, "2026-05", "txn_s4")
    periods = await settlement_service.settleable_periods(db_session)
    assert "2026-05" in periods


@pytest.mark.asyncio
async def test_settle_creates_pending_and_report(db_session: AsyncSession):
    """settle computes + creates pending batch + settlement report record (FR-004/FR-005)."""
    from src.models.report import Report

    await _seed_bill_period(db_session, "2026-07", "txn_s5")
    data = await settlement_service.settle(db_session, "2026-07", operator_id=1)
    assert data["status"] == "pending"

    s = (await db_session.execute(select(PerformanceSettlement))).scalars().first()
    assert s.status == SettlementStatus.PENDING

    reports = (await db_session.execute(select(Report))).scalars().all()
    assert len(reports) == 1
    assert reports[0].source == "performance_settlement"
    assert reports[0].period == "2026-07"


@pytest.mark.asyncio
async def test_settle_rejects_reviewed_month(db_session: AsyncSession):
    """settle on a frozen (reviewed) month raises (FR-008)."""
    await _seed_bill_period(db_session, "2026-07", "txn_s6")
    await _seed(db_session, "2026-07", SettlementStatus.REVIEWED)
    with pytest.raises(BadRequestException):
        await settlement_service.settle(db_session, "2026-07", operator_id=1)


@pytest.mark.asyncio
async def test_settle_rejects_non_bill_month(db_session: AsyncSession):
    """settle on a month with no bill data raises (FR-002)."""
    with pytest.raises(BadRequestException):
        await settlement_service.settle(db_session, "2026-07", operator_id=1)


@pytest.mark.asyncio
async def test_settleable_periods_includes_unassigned_mall_only_month_and_open_coordination(
    db_session: AsyncSession,
):
    """Any paid mall source creates a period, even before attribution and while open."""
    from datetime import datetime

    from src.models.performance_evidence import PerformancePeriodVersion
    from tests.mall_consumption_fixtures import add_mall_source, performance_context

    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    assert source.business_period == "2026-07"
    db_session.add(PerformancePeriodVersion(period="2026-07", revision=1, status="open"))
    await db_session.flush()

    assert await settlement_service.settleable_periods(db_session) == ["2026-07"]


@pytest.mark.asyncio
async def test_settleable_periods_does_not_treat_empty_coordination_as_business_data(
    db_session: AsyncSession,
):
    from src.models.performance_evidence import PerformancePeriodVersion

    db_session.add(PerformancePeriodVersion(period="2026-07", revision=1, status="open"))
    await db_session.flush()
    assert "2026-07" not in await settlement_service.settleable_periods(db_session)


@pytest.mark.asyncio
async def test_settleable_periods_uses_beijing_current_month_boundary(
    db_session: AsyncSession, monkeypatch
):
    from datetime import datetime, timezone

    from tests.mall_consumption_fixtures import add_mall_source, performance_context

    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 31, 16, 30), attributed=False
    )
    assert source.business_period == "2026-08"

    class FrozenDateTime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(settlement_service, "datetime", FrozenDateTime)
    assert "2026-08" in await settlement_service.settleable_periods(db_session)


@pytest.mark.asyncio
async def test_settleable_periods_includes_adjustment_only_target_period(
    db_session: AsyncSession,
):
    """An allocated performance adjustment is sufficient business input."""
    from src.models.commission_result import CommissionResult
    from src.models.performance_adjustment import (
        PerformanceAdjustment,
        PerformanceAdjustmentApplication,
    )
    from src.models.performance_rule import RuleType
    from tests.mall_consumption_fixtures import add_frozen_evidence, performance_context

    context = await performance_context(db_session)
    evidence = await add_frozen_evidence(
        db_session,
        context,
        period="2026-07",
        rule_snapshot={"tiers": [{"minCent": 0, "maxCent": None, "ratio": 0.08}]},
        result_presence="not_generated",
        result_absence_reason="below_first_tier",
    )
    target_result = CommissionResult(
        period="2026-08",
        distributor_id=context["distributorId"],
        org_id=context["orgId"],
        rule_type=RuleType.INTRA_ORG,
        base_cent=0,
        ratio="0.08",
        commission_cent=0,
    )
    db_session.add(target_result)
    await db_session.flush()
    adjustment = PerformanceAdjustment(
        adjustment_no="ADJ-T085-ONLY-001",
        origin_period="2026-07",
        origin_result_id=None,
        evidence_id=evidence.id,
        trigger_source_type="mall",
        trigger_source_id=1,
        trigger_version=1,
        beneficiary_id=context["distributorId"],
        rule_type=RuleType.INTRA_ORG.value,
        original_commission_cent=0,
        replayed_commission_cent=100,
        prior_confirmed_adjustment_cent=0,
        delta_cent=100,
        status="reviewed",
        remaining_cent=100,
    )
    db_session.add(adjustment)
    await db_session.flush()
    cancelled_target_result = CommissionResult(
        period="2026-09",
        distributor_id=context["distributorId"],
        org_id=context["orgId"],
        rule_type=RuleType.INTRA_ORG,
        base_cent=0,
        ratio="0.08",
        commission_cent=0,
    )
    db_session.add(cancelled_target_result)
    await db_session.flush()
    db_session.add(
        PerformanceAdjustmentApplication(
            adjustment_id=adjustment.id,
            target_period="2026-08",
            target_result_id=target_result.id,
            allocated_cent=100,
            settled_cent=0,
            status="allocated",
            allocation_key="t085-adjustment-only-period",
        )
    )
    db_session.add(
        PerformanceAdjustmentApplication(
            adjustment_id=adjustment.id,
            target_period="2026-09",
            target_result_id=cancelled_target_result.id,
            allocated_cent=100,
            settled_cent=0,
            status="cancelled",
            allocation_key="t085-cancelled-adjustment-period",
        )
    )
    await db_session.flush()

    periods = await settlement_service.settleable_periods(db_session)
    assert "2026-08" in periods
    assert "2026-09" not in periods
