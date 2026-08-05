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


async def _confirmed_month_items(db: AsyncSession, *, distributor_id: int | None = None, org_id: int | None = None) -> list:
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

    months: dict[str, dict] = {}
    for result, _settlement in rows:
        m = months.setdefault(
            result.period,
            {"month": result.period, "status": "confirmed", "intraOrg": None, "orgManagement": None},
        )
        item = {
            "baseCent": result.base_cent,
            "ratio": float(result.ratio),
            "commissionCent": result.commission_cent,
        }
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

    intra = await commission_service.estimate_distributor(db, dist.id, period)
    mgmt = None
    if dist.org_role == OrgRole.ADMIN:
        mgmt = await commission_service.estimate_org_admin(db, dist.id, period)

    confirmed = await _confirmed_month_items(db, distributor_id=dist.id)

    return {
        "currentMonth": {
            "month": period,
            "status": "estimate",
            "intraOrg": intra,
            "orgManagement": mgmt,
        },
        "confirmed": confirmed,
    }


async def org_commission(db: AsyncSession, user_id: int, month: Optional[str]) -> dict:
    """Org-admin view: managed org subtree estimate + confirmed months."""
    dist = await _distributor_for_user(db, user_id)
    if dist.org_role != OrgRole.ADMIN:
        raise ForbiddenException(message="仅组织管理员可查看组织绩效")
    period = month or _current_period()

    preview = await commission_service.preview_org_commission(db, dist.org_id, period)
    members = [
        {
            "distributorId": it["distributorId"],
            "name": it["name"],
            "baseCent": it["baseCent"],
            "ratio": it["ratio"],
            "commissionCent": it["commissionCent"],
        }
        for it in (preview.get("intraOrg") or []) + (preview.get("orgManagement") or [])
    ]
    summary_base = sum(m["baseCent"] for m in members)
    summary_comm = sum(m["commissionCent"] for m in members)

    confirmed = await _confirmed_month_items(db, org_id=dist.org_id)
    confirmed_summaries = []
    for cm in confirmed:
        total = (cm["intraOrg"] or {}).get("commissionCent", 0) + (cm["orgManagement"] or {}).get("commissionCent", 0)
        confirmed_summaries.append({**cm, "summary": {"baseCent": 0, "commissionCent": total}})

    from ..models.organization import Organization

    org = (
        await db.execute(select(Organization).where(Organization.id == dist.org_id))
    ).scalars().first()

    return {
        "orgId": str(dist.org_id),
        "orgName": org.name if org else "",
        "currentMonth": {
            "month": period,
            "status": "estimate",
            "summary": {"baseCent": summary_base, "commissionCent": summary_comm},
            "members": members,
        },
        "confirmed": confirmed_summaries,
    }
