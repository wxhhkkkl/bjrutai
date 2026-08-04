"""Admin contribution dashboard service — aggregation queries (FR-001~FR-008).

Provides stats, monthly trend, org/person rankings, bound-count rankings and
latest-30 details, all aggregated in real time from existing tables.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import cast

from ..models.binding import BindingStatus, Customer
from ..models.contribution import ContributionRecord
from ..models.distributor import Distributor, DistributorStatus
from ..models.organization import Organization
from ..models.user import User
from . import distributor_service, organization_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _month_bounds(month: str) -> tuple[datetime, datetime]:
    year, m = (int(x) for x in month.split("-"))
    start = datetime(year, m, 1)
    if m == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, m + 1, 1)
    return start, end


def _points_col():
    """CAST points (stored as string) to numeric for SUM."""
    return cast(ContributionRecord.points, Numeric(20, 2))


def _month_labels(n: int, end_month: str) -> list[str]:
    """Return the last ``n`` months ending at ``end_month`` (YYYY-MM)."""
    y, m = (int(x) for x in end_month.split("-"))
    labels = []
    for i in range(n - 1, -1, -1):
        total = y * 12 + (m - 1) - i
        yy, mm = divmod(total, 12)
        labels.append(f"{yy}-{mm + 1:02d}")
    return labels


async def _subtree_org_ids(db: AsyncSession, org_id: Optional[int]) -> Optional[set[int]]:
    if org_id is None:
        return None
    subtree = await organization_service.get_subtree(db, org_id)
    return distributor_service._collect_org_ids(subtree)


async def _scope_distributor_ids(db: AsyncSession, org_id: Optional[int]) -> Optional[set[int]]:
    org_ids = await _subtree_org_ids(db, org_id)
    if org_ids is None:
        return None
    result = await db.execute(select(Distributor.id).where(Distributor.org_id.in_(org_ids)))
    return set(result.scalars().all())


async def _person_map(db: AsyncSession, distributor_ids) -> dict[int, tuple[Optional[str], Optional[int]]]:
    if not distributor_ids:
        return {}
    result = await db.execute(
        select(Distributor.id, User.name, Distributor.org_id)
        .join(User, User.id == Distributor.user_id)
        .where(Distributor.id.in_(distributor_ids))
    )
    return {did: (name, org_id) for did, name, org_id in result.all()}


async def _org_name_map(db: AsyncSession, org_ids) -> dict[int, Optional[str]]:
    if not org_ids:
        return {}
    result = await db.execute(select(Organization.id, Organization.name).where(Organization.id.in_(org_ids)))
    return dict(result.all())


def _assign_ranks(pairs: list) -> list:
    """Given sorted (value, payload) pairs, attach dense rank (ties share a rank)."""
    items = []
    prev_val, prev_rank = None, 0
    for i, (val, payload) in enumerate(pairs, start=1):
        rank = prev_rank if prev_val == val else i
        prev_val, prev_rank = val, rank
        items.append((rank, payload))
    return items


# ---------------------------------------------------------------------------
# US1: dashboard (stats + trend + latest 30)
# ---------------------------------------------------------------------------
async def get_dashboard(
    db: AsyncSession,
    month: str,
    period: str = "12m",
    org_id: Optional[int] = None,
) -> dict:
    start, end = _month_bounds(month)
    dist_ids = await _scope_distributor_ids(db, org_id)
    org_ids = await _subtree_org_ids(db, org_id)

    def contrib_where(extra_start=None, extra_end=None):
        conds = []
        if extra_start is not None:
            conds.append(ContributionRecord.occurred_at >= extra_start)
        if extra_end is not None:
            conds.append(ContributionRecord.occurred_at < extra_end)
        if dist_ids is not None:
            conds.append(ContributionRecord.distributor_id.in_(dist_ids))
        return conds

    # Stats
    monthly = float((await db.execute(
        select(func.sum(_points_col())).where(*contrib_where(extra_start=start, extra_end=end))
    )).scalar() or 0)
    total = float((await db.execute(
        select(func.sum(_points_col())).where(*contrib_where())
    )).scalar() or 0)

    org_count_stmt = select(func.count(Organization.id))
    if org_ids is not None:
        org_count_stmt = org_count_stmt.where(Organization.id.in_(org_ids))
    org_count = (await db.execute(org_count_stmt)).scalar() or 0

    person_stmt = select(func.count(Distributor.id)).where(Distributor.status == DistributorStatus.ACTIVE)
    if dist_ids is not None:
        person_stmt = person_stmt.where(Distributor.id.in_(dist_ids))
    person_count = (await db.execute(person_stmt)).scalar() or 0

    bound_stmt = select(func.count(Customer.id)).where(Customer.binding_status == BindingStatus.BOUND)
    if dist_ids is not None:
        bound_stmt = bound_stmt.where(Customer.distributor_id.in_(dist_ids))
    bound_count = (await db.execute(bound_stmt)).scalar() or 0

    # Trend: last N months (DB-agnostic Python aggregation)
    num_months = int(period.replace("m", "")) if period.endswith("m") else 12
    trend_labels = _month_labels(num_months, month)
    trend_start = datetime(int(trend_labels[0][:4]), int(trend_labels[0][5:7]), 1)
    trend_rows = (await db.execute(
        select(ContributionRecord.occurred_at, _points_col()).where(*contrib_where(extra_start=trend_start))
    )).all()
    trend_map: dict[str, float] = {}
    for occurred, pts in trend_rows:
        if occurred is None:
            continue
        key = f"{occurred.year}-{occurred.month:02d}"
        trend_map[key] = trend_map.get(key, 0.0) + float(pts or 0)
    trend = [{"month": m, "points": trend_map.get(m, 0.0)} for m in trend_labels]

    # Latest 30
    latest_stmt = (
        select(ContributionRecord)
        .where(*contrib_where())
        .order_by(ContributionRecord.occurred_at.desc(), ContributionRecord.id.desc())
        .limit(30)
    )
    latest_rows = (await db.execute(latest_stmt)).scalars().all()
    person_map = await _person_map(db, {c.distributor_id for c in latest_rows})
    org_name_map = await _org_name_map(db, {o for _, o in person_map.values()})
    latest = []
    for c in latest_rows:
        name, c_org = person_map.get(c.distributor_id, (None, None))
        latest.append({
            "id": str(c.id),
            "distributorId": str(c.distributor_id),
            "personName": name,
            "orgName": org_name_map.get(c_org),
            "title": c.title,
            "category": c.category.value if hasattr(c.category, "value") else str(c.category),
            "points": float(c.points or 0),
            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
            "occurredAt": c.occurred_at.isoformat() if c.occurred_at else None,
        })

    return {
        "stats": {"monthlyPoints": monthly, "totalPoints": total, "orgCount": org_count,
                  "personCount": person_count, "boundUserCount": bound_count},
        "trend": trend,
        "latest": latest,
    }


# ---------------------------------------------------------------------------
# US2: org monthly ranking
# ---------------------------------------------------------------------------
async def org_ranking(
    db: AsyncSession, month: str, org_id: Optional[int] = None, page: int = 1, page_size: int = 20
) -> dict:
    start, end = _month_bounds(month)
    org_ids = await _subtree_org_ids(db, org_id)
    pts_expr = func.sum(_points_col()).label("pts")

    stmt = (
        select(Distributor.org_id.label("oid"), pts_expr)
        .join(ContributionRecord, ContributionRecord.distributor_id == Distributor.id)
        .where(ContributionRecord.occurred_at >= start, ContributionRecord.occurred_at < end)
        .group_by(Distributor.org_id)
    )
    if org_ids is not None:
        stmt = stmt.where(Distributor.org_id.in_(org_ids))
    rows = (await db.execute(stmt.order_by(pts_expr.desc()))).all()

    name_map = await _org_name_map(db, {oid for oid, _ in rows})
    pts_by_org = {oid: float(pts or 0) for oid, pts in rows}
    ranked = _assign_ranks([(pts_by_org[oid], oid) for oid, _ in rows])
    items = [{"rank": rank, "orgId": str(oid), "orgName": name_map.get(oid), "points": pts_by_org[oid]}
             for rank, oid in ranked]
    total = len(items)
    return {"items": items[(page - 1) * page_size: page * page_size], "total": total,
            "page": page, "pageSize": page_size, "hasMore": page * page_size < total}


# ---------------------------------------------------------------------------
# US3: person monthly ranking
# ---------------------------------------------------------------------------
async def persons_ranking(
    db: AsyncSession, month: str, org_id: Optional[int] = None, page: int = 1, page_size: int = 20
) -> dict:
    start, end = _month_bounds(month)
    dist_ids = await _scope_distributor_ids(db, org_id)
    pts_expr = func.sum(_points_col()).label("pts")

    stmt = (
        select(ContributionRecord.distributor_id.label("did"), pts_expr)
        .where(ContributionRecord.occurred_at >= start, ContributionRecord.occurred_at < end)
        .group_by(ContributionRecord.distributor_id)
    )
    if dist_ids is not None:
        stmt = stmt.where(ContributionRecord.distributor_id.in_(dist_ids))
    rows = (await db.execute(stmt.order_by(pts_expr.desc()))).all()

    person_map = await _person_map(db, {did for did, _ in rows})
    org_name_map = await _org_name_map(db, {o for _, o in person_map.values()})
    pts_by_person = {did: float(pts or 0) for did, pts in rows}
    ranked = _assign_ranks([(pts_by_person[did], did) for did, _ in rows])
    items = []
    for rank, did in ranked:
        name, c_org = person_map.get(did, (None, None))
        items.append({
            "rank": rank, "distributorId": str(did), "name": name,
            "orgId": str(c_org) if c_org else None, "orgName": org_name_map.get(c_org),
            "points": pts_by_person[did],
        })
    total = len(items)
    return {"items": items[(page - 1) * page_size: page * page_size], "total": total,
            "page": page, "pageSize": page_size, "hasMore": page * page_size < total}


# ---------------------------------------------------------------------------
# US4: bound-count ranking (person / org)
# ---------------------------------------------------------------------------
async def bindings_ranking(
    db: AsyncSession, scope: str, org_id: Optional[int] = None, page: int = 1, page_size: int = 20
) -> dict:
    dist_ids = await _scope_distributor_ids(db, org_id)

    if scope == "person":
        cnt_expr = func.count(Customer.id).label("cnt")
        stmt = (
            select(Customer.distributor_id.label("did"), cnt_expr)
            .where(Customer.binding_status == BindingStatus.BOUND)
            .group_by(Customer.distributor_id)
        )
        if dist_ids is not None:
            stmt = stmt.where(Customer.distributor_id.in_(dist_ids))
        rows = (await db.execute(stmt.order_by(cnt_expr.desc()))).all()
        person_map = await _person_map(db, {did for did, _ in rows})
        org_name_map = await _org_name_map(db, {o for _, o in person_map.values()})
        cnt_by_person = {did: cnt for did, cnt in rows}
        ranked = _assign_ranks([(cnt_by_person[did], did) for did, _ in rows])
        items = []
        for rank, did in ranked:
            name, c_org = person_map.get(did, (None, None))
            items.append({
                "rank": rank, "distributorId": str(did), "name": name,
                "orgId": str(c_org) if c_org else None, "orgName": org_name_map.get(c_org),
                "boundCount": cnt_by_person[did],
            })
    else:  # org scope: sum bound customers across the org subtree
        org_rows = (await db.execute(
            select(Customer.distributor_id.label("did"), func.count(Customer.id).label("cnt"))
            .where(Customer.binding_status == BindingStatus.BOUND)
            .group_by(Customer.distributor_id)
        )).all()
        did_to_org = await _person_map(db, {did for did, _ in org_rows})
        org_ids_scope = await _subtree_org_ids(db, org_id)
        org_totals: dict[int, int] = {}
        for did, cnt in org_rows:
            c_org = did_to_org.get(did, (None, None))[1]
            if c_org is None:
                continue
            if org_ids_scope is not None and c_org not in org_ids_scope:
                continue
            org_totals[c_org] = org_totals.get(c_org, 0) + cnt
        sorted_orgs = sorted(org_totals.items(), key=lambda x: x[1], reverse=True)
        name_map = await _org_name_map(db, {oid for oid, _ in sorted_orgs})
        cnt_by_org = dict(sorted_orgs)
        ranked = _assign_ranks([(cnt, oid) for oid, cnt in sorted_orgs])
        items = [{"rank": rank, "orgId": str(oid), "orgName": name_map.get(oid), "boundCount": cnt_by_org[oid]}
                 for rank, oid in ranked]

    total = len(items)
    return {"items": items[(page - 1) * page_size: page * page_size], "total": total,
            "page": page, "pageSize": page_size, "hasMore": page * page_size < total}
