"""Settlement review workflow (008, FR-003/FR-005/FR-012/FR-013).

State machine per period:
  pending -> reviewed (confirm; frozen, never recomputed)
  pending -> rejected (reject with reason; recompute returns to pending)
Concurrency is guarded by conditional UPDATE on status='pending'.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, NotFoundException
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus


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


async def _get_or_404(db: AsyncSession, period: str) -> PerformanceSettlement:
    settlement = (
        await db.execute(select(PerformanceSettlement).where(PerformanceSettlement.period == period))
    ).scalars().first()
    if settlement is None:
        raise NotFoundException(message=f"核算不存在: {period}")
    return settlement


async def review_settlement(db: AsyncSession, period: str, operator_id: int) -> dict:
    """Confirm a pending month's settlement (freezes it)."""
    settlement = await _get_or_404(db, period)
    if settlement.status != SettlementStatus.PENDING:
        raise BadRequestException(message="只有待审核状态的核算可确认")
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
    settlement = await _get_or_404(db, period)
    if settlement.status != SettlementStatus.PENDING:
        raise BadRequestException(message="只有待审核状态的核算可打回")
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
    await db.flush()
    return {
        "period": period,
        "status": SettlementStatus.REJECTED.value,
        "reviewedBy": operator_id,
        "reviewedAt": now.isoformat(),
        "rejectReason": reason,
    }


async def recompute_settlement(db: AsyncSession, period: str) -> dict:
    """Recompute a pending/rejected month. Reviewed (frozen) periods are rejected."""
    settlement = await _get_or_404(db, period)
    if settlement.status == SettlementStatus.REVIEWED:
        raise BadRequestException(message="已确认的核算不能重新计算")

    from .commission_service import compute_commission

    result = await compute_commission(db, period)
    await db.flush()
    return {
        "period": period,
        "status": SettlementStatus.PENDING.value,
        "computed": result.get("computed", 0),
    }
