"""Mini-program performance view service (008, US3).

Promoter sees own commission estimate + confirmed months; org admin sees the
managed org subtree view. Only commission amounts are exposed (FR-009); values
are in cents.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ForbiddenException, NotFoundException
from ..models.commission_result import CommissionResult
from ..models.distributor import Distributor, OrgRole
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus
from . import commission_service


def _current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


def _rule_type_str(rt) -> str:
    return rt.value if hasattr(rt, "value") else str(rt)


async def _distributor_for_user(db: AsyncSession, user_id: int) -> Distributor:
    dist = (
        await db.execute(select(Distributor).where(Distributor.user_id == user_id))
    ).scalars().first()
    if dist is None:
        raise NotFoundException(message="分销员不存在")
    return dist


async def _confirmed_month_items(
    db: AsyncSession,
    *,
    distributor_id: int | None = None,
    org_id: int | None = None,
) -> list:
    """Confirmed months (settlement reviewed) with commission items, newest first."""
    stmt = (
        select(CommissionResult, PerformanceSettlement)
        .join(PerformanceSettlement, PerformanceSettlement.period == CommissionResult.period)
        .where(PerformanceSettlement.status == SettlementStatus.REVIEWED)
    )
    if distributor_id is not None:
        stmt = stmt.where(CommissionResult.distributor_id == distributor_id)
    if org_id is not None:
        subtree_ids = await commission_service._org_subtree_ids(db, org_id)
        stmt = stmt.where(CommissionResult.org_id.in_(subtree_ids))
    stmt = stmt.order_by(CommissionResult.period.desc())
    rows = (await db.execute(stmt)).all()
    from .performance_adjustment_application_service import (
        adjustment_summaries_for_results,
    )

    summaries = await adjustment_summaries_for_results(
        db, [result for result, _settlement in rows]
    )

    months: dict[str, dict] = {}
    for result, _settlement in rows:
        m = months.setdefault(
            result.period,
            {
                "month": result.period,
                "status": "confirmed",
                "intraOrg": None,
                "orgManagement": None,
            },
        )
        item = _commission_item(result, summaries[result.id])
        key = _rule_type_str(result.rule_type)
        if key == "intra_org":
            m["intraOrg"] = item
        else:
            m["orgManagement"] = item
    return list(months.values())


async def my_commission(db: AsyncSession, user_id: int, month: Optional[str]) -> dict:
    """Promoter's own estimate (current/selected month) + confirmed history."""
    dist = await _distributor_for_user(db, user_id)
    period = month or _current_period()
    settlement = (
        await db.execute(
            select(PerformanceSettlement).where(PerformanceSettlement.period == period)
        )
    ).scalars().first()
    if settlement and settlement.status == SettlementStatus.REVIEWED:
        frozen_rows = (
            await db.execute(
                select(CommissionResult).where(
                    CommissionResult.period == period,
                    CommissionResult.distributor_id == dist.id,
                )
            )
        ).scalars().all()
        from .performance_adjustment_application_service import (
            adjustment_summaries_for_results,
        )

        summaries = await adjustment_summaries_for_results(db, frozen_rows)
        intra = next(
            (
                _commission_item(row, summaries[row.id])
                for row in frozen_rows
                if _rule_type_str(row.rule_type) == "intra_org"
            ),
            None,
        )
        mgmt = next(
            (
                _commission_item(row, summaries[row.id])
                for row in frozen_rows
                if _rule_type_str(row.rule_type) == "org_management"
            ),
            None,
        )
        points_balance = sum(
            summaries[row.id]["redeemableCent"]
            for row in frozen_rows
            if row.points_redeemed_at is None
        ) / 100
        month_status = "confirmed"
    else:
        intra = await commission_service.estimate_distributor(db, dist.id, period)
        mgmt = None
        if dist.org_role == OrgRole.ADMIN:
            mgmt = await commission_service.estimate_org_admin(db, dist.id, period)
        pending_rows = (
            await db.scalars(
                select(CommissionResult).where(
                    CommissionResult.period == period,
                    CommissionResult.distributor_id == dist.id,
                )
            )
        ).all()
        from .performance_adjustment_application_service import (
            adjustment_summaries_for_results,
        )

        pending_summaries = await adjustment_summaries_for_results(db, pending_rows)
        pending_by_rule = {
            _rule_type_str(row.rule_type): row for row in pending_rows
        }
        intra = _attach_adjustment_summary(
            intra,
            pending_by_rule.get("intra_org"),
            pending_summaries,
        )
        mgmt = _attach_adjustment_summary(
            mgmt,
            pending_by_rule.get("org_management"),
            pending_summaries,
        )
        points_balance = await commission_service.points_balance_for_distributor(
            db, dist.id, period, estimated_commissions=[intra, mgmt]
        )
        month_status = "estimate"

    confirmed = await _confirmed_month_items(db, distributor_id=dist.id)

    return {
        "currentMonth": {
            "month": period,
            "status": month_status,
            "intraOrg": intra,
            "orgManagement": mgmt,
            "pointsBalance": points_balance,
        },
        "confirmed": confirmed,
    }


def _commission_item(
    result: CommissionResult, amounts: dict[str, int] | None = None
) -> dict:
    if amounts is None:
        normal = result.commission_cent if result.origin_kind == "normal" else 0
        amounts = {
            "normalCommissionCent": normal,
            "confirmedAdjustmentCent": 0,
            "appliedDebtCent": 0,
            "redeemableCent": max(0, normal),
            "pendingDebtCent": 0,
        }
    return {
        "baseCent": result.base_cent,
        "ratio": float(result.ratio),
        "commissionCent": amounts["normalCommissionCent"],
        **amounts,
        "originKind": result.origin_kind,
    }


def _attach_adjustment_summary(
    item: dict | None,
    result: CommissionResult | None,
    summaries: dict[int, dict[str, int]],
) -> dict | None:
    if item is None:
        if result is None or result.origin_kind != "adjustment_only":
            return None
        return _commission_item(result, summaries[result.id])

    normal = int(item.get("commissionCent", 0) or 0)
    amounts = summaries.get(result.id, {}) if result is not None else {}
    adjustment = int(amounts.get("confirmedAdjustmentCent", 0))
    return {
        **item,
        "commissionCent": normal,
        "normalCommissionCent": normal,
        "confirmedAdjustmentCent": adjustment,
        "appliedDebtCent": int(amounts.get("appliedDebtCent", 0)),
        "redeemableCent": max(0, normal + adjustment),
        "pendingDebtCent": int(amounts.get("pendingDebtCent", 0)),
        "originKind": result.origin_kind if result is not None else "normal",
    }


async def org_commission(db: AsyncSession, user_id: int, month: Optional[str]) -> dict:
    """Org-admin view: managed org subtree estimate + confirmed months."""
    dist = await _distributor_for_user(db, user_id)
    if dist.org_role != OrgRole.ADMIN:
        raise ForbiddenException(message="仅组织管理员可查看组织绩效")
    period = month or _current_period()

    preview = await commission_service.preview_org_commission(db, dist.org_id, period)
    settlement = (
        await db.execute(
            select(PerformanceSettlement).where(PerformanceSettlement.period == period)
        )
    ).scalars().first()
    month_status = (
        "confirmed"
        if settlement and settlement.status == SettlementStatus.REVIEWED
        else "estimate"
    )
    members = [
        {
            "distributorId": it["distributorId"],
            "name": it["name"],
            "baseCent": it["baseCent"],
            "ratio": it["ratio"],
            "commissionCent": it["commissionCent"],
            "normalCommissionCent": it.get("normalCommissionCent", it["commissionCent"]),
            "confirmedAdjustmentCent": it.get("confirmedAdjustmentCent", 0),
            "appliedDebtCent": it.get("appliedDebtCent", 0),
            "redeemableCent": it.get("redeemableCent", it["commissionCent"]),
            "pendingDebtCent": it.get("pendingDebtCent", 0),
            "originKind": it.get("originKind", "normal"),
            "ruleType": it.get("ruleType"),
        }
        for it in (preview.get("intraOrg") or []) + (preview.get("orgManagement") or [])
    ]
    summary_base = sum(m["baseCent"] for m in members)
    summary_comm = sum(m["normalCommissionCent"] for m in members)
    summary_adjustment = sum(m["confirmedAdjustmentCent"] for m in members)
    summary_debt = sum(m["appliedDebtCent"] for m in members)
    summary_redeemable = sum(m["redeemableCent"] for m in members)
    summary_pending_debt = sum(m["pendingDebtCent"] for m in members)

    confirmed = await _confirmed_month_items(db, org_id=dist.org_id)
    confirmed_summaries = []
    for cm in confirmed:
        items = [item for item in (cm["intraOrg"], cm["orgManagement"]) if item]
        total = sum(item.get("normalCommissionCent", 0) for item in items)
        confirmed_summaries.append(
            {
                **cm,
                "summary": {
                    "baseCent": 0,
                    "commissionCent": total,
                    "normalCommissionCent": total,
                    "confirmedAdjustmentCent": sum(
                        item.get("confirmedAdjustmentCent", 0) for item in items
                    ),
                    "appliedDebtCent": sum(
                        item.get("appliedDebtCent", 0) for item in items
                    ),
                    "redeemableCent": sum(
                        item.get("redeemableCent", 0) for item in items
                    ),
                    "pendingDebtCent": sum(
                        item.get("pendingDebtCent", 0) for item in items
                    ),
                },
            }
        )

    from ..models.organization import Organization

    org = (
        await db.execute(select(Organization).where(Organization.id == dist.org_id))
    ).scalars().first()

    return {
        "orgId": str(dist.org_id),
        "orgName": org.name if org else "",
        "currentMonth": {
            "month": period,
            "status": month_status,
            "summary": {
                "baseCent": summary_base,
                "commissionCent": summary_comm,
                "normalCommissionCent": summary_comm,
                "confirmedAdjustmentCent": summary_adjustment,
                "appliedDebtCent": summary_debt,
                "redeemableCent": summary_redeemable,
                "pendingDebtCent": summary_pending_debt,
            },
            "members": members,
        },
        "confirmed": confirmed_summaries,
    }
