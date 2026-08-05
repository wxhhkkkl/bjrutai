"""Commission calculation engine (FR-011 / FR-013).

- Non-admin members: base = their own consumption (sum of ``Bill.paid_amount_cent``
  for bills of their bound customers in the period), apply the org's intra_org
  tiered ladder.
- Org admins: base = total consumption of ALL people in the managed org subtree,
  apply the org_management tiered ladder (result assigned to the admin).

Monthly settlement persists results into ``commission_results`` (idempotent
upsert); a preview variant computes for one org without persisting.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.bill import Bill, TransactionStatus
from ..models.binding import Customer
from ..models.commission_result import CommissionResult
from ..models.distributor import Distributor, OrgRole
from ..models.performance_rule import PerformanceRule, RuleStatus, RuleType
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus
from . import distributor_service, organization_service


def _period_start_end(period: str) -> tuple[datetime, datetime]:
    year, month = (int(x) for x in period.split("-"))
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def _apply_tiers(tiers: list, base_cent: int) -> float:
    """Return the ratio matched by ``base_cent`` (tiers sorted ascending,
    intervals include lower bound, exclude upper bound)."""
    for t in sorted(tiers, key=lambda x: x["minCent"]):
        if base_cent < t["minCent"]:
            continue
        if t["maxCent"] is None or base_cent < t["maxCent"]:
            return float(t["ratio"])
    return 0.0


async def _consumption_by_distributor(db: AsyncSession, distributor_ids: list, period: str) -> dict[int, int]:
    """Return {distributor_id: total paid consumption (cents)} in the period,
    excluding refunded/cancelled bills."""
    if not distributor_ids:
        return {}
    start, end = _period_start_end(period)
    result = await db.execute(
        select(Customer.distributor_id, func.coalesce(func.sum(Bill.paid_amount_cent), 0))
        .join(Bill, Bill.customer_id == Customer.id)
        .where(
            Customer.distributor_id.in_(distributor_ids),
            Bill.transaction_time >= start,
            Bill.transaction_time < end,
            Bill.transaction_status.notin_([TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]),
        )
        .group_by(Customer.distributor_id)
    )
    return {int(did): int(amount) for did, amount in result.all()}


async def _org_subtree_ids(db: AsyncSession, org_id: int) -> set[int]:
    subtree = await organization_service.get_subtree(db, org_id)
    return distributor_service._collect_org_ids(subtree)


def _ratio_str(ratio: float) -> str:
    return f"{ratio:.6f}"


def _rule_snapshot(rule: PerformanceRule) -> dict:
    """Snapshot of the active rule used at computation time (FR-007)."""
    return {
        "ruleType": rule.rule_type.value if hasattr(rule.rule_type, "value") else str(rule.rule_type),
        "tiers": rule.tiers,
        "version": rule.version,
    }


async def _ensure_pending_settlement(db: AsyncSession, period: str) -> None:
    """Create the period batch as pending, or flip a rejected batch back to pending."""
    settlement = (
        await db.execute(
            select(PerformanceSettlement).where(PerformanceSettlement.period == period)
        )
    ).scalars().first()
    if settlement is None:
        db.add(PerformanceSettlement(period=period, status=SettlementStatus.PENDING))
    elif settlement.status == SettlementStatus.REJECTED:
        settlement.status = SettlementStatus.PENDING
        settlement.reject_reason = None
        db.add(settlement)


async def _upsert_result(
    db: AsyncSession,
    period: str,
    distributor_id: int,
    org_id: int,
    rule_type: RuleType,
    base_cent: int,
    ratio: float,
    commission_cent: int,
    rule_snapshot: dict | None = None,
) -> None:
    existing = (
        await db.execute(
            select(CommissionResult).where(
                CommissionResult.period == period,
                CommissionResult.distributor_id == distributor_id,
                CommissionResult.rule_type == rule_type,
            )
        )
    ).scalars().first()
    if existing is None:
        db.add(CommissionResult(
            period=period, distributor_id=distributor_id, org_id=org_id,
            rule_type=rule_type, base_cent=base_cent,
            ratio=_ratio_str(ratio), commission_cent=commission_cent,
            rule_snapshot=rule_snapshot,
            computed_at=datetime.now(timezone.utc),
        ))
    else:
        existing.org_id = org_id
        existing.base_cent = base_cent
        existing.ratio = _ratio_str(ratio)
        existing.commission_cent = commission_cent
        if rule_snapshot is not None:
            existing.rule_snapshot = rule_snapshot
        existing.computed_at = datetime.now(timezone.utc)
        db.add(existing)


async def _load_org_people(db: AsyncSession) -> tuple[dict, dict, list]:
    """Return {org_id: all distributors}, {org_id: admins}, and the full list."""
    dist_result = await db.execute(select(Distributor))
    distributors = dist_result.scalars().all()
    org_people: dict[int, list[Distributor]] = {}
    org_admins: dict[int, list[Distributor]] = {}
    for d in distributors:
        org_people.setdefault(d.org_id, []).append(d)
        if d.org_role == OrgRole.ADMIN:
            org_admins.setdefault(d.org_id, []).append(d)
    return org_people, org_admins, distributors


# ---------------------------------------------------------------------------
# Monthly settlement: compute for all orgs and persist
# ---------------------------------------------------------------------------
async def compute_commission(db: AsyncSession, period: str) -> dict:
    """Compute commissions for all orgs with active rules and upsert results.

    Freeze (FR-006): a period whose settlement is ``reviewed`` is skipped entirely.
    Snapshot (FR-007): each result row stores the rule tiers/version used.
    A pending batch is created/kept for the period (FR-003).
    """
    settlement = (
        await db.execute(
            select(PerformanceSettlement).where(PerformanceSettlement.period == period)
        )
    ).scalars().first()
    if settlement is not None and settlement.status == SettlementStatus.REVIEWED:
        return {"period": period, "computed": 0, "frozen": True}

    rules_result = await db.execute(
        select(PerformanceRule).where(PerformanceRule.status == RuleStatus.ACTIVE)
    )
    rules = rules_result.scalars().all()
    if not rules:
        await _ensure_pending_settlement(db, period)
        await db.flush()
        return {"period": period, "computed": 0, "frozen": False}

    org_people, org_admins, distributors = await _load_org_people(db)
    consumption = await _consumption_by_distributor(db, [d.id for d in distributors], period)

    computed = 0
    for rule in rules:
        if rule.rule_type == RuleType.INTRA_ORG:
            # 组织内绩效提成覆盖本组织所有人员（含组织管理员）——管理员同时
            # 计算组织内提成（自身消费）与组织管理提成（子树总额）。
            for d in org_people.get(rule.org_id, []):
                base = consumption.get(d.id, 0)
                ratio = _apply_tiers(rule.tiers, base)
                if ratio <= 0:
                    continue
                await _upsert_result(
                    db, period, d.id, rule.org_id, RuleType.INTRA_ORG, base, ratio,
                    int(round(base * ratio)), rule_snapshot=_rule_snapshot(rule),
                )
                computed += 1
        elif rule.rule_type == RuleType.ORG_MANAGEMENT:
            subtree_ids = await _org_subtree_ids(db, rule.org_id)
            subtree_dists = [d.id for d in distributors if d.org_id in subtree_ids]
            base = sum(consumption.get(did, 0) for did in subtree_dists)
            for admin in org_admins.get(rule.org_id, []):
                ratio = _apply_tiers(rule.tiers, base)
                if ratio <= 0:
                    continue
                await _upsert_result(
                    db, period, admin.id, rule.org_id, RuleType.ORG_MANAGEMENT, base, ratio,
                    int(round(base * ratio)), rule_snapshot=_rule_snapshot(rule),
                )
                computed += 1
    await _ensure_pending_settlement(db, period)
    await db.flush()
    return {"period": period, "computed": computed, "frozen": False}


# ---------------------------------------------------------------------------
# Real-time preview (FR-013) — computes for one org without persisting
# ---------------------------------------------------------------------------
async def preview_org_commission(db: AsyncSession, org_id: int, period: str) -> dict:
    rules_result = await db.execute(
        select(PerformanceRule).where(
            PerformanceRule.org_id == org_id,
            PerformanceRule.status == RuleStatus.ACTIVE,
        )
    )
    rules = {r.rule_type.value: r for r in rules_result.scalars().all()}

    org_people, org_admins, distributors = await _load_org_people(db)
    consumption = await _consumption_by_distributor(db, [d.id for d in distributors], period)

    intra_items, mgmt_items, unconfigured = [], [], []

    intra_rule = rules.get(RuleType.INTRA_ORG.value)
    if intra_rule:
        for d in org_people.get(org_id, []):
            base = consumption.get(d.id, 0)
            ratio = _apply_tiers(intra_rule.tiers, base)
            if ratio <= 0:
                continue
            intra_items.append(_preview_item(d.id, await _distributor_name(db, d.id), base, ratio))
    else:
        unconfigured.append(RuleType.INTRA_ORG.value)

    mgmt_rule = rules.get(RuleType.ORG_MANAGEMENT.value)
    if mgmt_rule:
        subtree_ids = await _org_subtree_ids(db, org_id)
        subtree_dists = [d.id for d in distributors if d.org_id in subtree_ids]
        base = sum(consumption.get(did, 0) for did in subtree_dists)
        for admin in org_admins.get(org_id, []):
            ratio = _apply_tiers(mgmt_rule.tiers, base)
            if ratio <= 0:
                continue
            mgmt_items.append(_preview_item(admin.id, await _distributor_name(db, admin.id), base, ratio))
    else:
        unconfigured.append(RuleType.ORG_MANAGEMENT.value)

    return {
        "orgId": str(org_id),
        "period": period,
        "intraOrg": intra_items,
        "orgManagement": mgmt_items,
        "unconfigured": unconfigured,
    }


def _preview_item(distributor_id: int, name, base_cent: int, ratio: float) -> dict:
    return {
        "distributorId": str(distributor_id),
        "name": name,
        "baseCent": base_cent,
        "ratio": float(ratio),
        "commissionCent": int(round(base_cent * ratio)),
    }


# ---------------------------------------------------------------------------
# Query monthly results (FR-013 / SC-009)
# ---------------------------------------------------------------------------
async def list_results(
    db: AsyncSession,
    period: str,
    org_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    filters = [CommissionResult.period == period]
    if org_id is not None:
        subtree_ids = await _org_subtree_ids(db, org_id)
        filters.append(CommissionResult.org_id.in_(subtree_ids))

    count_stmt = select(func.count(CommissionResult.id)).where(*filters)
    total = (await db.execute(count_stmt)).scalar() or 0

    rows = (
        await db.execute(
            select(CommissionResult)
            .where(*filters)
            .order_by(CommissionResult.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()

    items = []
    for r in rows:
        name = await _distributor_name(db, r.distributor_id)
        items.append({
            "period": r.period,
            "distributorId": str(r.distributor_id),
            "name": name,
            "orgId": str(r.org_id),
            "ruleType": r.rule_type.value if hasattr(r.rule_type, "value") else str(r.rule_type),
            "baseCent": r.base_cent,
            "ratio": float(r.ratio),
            "commissionCent": r.commission_cent,
            "computedAt": r.computed_at.isoformat() if r.computed_at else None,
        })

    return {"items": items, "total": total, "page": page, "pageSize": page_size, "hasMore": page * page_size < total}


async def _distributor_name(db: AsyncSession, distributor_id: int) -> Optional[str]:
    from ..models.user import User

    result = await db.execute(
        select(User.name).join(Distributor, Distributor.user_id == User.id)
        .where(Distributor.id == distributor_id)
    )
    return result.scalars().first()


async def _org_names(db: AsyncSession, org_ids: set[int]) -> dict[int, str]:
    if not org_ids:
        return {}
    from ..models.organization import Organization

    rows = (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars().all()
    return {o.id: o.name for o in rows}


# ---------------------------------------------------------------------------
# Export monthly results (FR-010 / SC-007)
# ---------------------------------------------------------------------------
async def export_results_csv(
    db: AsyncSession,
    period: str,
    org_id: Optional[int] = None,
) -> str:
    """Return CSV text of a period's commission results (optionally org-subtree scoped)."""
    import csv
    import io

    filters = [CommissionResult.period == period]
    if org_id is not None:
        subtree_ids = await _org_subtree_ids(db, org_id)
        filters.append(CommissionResult.org_id.in_(subtree_ids))

    rows = (
        await db.execute(
            select(CommissionResult).where(*filters).order_by(CommissionResult.org_id, CommissionResult.id)
        )
    ).scalars().all()

    org_ids = {r.org_id for r in rows}
    names = await _org_names(db, org_ids)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "period", "orgId", "orgName", "distributorId", "name",
        "ruleType", "baseCent", "ratio", "commissionCent", "computedAt",
    ])
    for r in rows:
        writer.writerow([
            r.period,
            r.org_id,
            names.get(r.org_id, ""),
            r.distributor_id,
            await _distributor_name(db, r.distributor_id) or "",
            r.rule_type.value if hasattr(r.rule_type, "value") else str(r.rule_type),
            r.base_cent,
            r.ratio,
            r.commission_cent,
            r.computed_at.isoformat() if r.computed_at else "",
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Real-time estimate for one distributor (mini-program, FR-009 / SC-008)
# ---------------------------------------------------------------------------
async def estimate_distributor(db: AsyncSession, distributor_id: int, period: str) -> Optional[dict]:
    """Real-time intra_org estimate for one distributor. Returns None when no
    rule applies or commission is 0 (aligned with preview_org_commission)."""
    dist = (
        await db.execute(select(Distributor).where(Distributor.id == distributor_id))
    ).scalars().first()
    if dist is None:
        return None

    rule = (
        await db.execute(
            select(PerformanceRule).where(
                PerformanceRule.org_id == dist.org_id,
                PerformanceRule.rule_type == RuleType.INTRA_ORG,
                PerformanceRule.status == RuleStatus.ACTIVE,
            )
        )
    ).scalars().first()

    consumption = await _consumption_by_distributor(db, [dist.id], period)
    base = consumption.get(dist.id, 0)
    ratio = _apply_tiers(rule.tiers, base) if rule else 0.0
    if ratio <= 0:
        return None
    return {
        "distributorId": str(dist.id),
        "name": await _distributor_name(db, dist.id),
        "baseCent": base,
        "ratio": ratio,
        "commissionCent": int(round(base * ratio)),
    }


async def estimate_org_admin(db: AsyncSession, distributor_id: int, period: str) -> Optional[dict]:
    """Real-time org_management estimate for one org-admin. None when not admin
    or no commission."""
    dist = (
        await db.execute(select(Distributor).where(Distributor.id == distributor_id))
    ).scalars().first()
    if dist is None or dist.org_role != OrgRole.ADMIN:
        return None

    rule = (
        await db.execute(
            select(PerformanceRule).where(
                PerformanceRule.org_id == dist.org_id,
                PerformanceRule.rule_type == RuleType.ORG_MANAGEMENT,
                PerformanceRule.status == RuleStatus.ACTIVE,
            )
        )
    ).scalars().first()
    if rule is None:
        return None

    subtree_ids = await _org_subtree_ids(db, dist.org_id)
    rows = (
        await db.execute(select(Distributor).where(Distributor.org_id.in_(subtree_ids)))
    ).scalars().all()
    consumption = await _consumption_by_distributor(db, [d.id for d in rows], period)
    base = sum(consumption.get(d.id, 0) for d in rows)
    ratio = _apply_tiers(rule.tiers, base)
    if ratio <= 0:
        return None
    return {
        "baseCent": base,
        "ratio": ratio,
        "commissionCent": int(round(base * ratio)),
    }
