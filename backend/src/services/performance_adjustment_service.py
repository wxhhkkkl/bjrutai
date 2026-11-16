"""Recompute original-period commission differences from frozen evidence."""

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ConflictException, NotFoundException, ValidationException
from ..models.bill import Bill, TransactionStatus
from ..models.binding import Customer
from ..models.commission_result import CommissionResult
from ..models.mall_consumption import MallConsumption
from ..models.mall_operations import MallFile
from ..models.performance_adjustment import (
    PerformanceAdjustment,
    PerformanceAdjustmentApplication,
)
from ..models.performance_evidence import PerformanceEvidence, PerformanceEvidenceSource
from ..models.performance_rule import RuleType
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus
from .consumption_service import period_start_end
from ..models.mall_base import utc_now
from .performance_evidence_service import _timestamp_version
from .performance_period_service import lock_period


def _member_scope(evidence: PerformanceEvidence) -> set[int]:
    if evidence.rule_type == RuleType.ORG_MANAGEMENT.value:
        return {int(identity) for identity in evidence.frozen_members or []}
    return {evidence.distributor_id}


async def _current_legacy_base(
    db: AsyncSession, *, evidence: PerformanceEvidence, member_ids: set[int]
) -> int | None:
    start, end = period_start_end(evidence.period)
    captured = (
        await db.scalars(
            select(PerformanceEvidenceSource).where(
                PerformanceEvidenceSource.evidence_id == evidence.id,
                PerformanceEvidenceSource.source_type == "bill",
            )
        )
    ).all()
    captured_ids = {row.source_id for row in captured}
    base = 0
    for source in captured:
        if source.attributed_distributor_id not in member_ids:
            continue
        bill = await db.get(Bill, source.source_id, populate_existing=True)
        if (
            bill
            and start <= bill.transaction_time < end
            and bill.transaction_status
            not in (TransactionStatus.REFUNDED, TransactionStatus.CANCELLED)
        ):
            base += max(0, int(bill.paid_amount_cent or 0))

    owner = func.coalesce(Bill.attributed_distributor_id, Customer.distributor_id)
    statement = (
        select(Bill, Customer.distributor_id)
        .join(Customer, Customer.id == Bill.customer_id)
        .where(
            owner.in_(member_ids),
            Bill.transaction_time >= start,
            Bill.transaction_time < end,
            Bill.transaction_status.notin_(
                (TransactionStatus.REFUNDED, TransactionStatus.CANCELLED)
            ),
        )
    )
    if captured_ids:
        statement = statement.where(Bill.id.notin_(captured_ids))
    new_rows = (await db.execute(statement)).all()
    if not captured:
        if not new_rows:
            return int(evidence.legacy_base_cent or 0)
        if evidence.legacy_base_cent:
            # Without frozen Bill identities, these current rows may already be
            # represented by the frozen aggregate. Do not guess or double count.
            return None
    base += sum(max(0, int(bill.paid_amount_cent or 0)) for bill, _ in new_rows)
    return base


async def _current_mall_base(db: AsyncSession, *, period: str, member_ids: set[int]) -> int:
    if not member_ids:
        return 0
    return int(
        await db.scalar(
            select(func.coalesce(func.sum(MallConsumption.performance_base_cent), 0)).where(
                MallConsumption.business_period == period,
                MallConsumption.status == "assigned",
                MallConsumption.attributed_distributor_id.in_(member_ids),
            )
        )
        or 0
    )


async def _lock_trigger_source(
    db: AsyncSession,
    *,
    evidence: PerformanceEvidence,
    source_type: str,
    source_id: int,
    trigger_version: int,
    member_ids: set[int],
):
    if source_type == "mall":
        source = await db.scalar(
            select(MallConsumption)
            .where(MallConsumption.id == source_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if source is None:
            raise NotFoundException(message="商城消费来源不存在")
        if (
            source.source_version != trigger_version
            or source.business_period != evidence.period
            or source.status != "assigned"
            or source.attributed_distributor_id not in member_ids
        ):
            raise ConflictException(message="商城消费来源已变化或不在原核算范围")
        return source
    if source_type == "bill":
        source = await db.scalar(
            select(Bill)
            .where(Bill.id == source_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if source is None:
            raise NotFoundException(message="旧账单来源不存在")
        owner = source.attributed_distributor_id
        if owner is None:
            owner = await db.scalar(
                select(Customer.distributor_id).where(Customer.id == source.customer_id)
            )
        if (
            _timestamp_version(source.updated_at) != trigger_version
            or source.transaction_time.strftime("%Y-%m") != evidence.period
            or owner not in member_ids
        ):
            raise ConflictException(message="旧账单来源已变化或不在原核算范围")
        return source
    raise ValidationException(message="不支持的绩效来源类型")


async def propose_adjustment(
    db: AsyncSession,
    evidence_id: int,
    *,
    trigger_source_type: str,
    trigger_source_id: int,
    trigger_version: int,
) -> PerformanceAdjustment:
    """Create one immutable, idempotent adjustment proposal for a frozen anchor."""
    anchor = await db.get(PerformanceEvidence, evidence_id, populate_existing=True)
    if anchor is None:
        raise NotFoundException(message="原期绩效证据不存在")
    period_row = await lock_period(db, anchor.period)
    settlement_status = await db.scalar(
        select(PerformanceSettlement.status)
        .where(PerformanceSettlement.period == anchor.period)
        .with_for_update()
    )
    if settlement_status != SettlementStatus.REVIEWED and period_row.status != "frozen":
        raise ConflictException(message="只有冻结月份可以生成绩效差额")
    period_row.status = "frozen"
    anchor = await db.scalar(
        select(PerformanceEvidence)
        .where(PerformanceEvidence.id == evidence_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    existing = await db.scalar(
        select(PerformanceAdjustment)
        .where(
            PerformanceAdjustment.evidence_id == evidence_id,
            PerformanceAdjustment.trigger_source_type == trigger_source_type,
            PerformanceAdjustment.trigger_source_id == trigger_source_id,
            PerformanceAdjustment.trigger_version == trigger_version,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        return existing

    member_ids = _member_scope(anchor)
    await _lock_trigger_source(
        db,
        evidence=anchor,
        source_type=trigger_source_type,
        source_id=trigger_source_id,
        trigger_version=trigger_version,
        member_ids=member_ids,
    )

    prior_confirmed = int(
        await db.scalar(
            select(func.coalesce(func.sum(PerformanceAdjustment.delta_cent), 0)).where(
                PerformanceAdjustment.evidence_id == evidence_id,
                PerformanceAdjustment.status == "reviewed",
            )
        )
        or 0
    )
    original_commission = int(anchor.original_commission_cent)
    rule_snapshot = anchor.rule_snapshot or {}
    tiers = rule_snapshot.get("tiers") if isinstance(rule_snapshot, dict) else None
    manual_required = (
        anchor.evidence_status != "complete"
        or not isinstance(tiers, list)
        or not tiers
        or anchor.result_presence not in {"present", "not_generated"}
    )
    replayed_commission = 0
    if not manual_required:
        try:
            from .commission_service import _apply_tiers

            legacy_base = await _current_legacy_base(db, evidence=anchor, member_ids=member_ids)
            if legacy_base is None:
                manual_required = True
            else:
                replayed_base = legacy_base + await _current_mall_base(
                    db, period=anchor.period, member_ids=member_ids
                )
                ratio = _apply_tiers(tiers, replayed_base)
                replayed_commission = int(round(replayed_base * ratio))
        except (KeyError, TypeError, ValueError):
            manual_required = True
            replayed_commission = 0

    delta = replayed_commission - original_commission - prior_confirmed
    result = PerformanceAdjustment(
        adjustment_no=f"PA{uuid4().hex[:30]}",
        origin_period=anchor.period,
        origin_result_id=anchor.result_id,
        evidence_id=anchor.id,
        trigger_source_type=trigger_source_type,
        trigger_source_id=trigger_source_id,
        trigger_version=trigger_version,
        beneficiary_id=anchor.distributor_id,
        rule_type=anchor.rule_type,
        original_commission_cent=original_commission,
        replayed_commission_cent=replayed_commission,
        prior_confirmed_adjustment_cent=prior_confirmed,
        delta_cent=delta,
        status="manual_required" if manual_required else "proposed",
        reason=(
            "原期资格或规则证据不完整，需人工补证"
            if manual_required
            else "按冻结原期证据重算，待审核"
        ),
        remaining_cent=delta,
    )
    db.add(result)
    await db.flush()
    return result


def _evidence_is_reviewable(anchor: PerformanceEvidence) -> bool:
    snapshot = anchor.rule_snapshot if isinstance(anchor.rule_snapshot, dict) else {}
    tiers = snapshot.get("tiers")
    if (
        anchor.evidence_status != "complete"
        or not isinstance(tiers, list)
        or not tiers
        or anchor.result_presence not in {"present", "not_generated"}
    ):
        return False
    if anchor.rule_type == RuleType.ORG_MANAGEMENT.value and not anchor.frozen_members:
        return False
    return True


def _serialize_adjustment(
    adjustment: PerformanceAdjustment,
    anchor: PerformanceEvidence,
) -> dict:
    return {
        "id": str(adjustment.id),
        "adjustmentNo": adjustment.adjustment_no,
        "originPeriod": adjustment.origin_period,
        "originResultId": (
            str(adjustment.origin_result_id) if adjustment.origin_result_id else None
        ),
        "beneficiaryId": str(adjustment.beneficiary_id),
        "ruleType": adjustment.rule_type,
        "originalCommissionCent": adjustment.original_commission_cent,
        "replayedCommissionCent": adjustment.replayed_commission_cent,
        "priorConfirmedAdjustmentCent": adjustment.prior_confirmed_adjustment_cent,
        "deltaCent": adjustment.delta_cent,
        "remainingCent": adjustment.remaining_cent,
        "status": adjustment.status,
        "evidenceStatus": anchor.evidence_status,
        "version": adjustment.version,
        "originEvidenceId": str(anchor.id),
        "originResultPresence": anchor.result_presence,
        "evidenceFileIds": [str(file_id) for file_id in adjustment.evidence_file_ids or []],
        "reason": adjustment.reason,
    }


async def _adjustment_and_anchor(
    db: AsyncSession, adjustment_id: int
) -> tuple[PerformanceAdjustment, PerformanceEvidence]:
    row = (
        await db.execute(
            select(PerformanceAdjustment, PerformanceEvidence)
            .join(PerformanceEvidence, PerformanceEvidence.id == PerformanceAdjustment.evidence_id)
            .where(PerformanceAdjustment.id == adjustment_id)
        )
    ).first()
    if row is None:
        raise NotFoundException(message="绩效差额不存在")
    return row


async def _serialize_adjustments(
    db: AsyncSession, adjustment_rows: list[PerformanceAdjustment]
) -> list[dict]:
    if not adjustment_rows:
        return []
    anchors = (
        await db.scalars(
            select(PerformanceEvidence).where(
                PerformanceEvidence.id.in_({row.evidence_id for row in adjustment_rows})
            )
        )
    ).all()
    anchors_by_id = {anchor.id: anchor for anchor in anchors}
    return [
        _serialize_adjustment(row, anchors_by_id[row.evidence_id])
        for row in adjustment_rows
        if row.evidence_id in anchors_by_id
    ]


async def list_performance_adjustments(
    db: AsyncSession, *, cursor_id: int | None, page_size: int
) -> dict:
    filters = [PerformanceAdjustment.id < cursor_id] if cursor_id is not None else []
    total = int(await db.scalar(select(func.count(PerformanceAdjustment.id))) or 0)
    rows = (
        await db.scalars(
            select(PerformanceAdjustment)
            .where(*filters)
            .order_by(PerformanceAdjustment.id.desc())
            .limit(page_size + 1)
        )
    ).all()
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    items = await _serialize_adjustments(db, page_rows)
    return {
        "items": items,
        "nextCursorId": page_rows[-1].id if has_more and page_rows else None,
        "total": total,
    }


async def get_performance_adjustment(db: AsyncSession, adjustment_id: int) -> dict:
    adjustment, anchor = await _adjustment_and_anchor(db, adjustment_id)
    return _serialize_adjustment(adjustment, anchor)


async def _lock_adjustment_context(
    db: AsyncSession, adjustment_id: int
) -> tuple[PerformanceAdjustment, PerformanceEvidence]:
    hint = await db.get(PerformanceAdjustment, adjustment_id)
    if hint is None:
        raise NotFoundException(message="绩效差额不存在")

    period_row = await lock_period(db, hint.origin_period)
    settlement_status = await db.scalar(
        select(PerformanceSettlement.status)
        .where(PerformanceSettlement.period == hint.origin_period)
        .with_for_update()
    )
    if settlement_status != SettlementStatus.REVIEWED or period_row.status != "frozen":
        raise ConflictException(message="原期绩效尚未完成冻结")

    anchor = await db.scalar(
        select(PerformanceEvidence)
        .where(PerformanceEvidence.id == hint.evidence_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if anchor is None:
        raise ConflictException(message="原期绩效证据已不存在")
    adjustment = await db.scalar(
        select(PerformanceAdjustment)
        .where(PerformanceAdjustment.id == adjustment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return adjustment, anchor


async def _prior_confirmed_adjustments(
    db: AsyncSession, *, evidence_id: int, exclude_id: int | None = None
) -> int:
    statement = select(func.coalesce(func.sum(PerformanceAdjustment.delta_cent), 0)).where(
        PerformanceAdjustment.evidence_id == evidence_id,
        PerformanceAdjustment.status == "reviewed",
    )
    if exclude_id is not None:
        statement = statement.where(PerformanceAdjustment.id != exclude_id)
    return int(await db.scalar(statement) or 0)


async def review_performance_adjustment(
    db: AsyncSession,
    *,
    adjustment_id: int,
    expected_version: int,
    admin_id: int,
) -> PerformanceAdjustment:
    adjustment, anchor = await _lock_adjustment_context(db, adjustment_id)
    if adjustment.version != expected_version:
        raise ConflictException(message="绩效差额版本已变化，请刷新后重试")
    if adjustment.status != "proposed" or not _evidence_is_reviewable(anchor):
        raise ConflictException(message="该绩效差额证据不足或当前状态不可审核")

    prior_confirmed = await _prior_confirmed_adjustments(
        db, evidence_id=anchor.id, exclude_id=adjustment.id
    )
    if prior_confirmed != adjustment.prior_confirmed_adjustment_cent:
        raise ConflictException(message="原期已有其他差额先完成审核，请补证重算后再审核")

    adjustment.status = "reviewed"
    adjustment.reviewed_by = admin_id
    adjustment.reviewed_at = utc_now()
    adjustment.remaining_cent = adjustment.delta_cent
    adjustment.version += 1
    await db.flush()
    return adjustment


async def reject_performance_adjustment(
    db: AsyncSession,
    *,
    adjustment_id: int,
    expected_version: int,
    admin_id: int,
    reason: str,
) -> PerformanceAdjustment:
    adjustment, _anchor = await _lock_adjustment_context(db, adjustment_id)
    if adjustment.version != expected_version:
        raise ConflictException(message="绩效差额版本已变化，请刷新后重试")
    if adjustment.status not in {"proposed", "manual_required"}:
        raise ConflictException(message="该绩效差额当前状态不可拒绝")

    adjustment.status = "rejected"
    adjustment.reviewed_by = admin_id
    adjustment.reviewed_at = utc_now()
    adjustment.reason = reason
    adjustment.remaining_cent = 0
    adjustment.version += 1
    await db.flush()
    return adjustment


async def reconcile_performance_adjustment(
    db: AsyncSession,
    *,
    adjustment_id: int,
    expected_version: int,
    evidence_file_ids: list[int],
    admin_id: int,
    reason: str,
) -> tuple[PerformanceAdjustment, str, str]:
    adjustment, anchor = await _lock_adjustment_context(db, adjustment_id)
    if adjustment.version != expected_version:
        raise ConflictException(message="绩效差额版本已变化，请刷新后重试")
    if adjustment.status not in {"proposed", "manual_required", "rejected"}:
        raise ConflictException(message="已确认差额不能再补证修改")

    requested_ids = sorted(set(evidence_file_ids))
    files = (
        await db.scalars(
            select(MallFile)
            .where(MallFile.id.in_(requested_ids))
            .order_by(MallFile.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(files) != len(requested_ids):
        raise NotFoundException(message="补证文件不存在")

    current_ids = {int(value) for value in adjustment.evidence_file_ids or []}
    if len(current_ids.union(requested_ids)) > 5:
        raise ValidationException(message="单条绩效差额最多关联5份补证")
    now = utc_now()
    for file in files:
        if (
            file.purpose != "performance_adjustment_evidence"
            or file.owner_actor_type != "admin"
            or file.status not in {"verified", "bound"}
            or file.expires_at > now
        ):
            raise ValidationException(message="补证文件未核验或用途不匹配")
        file.status = "bound"
        file.version += 1

    adjustment.evidence_file_ids = sorted(current_ids.union(requested_ids))
    previous_status = adjustment.status
    if _evidence_is_reviewable(anchor):
        adjustment.prior_confirmed_adjustment_cent = await _prior_confirmed_adjustments(
            db, evidence_id=anchor.id, exclude_id=adjustment.id
        )
        adjustment.delta_cent = (
            adjustment.replayed_commission_cent
            - adjustment.original_commission_cent
            - adjustment.prior_confirmed_adjustment_cent
        )
        adjustment.remaining_cent = 0
        adjustment.status = "proposed"
    else:
        adjustment.status = "manual_required"
        adjustment.remaining_cent = 0
    adjustment.reason = reason
    adjustment.reviewed_by = None
    adjustment.reviewed_at = None
    adjustment.version += 1
    await db.flush()
    return adjustment, previous_status, adjustment.status


async def get_net_entitlement(db: AsyncSession, result_id: int) -> dict:
    result = await db.get(CommissionResult, result_id, populate_existing=True)
    if result is None:
        raise NotFoundException(message="绩效结果不存在")
    settlement_status = await db.scalar(
        select(PerformanceSettlement.status).where(PerformanceSettlement.period == result.period)
    )
    if settlement_status != SettlementStatus.REVIEWED:
        raise ConflictException(message="仅可查询已审核月份的净可兑现额")

    from .performance_adjustment_application_service import (
        adjustment_summaries_for_results,
    )

    amounts = (await adjustment_summaries_for_results(db, [result]))[result.id]
    applications = (
        await db.scalars(
            select(PerformanceAdjustmentApplication).where(
                PerformanceAdjustmentApplication.target_result_id == result.id
            )
        )
    ).all()
    snapshot_version = 1 + sum(row.version for row in applications)
    if result.points_redeemed_at is not None:
        snapshot_version += 1
    return {
        "resultId": str(result.id),
        "period": result.period,
        "normalCommissionCent": amounts["normalCommissionCent"],
        "confirmedAdjustmentCent": amounts["confirmedAdjustmentCent"],
        "appliedDebtCent": amounts["appliedDebtCent"],
        "redeemableCent": amounts["redeemableCent"],
        "pendingDebtCent": amounts["pendingDebtCent"],
        "redeemedPointsX100": result.redeemed_points_x100,
        "version": snapshot_version,
    }
