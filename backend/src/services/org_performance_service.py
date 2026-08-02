"""Org performance service (US5): subtree contribution aggregation for org admins."""

from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ForbiddenException, NotFoundException
from ..models.contribution import ContributionRecord
from ..models.distributor import Distributor, OrgRole
from ..models.organization import Organization
from ..models.user import User
from . import distributor_service, organization_service

_ZERO = Decimal("0.00")


def _dec(v: Optional[str]) -> Decimal:
    try:
        return Decimal(v or "0.00")
    except (InvalidOperation, TypeError):
        return _ZERO


def _fmt(d: Decimal) -> str:
    return format(d, ".2f")


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


def _org_total(org_id: int, children: dict[int, list[int]], member_sums: dict[int, dict]) -> dict:
    """Compute thisMonth/cumulative for an org including all descendants."""
    this = Decimal("0.00")
    cum = Decimal("0.00")
    stack = [org_id]
    while stack:
        current = stack.pop()
        s = member_sums.get(current)
        if s:
            this += s["thisMonth"]
            cum += s["cumulative"]
        for child in children.get(current, []):
            stack.append(child)
    return {"thisMonth": _fmt(this), "cumulative": _fmt(cum)}


async def get_org_performance(
    db: AsyncSession, user_id: int, month: Optional[str] = None
) -> dict:
    """Return org performance for the current user (must be an org admin).

    Aggregates ``contribution_records`` for distributors in the admin's
    authorized org subtree (FR-016). No customer-level detail (FR-015).
    """
    dist = await distributor_service.get_distributor_by_user(db, user_id)
    if dist is None or dist.org_role != OrgRole.ADMIN:
        raise ForbiddenException(message="当前账号非组织管理员，无权限查看")

    name_map, children, org_ids = await _collect_subtree(db, dist.org_id)

    # Distributors in the subtree
    dist_rows = (
        await db.execute(select(Distributor).where(Distributor.org_id.in_(org_ids)))
    ).scalars().all()
    if not dist_rows:
        return {
            "orgId": str(dist.org_id),
            "orgName": name_map.get(dist.org_id),
            "period": month,
            "summary": {"thisMonth": "0.00", "cumulative": "0.00"},
            "subOrgs": [],
            "members": [],
        }

    # Distributor id set in subtree
    dist_ids = {d.id for d in dist_rows}
    dist_by_id: dict[int, Distributor] = {d.id: d for d in dist_rows}

    if not dist_ids:
        return {
            "orgId": str(dist.org_id),
            "orgName": name_map.get(dist.org_id),
            "period": month,
            "summary": {"thisMonth": "0.00", "cumulative": "0.00"},
            "subOrgs": [],
            "members": [],
        }

    contrib_rows = (
        await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.distributor_id.in_(dist_ids)
            )
        )
    ).scalars().all()

    # Per-distributor sums
    member_sums: dict[int, dict] = {}  # org_id -> {thisMonth, cumulative}
    member_detail: dict[int, dict] = {}  # distributor_id -> {thisMonth, cumulative, name}

    for d in dist_rows:
        member_sums.setdefault(d.org_id, {"thisMonth": _ZERO, "cumulative": _ZERO})
        member_detail[d.id] = {"thisMonth": _ZERO, "cumulative": _ZERO}

    for cr in contrib_rows:
        d = dist_by_id.get(cr.distributor_id)
        if d is None:
            continue
        pts = _dec(cr.points)
        member_sums[d.org_id]["cumulative"] += pts
        member_detail[d.id]["cumulative"] += pts
        in_month = month is None or (
            cr.occurred_at and cr.occurred_at.strftime("%Y-%m") == month
        )
        if in_month:
            member_sums[d.org_id]["thisMonth"] += pts
            member_detail[d.id]["thisMonth"] += pts

    # Fill member names
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
            "thisMonth": _fmt(md["thisMonth"]),
            "cumulative": _fmt(md["cumulative"]),
        })

    sub_orgs = []
    for org_id in org_ids:
        if org_id == dist.org_id:
            continue
        total = _org_total(org_id, children, member_sums)
        sub_orgs.append({"orgId": str(org_id), "orgName": name_map.get(org_id), **total})

    summary = _org_total(dist.org_id, children, member_sums)

    return {
        "orgId": str(dist.org_id),
        "orgName": name_map.get(dist.org_id),
        "period": month,
        "summary": summary,
        "subOrgs": sub_orgs,
        "members": members,
    }
