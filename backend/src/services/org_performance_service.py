"""Org performance service (US5): subtree 消费金额 aggregation for org admins.

业绩贡献 = 消费金额：按账单（Bill.paid_amount_cent）实时统计，单位为分（整数）。
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ForbiddenException
from ..models.distributor import Distributor, OrgRole
from ..models.organization import Organization
from ..models.user import User
from . import distributor_service
from .consumption_service import consumption_by_distributor


async def _collect_subtree(
    db: AsyncSession, org_id: int
) -> tuple[dict[int, str], dict[int, list[int]], set[int]]:
    """Return (org_name_map, children_map, org_ids) for the subtree of org_id."""
    result = await db.execute(select(Organization))
    all_orgs = result.scalars().all()
    name_map = {o.id: o.name for o in all_orgs}
    children: dict[int, list[int]] = {}
    for o in all_orgs:
        children.setdefault(o.parent_id or 0, []).append(o.id)

    org_ids: set[int] = set()
    stack = [org_id]
    while stack:
        current = stack.pop()
        org_ids.add(current)
        for child in children.get(current, []):
            stack.append(child)
    return name_map, children, org_ids


def _empty(org_id: int, org_name, month: Optional[str]) -> dict:
    return {
        "orgId": str(org_id),
        "orgName": org_name,
        "period": month,
        "summary": {"thisMonth": 0, "cumulative": 0},
        "subOrgs": [],
        "members": [],
    }


async def get_org_performance(
    db: AsyncSession, user_id: int, month: Optional[str] = None
) -> dict:
    """Return org performance for the current user (must be an org admin).

    业绩贡献 = 消费金额（分），按管理组织子树内分销员的 PAID 账单汇总。
    """
    dist = await distributor_service.get_distributor_by_user(db, user_id)
    if dist is None or dist.org_role != OrgRole.ADMIN:
        raise ForbiddenException(message="当前账号非组织管理员，无权限查看")

    name_map, children, org_ids = await _collect_subtree(db, dist.org_id)

    dist_rows = (
        await db.execute(select(Distributor).where(Distributor.org_id.in_(org_ids)))
    ).scalars().all()
    if not dist_rows:
        return _empty(dist.org_id, name_map.get(dist.org_id), month)

    dist_ids = [d.id for d in dist_rows]
    month_cents = await consumption_by_distributor(db, dist_ids, month)
    total_cents = await consumption_by_distributor(db, dist_ids, None)

    member_sums: dict[int, dict] = {}
    member_detail: dict[int, dict] = {}
    for d in dist_rows:
        member_sums.setdefault(d.org_id, {"thisMonth": 0, "cumulative": 0})
        this = month_cents.get(d.id, 0)
        cum = total_cents.get(d.id, 0)
        member_sums[d.org_id]["thisMonth"] += this
        member_sums[d.org_id]["cumulative"] += cum
        member_detail[d.id] = {"thisMonth": this, "cumulative": cum}

    users = (
        await db.execute(select(User.id, User.name).where(User.id.in_({d.user_id for d in dist_rows})))
    ).fetchall()
    user_name_map = {u_id: name for u_id, name in users}
    for d in dist_rows:
        member_detail[d.id]["name"] = user_name_map.get(d.user_id)

    members = []
    for d in dist_rows:
        md = member_detail[d.id]
        members.append({
            "distributorId": str(d.id),
            "orgId": str(d.org_id),
            "name": md["name"],
            "thisMonth": md["thisMonth"],
            "cumulative": md["cumulative"],
        })

    def _org_total(org_id: int) -> dict:
        this, cum = 0, 0
        stack = [org_id]
        while stack:
            current = stack.pop()
            s = member_sums.get(current)
            if s:
                this += s["thisMonth"]
                cum += s["cumulative"]
            for child in children.get(current, []):
                stack.append(child)
        return {"thisMonth": this, "cumulative": cum}

    sub_orgs = []
    for org_id in org_ids:
        if org_id == dist.org_id:
            continue
        sub_orgs.append({"orgId": str(org_id), "orgName": name_map.get(org_id), **_org_total(org_id)})

    return {
        "orgId": str(dist.org_id),
        "orgName": name_map.get(dist.org_id),
        "period": month,
        "summary": _org_total(dist.org_id),
        "subOrgs": sub_orgs,
        "members": members,
    }
