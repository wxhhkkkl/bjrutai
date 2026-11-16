"""Settlement review workflow (008, FR-003/FR-005/FR-012/FR-013).

State machine per period:
  pending -> reviewed (confirm; frozen, never recomputed)
  pending -> rejected (reject with reason; recompute returns to pending)
Concurrency is guarded by conditional UPDATE on status='pending'.
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, ConflictException, NotFoundException
from ..models.bill import Bill, TransactionStatus
from ..models.mall_consumption import MallConsumption
from ..models.performance_adjustment import PerformanceAdjustmentApplication
from ..models.performance_evidence import PerformanceEvidence
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus
from .performance_period_service import lock_period


def _serialize(s: PerformanceSettlement) -> dict:
    return {
        "period": s.period,
        "status": s.status.value if hasattr(s.status, "value") else str(s.status),
        "reviewedBy": s.reviewed_by,
        "reviewedAt": s.reviewed_at.isoformat() if s.reviewed_at else None,
        "rejectReason": s.reject_reason,
    }


async def get_settlements(db: AsyncSession, period: Optional[str] = None) -> dict:
    """List settlement batches, optionally filtered by period."""
    stmt = select(PerformanceSettlement).order_by(PerformanceSettlement.period.desc())
    if period:
        stmt = stmt.where(PerformanceSettlement.period == period)
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_serialize(s) for s in rows]}


async def settleable_periods(db: AsyncSession) -> list[str]:
    """Return periods that can be settled (FR-002).

    A period is settleable when it has a bill, a mall consumption source, or a
    non-cancelled adjustment application and its settlement is absent or
    ``rejected``. Open period-coordination rows alone are not business data.
    Future Beijing business months, ``pending`` and ``reviewed`` months are
    excluded. Returned sorted ascending.
    """
    bills = (
        await db.execute(
            select(Bill).where(
                Bill.transaction_status.notin_([
                    TransactionStatus.REFUNDED,
                    TransactionStatus.CANCELLED,
                ])
            )
        )
    ).scalars().all()

    bill_months = {
        b.transaction_time.strftime("%Y-%m") for b in bills if b.transaction_time
    }

    mall_months = set(
        (
            await db.execute(
                select(MallConsumption.business_period).distinct().where(
                    MallConsumption.business_period.is_not(None),
                    MallConsumption.business_period != "",
                )
            )
        ).scalars().all()
    )
    adjustment_months = set(
        (
            await db.execute(
                select(PerformanceAdjustmentApplication.target_period)
                .distinct()
                .where(
                    PerformanceAdjustmentApplication.status.in_(["allocated", "consumed"]),
                    PerformanceAdjustmentApplication.target_period.is_not(None),
                    PerformanceAdjustmentApplication.target_period != "",
                )
            )
        ).scalars().all()
    )

    now = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
    current = f"{now.year}-{now.month:02d}"

    excluded: set[str] = set()
    for s in (
        await db.execute(
            select(PerformanceSettlement).where(
                PerformanceSettlement.status.in_([
                    SettlementStatus.PENDING,
                    SettlementStatus.REVIEWED,
                ])
            )
        )
    ).scalars().all():
        excluded.add(s.period)

    periods = sorted(
        m for m in bill_months | mall_months | adjustment_months
        if m and m <= current and m not in excluded
    )
    return periods


async def settle(db: AsyncSession, period: str, operator_id: int) -> dict:
    """Initiate settlement for a settleable month (FR-001/FR-002/FR-004).

    Validates the period is settleable, computes commissions, keeps/creates the
    pending batch, and auto-generates the settlement report record (FR-005).
    """
    if period not in await settleable_periods(db):
        raise BadRequestException(message="该月不可核算（已核算待审核、已冻结或无业务数据）")

    period_row = await lock_period(db, period)
    if period_row.status != "open":
        raise BadRequestException(message="已冻结月份不可重新核算")

    from .commission_service import compute_commission
    from .report_service import ReportService

    result = await compute_commission(db, period)
    from .performance_evidence_service import capture_period_evidence

    await capture_period_evidence(db, period, period_row=period_row)
    await ReportService.ensure_settlement_report(
        db, period, "pending", generated_by=f"User {operator_id}"
    )
    await db.flush()
    return {
        "period": period,
        "status": SettlementStatus.PENDING.value,
        "computed": result.get("computed", 0),
    }


async def review_settlement(db: AsyncSession, period: str, operator_id: int) -> dict:
    """Confirm a pending month's settlement (freezes it)."""
    period_row = await lock_period(db, period)
    settlement = (
        await db.execute(
            select(PerformanceSettlement)
            .where(PerformanceSettlement.period == period)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if settlement is None:
        raise NotFoundException(message=f"核算不存在: {period}")
    if settlement.status != SettlementStatus.PENDING:
        raise BadRequestException(message="只有待审核状态的核算可确认")
    if period_row.status != "open":
        raise ConflictException(message="核算月份已冻结，请刷新后重试")

    from .performance_evidence_service import (
        capture_period_evidence,
        freeze_period_evidence,
        verify_period_evidence,
    )

    evidence_exists = await db.scalar(
        select(PerformanceEvidence.id)
        .where(PerformanceEvidence.period == period)
        .limit(1)
    )
    if period_row.recomputed_revision is None and not evidence_exists:
        await capture_period_evidence(db, period, period_row=period_row)
    fingerprint = await verify_period_evidence(db, period, period_row=period_row)

    from .performance_adjustment_application_service import (
        finalize_adjustments_for_period,
    )

    await finalize_adjustments_for_period(db, period)

    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(PerformanceSettlement)
        .where(
            PerformanceSettlement.period == period,
            PerformanceSettlement.status == SettlementStatus.PENDING,
        )
        .values(status=SettlementStatus.REVIEWED, reviewed_by=operator_id, reviewed_at=now)
    )
    if result.rowcount == 0:
        raise BadRequestException(message="核算状态已变化，请刷新后重试")
    await freeze_period_evidence(
        db,
        period,
        period_row=period_row,
        fingerprint=fingerprint,
        frozen_at=now.replace(tzinfo=None),
    )
    await _sync_settlement_report(db, period, SettlementStatus.REVIEWED.value)
    await db.flush()
    return {
        "period": period,
        "status": SettlementStatus.REVIEWED.value,
        "reviewedBy": operator_id,
        "reviewedAt": now.isoformat(),
        "rejectReason": None,
    }


async def reject_settlement(db: AsyncSession, period: str, operator_id: int, reason: str) -> dict:
    """Reject a pending month's settlement (must record a reason)."""
    reason = (reason or "").strip()
    if not reason:
        raise BadRequestException(message="打回必须填写原因")
    period_row = await lock_period(db, period)
    settlement = (
        await db.execute(
            select(PerformanceSettlement)
            .where(PerformanceSettlement.period == period)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if settlement is None:
        raise NotFoundException(message=f"核算不存在: {period}")
    if settlement.status != SettlementStatus.PENDING:
        raise BadRequestException(message="只有待审核状态的核算可打回")
    if period_row.status != "open":
        raise ConflictException(message="核算月份已冻结，不能打回")
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(PerformanceSettlement)
        .where(
            PerformanceSettlement.period == period,
            PerformanceSettlement.status == SettlementStatus.PENDING,
        )
        .values(
            status=SettlementStatus.REJECTED,
            reviewed_by=operator_id,
            reviewed_at=now,
            reject_reason=reason,
        )
    )
    if result.rowcount == 0:
        raise BadRequestException(message="核算状态已变化，请刷新后重试")
    await _sync_settlement_report(db, period, SettlementStatus.REJECTED.value)
    await db.flush()
    return {
        "period": period,
        "status": SettlementStatus.REJECTED.value,
        "reviewedBy": operator_id,
        "reviewedAt": now.isoformat(),
        "rejectReason": reason,
    }


async def _sync_settlement_report(db: AsyncSession, period: str, status: str) -> None:
    """Keep the settlement report record's status in sync (010, FR-005)."""
    from .report_service import ReportService

    await ReportService.ensure_settlement_report(db, period, status)


async def recompute_settlement(db: AsyncSession, period: str) -> dict:
    """Recompute a pending/rejected month. Reviewed (frozen) periods are rejected."""
    period_row = await lock_period(db, period)
    settlement = (
        await db.execute(
            select(PerformanceSettlement)
            .where(PerformanceSettlement.period == period)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if settlement is None:
        raise NotFoundException(message=f"核算不存在: {period}")
    if settlement.status == SettlementStatus.REVIEWED:
        raise BadRequestException(message="已确认的核算不能重新计算")
    if period_row.status != "open":
        raise BadRequestException(message="已冻结月份不可重新计算")

    from .commission_service import compute_commission
    from .performance_evidence_service import capture_period_evidence

    result = await compute_commission(db, period)
    await capture_period_evidence(db, period, period_row=period_row)
    await _sync_settlement_report(db, period, SettlementStatus.PENDING.value)
    await db.flush()
    return {
        "period": period,
        "status": SettlementStatus.PENDING.value,
        "computed": result.get("computed", 0),
    }
