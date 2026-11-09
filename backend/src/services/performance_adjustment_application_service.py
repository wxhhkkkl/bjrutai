"""Apply reviewed performance differences to later settlement results."""

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ConflictException, NotFoundException, ValidationException
from ..models.commission_result import CommissionResult
from ..models.distributor import Distributor
from ..models.performance_adjustment import (
    PerformanceAdjustment,
    PerformanceAdjustmentApplication,
)
from ..models.performance_rule import RuleType
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus
from .performance_period_service import lock_period


def _rule_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _allocation_key(adjustment_id: int, result_id: int) -> str:
    return f"performance-adjustment:{adjustment_id}:result:{result_id}"


async def apply_adjustment_to_result(
    db: AsyncSession, adjustment_id: int, target_result_id: int
) -> PerformanceAdjustmentApplication | None:
    """Reserve a reviewed adjustment against one later result, at most once.

    Negative adjustments consume only available positive performance. A
    redeemed result is immutable, so the difference remains for a later month.
    """
    initial_adjustment = await db.get(PerformanceAdjustment, adjustment_id)
    if initial_adjustment is None:
        raise NotFoundException(message="绩效调整不存在")
    initial_result = await db.get(CommissionResult, target_result_id)
    if initial_result is None:
        raise NotFoundException(message="目标绩效结果不存在")
    if initial_result.period <= initial_adjustment.origin_period:
        raise ValidationException(message="绩效调整只能应用到原期间之后")

    await lock_period(db, initial_result.period)
    settlement_status = await db.scalar(
        select(PerformanceSettlement.status)
        .where(PerformanceSettlement.period == initial_result.period)
        .with_for_update()
    )
    if settlement_status not in (SettlementStatus.PENDING, SettlementStatus.REVIEWED):
        raise ConflictException(message="目标绩效月份尚未进入核算")

    target = await db.scalar(
        select(CommissionResult)
        .where(CommissionResult.id == target_result_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    adjustment = await db.scalar(
        select(PerformanceAdjustment)
        .where(PerformanceAdjustment.id == adjustment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if adjustment.status != "reviewed":
        raise ConflictException(message="只有已审核绩效调整可以应用")
    if (
        target.period <= adjustment.origin_period
        or target.distributor_id != adjustment.beneficiary_id
        or _rule_value(target.rule_type) != adjustment.rule_type
    ):
        raise ValidationException(message="目标绩效结果与调整对象不匹配")

    existing = await db.scalar(
        select(PerformanceAdjustmentApplication)
        .where(
            PerformanceAdjustmentApplication.adjustment_id == adjustment.id,
            PerformanceAdjustmentApplication.target_result_id == target.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None and existing.status == "consumed":
        return existing
    if existing is not None and existing.status == "allocated" and adjustment.delta_cent > 0:
        return existing
    if target.points_redeemed_at is not None:
        return None
    if adjustment.remaining_cent == 0 and existing is None:
        return None

    target_applications = (
        await db.scalars(
            select(PerformanceAdjustmentApplication)
            .where(
                PerformanceAdjustmentApplication.target_result_id == target.id,
                PerformanceAdjustmentApplication.status.in_(("allocated", "consumed")),
            )
            .order_by(PerformanceAdjustmentApplication.id)
            .with_for_update()
        )
    ).all()
    other_target_delta = sum(
        row.allocated_cent
        for row in target_applications
        if existing is None or row.id != existing.id
    )
    normal_cent = target.commission_cent if target.origin_kind == "normal" else 0
    available_cent = max(0, normal_cent + other_target_delta)

    now = datetime.now(timezone.utc)
    if adjustment.remaining_cent > 0:
        allocation = adjustment.remaining_cent
        adjustment.remaining_cent -= allocation
        status = "allocated"
        settled_cent = 0
        consumed_at = None
    else:
        reserved_elsewhere = int(
            await db.scalar(
                select(
                    func.coalesce(func.sum(PerformanceAdjustmentApplication.allocated_cent), 0)
                ).where(
                    PerformanceAdjustmentApplication.adjustment_id == adjustment.id,
                    PerformanceAdjustmentApplication.status == "allocated",
                    PerformanceAdjustmentApplication.allocated_cent < 0,
                    PerformanceAdjustmentApplication.target_result_id != target.id,
                )
            )
            or 0
        )
        unallocated_debt = adjustment.remaining_cent - reserved_elsewhere
        amount = min(abs(unallocated_debt), available_cent)
        if amount <= 0:
            if existing is not None and existing.status == "allocated":
                existing.allocated_cent = 0
                existing.settled_cent = 0
                existing.status = "cancelled"
                existing.version += 1
            await db.flush()
            return None
        allocation = -amount
        if settlement_status == SettlementStatus.REVIEWED:
            adjustment.remaining_cent -= allocation
            status = "consumed"
            settled_cent = allocation
            consumed_at = now
        else:
            status = "allocated"
            settled_cent = 0
            consumed_at = None

    if existing is None:
        existing = PerformanceAdjustmentApplication(
            adjustment_id=adjustment.id,
            target_period=target.period,
            target_result_id=target.id,
            allocated_cent=allocation,
            settled_cent=settled_cent,
            status=status,
            allocation_key=_allocation_key(adjustment.id, target.id),
            consumed_at=consumed_at,
        )
        db.add(existing)
    else:
        existing.target_period = target.period
        existing.allocated_cent = allocation
        existing.settled_cent = settled_cent
        existing.status = status
        existing.consumed_at = consumed_at
        existing.version += 1

    adjustment.version += 1
    await db.flush()
    return existing


async def apply_adjustments_to_period(db: AsyncSession, target_period: str) -> int:
    """Apply older reviewed adjustments after the period's normal calculation."""
    await lock_period(db, target_period)
    adjustments = (
        await db.scalars(
            select(PerformanceAdjustment)
            .where(
                PerformanceAdjustment.status == "reviewed",
                PerformanceAdjustment.origin_period < target_period,
                PerformanceAdjustment.remaining_cent != 0,
            )
            .order_by(PerformanceAdjustment.origin_period, PerformanceAdjustment.id)
        )
    ).all()
    adjustments = sorted(
        adjustments,
        key=lambda row: (row.delta_cent < 0, row.origin_period, row.id),
    )

    applied = 0
    for adjustment in adjustments:
        target = await db.scalar(
            select(CommissionResult)
            .where(
                CommissionResult.period == target_period,
                CommissionResult.distributor_id == adjustment.beneficiary_id,
                CommissionResult.rule_type == RuleType(adjustment.rule_type),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if target is None and adjustment.remaining_cent > 0:
            distributor = await db.get(Distributor, adjustment.beneficiary_id)
            if distributor is None:
                continue
            target = CommissionResult(
                period=target_period,
                distributor_id=adjustment.beneficiary_id,
                org_id=distributor.org_id,
                rule_type=RuleType(adjustment.rule_type),
                base_cent=0,
                ratio="0.000000",
                commission_cent=0,
                rule_snapshot=None,
                origin_kind="adjustment_only",
            )
            db.add(target)
            await db.flush()
        if target is None:
            # Debt without later positive commission remains unallocated.
            continue
        application = await apply_adjustment_to_result(db, adjustment.id, target.id)
        if application is not None:
            applied += 1
    return applied


async def finalize_adjustments_for_period(db: AsyncSession, period: str) -> int:
    """Finalize negative offsets when the target settlement is confirmed."""
    applications = (
        await db.scalars(
            select(PerformanceAdjustmentApplication)
            .where(
                PerformanceAdjustmentApplication.target_period == period,
                PerformanceAdjustmentApplication.status == "allocated",
                PerformanceAdjustmentApplication.allocated_cent < 0,
            )
            .order_by(PerformanceAdjustmentApplication.id)
            .with_for_update()
        )
    ).all()
    finalized = 0
    for application in applications:
        adjustment = await db.scalar(
            select(PerformanceAdjustment)
            .where(PerformanceAdjustment.id == application.adjustment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if adjustment is None or adjustment.status != "reviewed":
            raise ConflictException(message="待应用的绩效调整状态已变化")
        application.settled_cent = application.allocated_cent
        application.status = "consumed"
        application.consumed_at = datetime.now(timezone.utc)
        application.version += 1
        adjustment.remaining_cent -= application.settled_cent
        adjustment.version += 1
        finalized += 1
    await db.flush()
    return finalized


async def adjustment_summaries_for_results(
    db: AsyncSession, results: list[CommissionResult]
) -> dict[int, dict[str, int]]:
    """Return normal, adjustment, debt, redeemable, and pending-debt amounts."""
    if not results:
        return {}
    result_ids = [row.id for row in results]
    active_apps = (
        await db.execute(
            select(PerformanceAdjustmentApplication, PerformanceAdjustment)
            .join(
                PerformanceAdjustment,
                PerformanceAdjustment.id == PerformanceAdjustmentApplication.adjustment_id,
            )
            .where(
                PerformanceAdjustmentApplication.target_result_id.in_(result_ids),
                PerformanceAdjustmentApplication.status.in_(("allocated", "consumed")),
            )
        )
    ).all()
    apps_by_result: dict[int, list[tuple]] = {}
    for application, adjustment in active_apps:
        apps_by_result.setdefault(application.target_result_id, []).append(
            (application, adjustment)
        )

    identities = {(row.period, row.distributor_id, _rule_value(row.rule_type)) for row in results}
    scopes = [
        and_(
            PerformanceAdjustment.origin_period < period,
            PerformanceAdjustment.beneficiary_id == distributor_id,
            PerformanceAdjustment.rule_type == rule_type,
        )
        for period, distributor_id, rule_type in identities
    ]
    debts = (
        await db.scalars(
            select(PerformanceAdjustment).where(
                PerformanceAdjustment.status == "reviewed",
                PerformanceAdjustment.remaining_cent < 0,
                or_(*scopes),
            )
        )
    ).all()
    debt_ids = [row.id for row in debts]
    reserved_by_adjustment: dict[int, list[PerformanceAdjustmentApplication]] = {}
    if debt_ids:
        reserved = (
            await db.scalars(
                select(PerformanceAdjustmentApplication).where(
                    PerformanceAdjustmentApplication.adjustment_id.in_(debt_ids),
                    PerformanceAdjustmentApplication.status == "allocated",
                    PerformanceAdjustmentApplication.allocated_cent < 0,
                )
            )
        ).all()
        for application in reserved:
            reserved_by_adjustment.setdefault(application.adjustment_id, []).append(application)

    summaries = {}
    for result in results:
        rows = apps_by_result.get(result.id, [])
        confirmed_delta = sum(application.allocated_cent for application, _ in rows)
        applied_debt = sum(
            abs(application.allocated_cent)
            for application, _ in rows
            if application.allocated_cent < 0
        )
        normal = result.commission_cent if result.origin_kind == "normal" else 0
        pending_debt = 0
        for adjustment in debts:
            if (
                adjustment.beneficiary_id != result.distributor_id
                or adjustment.rule_type != _rule_value(result.rule_type)
                or adjustment.origin_period >= result.period
            ):
                continue
            reservations = [
                app
                for app in reserved_by_adjustment.get(adjustment.id, [])
                if app.target_period <= result.period
            ]
            pending_debt += max(
                0,
                abs(adjustment.remaining_cent)
                - sum(abs(app.allocated_cent) for app in reservations),
            )
        summaries[result.id] = {
            "normalCommissionCent": normal,
            "confirmedAdjustmentCent": confirmed_delta,
            "appliedDebtCent": applied_debt,
            "redeemableCent": max(0, normal + confirmed_delta),
            "pendingDebtCent": pending_debt,
        }
    return summaries


async def settle_positive_applications_for_result(
    db: AsyncSession, result_id: int, *, consumed_at: datetime
) -> None:
    """Mark credited adjustment allocations consumed by point redemption."""
    applications = (
        await db.scalars(
            select(PerformanceAdjustmentApplication)
            .where(
                PerformanceAdjustmentApplication.target_result_id == result_id,
                PerformanceAdjustmentApplication.status == "allocated",
                PerformanceAdjustmentApplication.allocated_cent > 0,
            )
            .order_by(PerformanceAdjustmentApplication.id)
            .with_for_update()
        )
    ).all()
    for application in applications:
        application.settled_cent = application.allocated_cent
        application.status = "consumed"
        application.consumed_at = consumed_at
        application.version += 1
    await db.flush()
