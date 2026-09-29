"""Performance rule configuration service (FR-003~FR-007).

Per-org commission rules with tier validation, versioned updates and change
history. The calculation engine lives in commission_service.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, NotFoundException
from ..models.distributor import Distributor
from ..models.organization import Organization
from ..models.performance_rule import (
    ChangeOperation,
    PerformanceRule,
    PerformanceRuleChangeLog,
    RuleStatus,
    RuleType,
)
from ..models.personal_performance_rule import PersonalPerformanceRule
from ..schemas.performance_rule import PersonalPerformanceRuleUpdateRequest
from . import distributor_service, organization_service


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_tiers(tiers: list) -> None:
    """Validate a tier ladder (FR-006): contiguous (no gaps/overlaps so any
    amount is covered), first tier minCent == 0, last tier maxCent == null."""
    if not tiers:
        raise BadRequestException(message="阶梯至少一项")

    prev_max: Optional[int] = None
    for i, t in enumerate(tiers):
        if t.minCent < 0:
            raise BadRequestException(message="阶梯下限不能为负")
        if t.ratio <= 0 or t.ratio > 1:
            raise BadRequestException(message="比率必须大于 0 且不超过 100%")
        if t.maxCent is not None and t.maxCent <= t.minCent:
            raise BadRequestException(message="阶梯上限必须大于下限")
        if i == 0 and t.minCent != 0:
            raise BadRequestException(message="首项阶梯下限必须为 0")
        if prev_max is not None and t.minCent != prev_max:
            raise BadRequestException(message="阶梯区间需连续覆盖任意金额，不得有空隙或重叠")
        prev_max = t.maxCent if t.maxCent is not None else float("inf")

    if tiers[-1].maxCent is not None:
        raise BadRequestException(message="末项阶梯上限必须为空（上不封顶）")


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def _rule_to_dict(rule: PerformanceRule) -> dict:
    return {
        "ruleId": str(rule.id),
        "ruleType": rule.rule_type.value if hasattr(rule.rule_type, "value") else str(rule.rule_type),
        "tiers": rule.tiers,
        "status": rule.status.value if hasattr(rule.status, "value") else str(rule.status),
        "version": rule.version,
        "updatedAt": rule.updated_at.isoformat() if rule.updated_at else None,
    }


async def _get_org_or_404(db: AsyncSession, org_id: int) -> Organization:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalars().first()
    if org is None:
        raise NotFoundException(message="组织不存在")
    return org


# ---------------------------------------------------------------------------
# US1: get both rules for an org
# ---------------------------------------------------------------------------
async def get_rules_for_org(db: AsyncSession, org_id: int) -> dict:
    await _get_org_or_404(db, org_id)
    result = await db.execute(
        select(PerformanceRule).where(
            PerformanceRule.org_id == org_id,
            PerformanceRule.status == RuleStatus.ACTIVE,
        )
    )
    rules = {r.rule_type.value: r for r in result.scalars().all()}
    intra = rules.get(RuleType.INTRA_ORG.value)
    mgmt = rules.get(RuleType.ORG_MANAGEMENT.value)
    return {
        "orgId": str(org_id),
        "intraOrg": _rule_to_dict(intra) if intra else None,
        "orgManagement": _rule_to_dict(mgmt) if mgmt else None,
        "summary": {
            "intraOrgConfigured": intra is not None,
            "orgManagementConfigured": mgmt is not None,
        },
    }


# ---------------------------------------------------------------------------
# US2/US3: save a rule (upsert) with version + change history
# ---------------------------------------------------------------------------
async def save_rule(
    db: AsyncSession,
    org_id: int,
    rule_type_str: str,
    data,
    operator_id: int,
) -> dict:
    await _get_org_or_404(db, org_id)
    try:
        rule_type = RuleType(rule_type_str)
    except ValueError:
        raise BadRequestException(message="无效的提成方式类型")

    validate_tiers(data.tiers)
    tiers = [t.model_dump() for t in data.tiers]
    await _upsert_rule(db, org_id, rule_type, tiers, operator_id)
    result = await db.execute(
        select(PerformanceRule).where(
            PerformanceRule.org_id == org_id,
            PerformanceRule.rule_type == rule_type,
        )
    )
    return _rule_to_dict(result.scalars().first())


async def _upsert_rule(
    db: AsyncSession, org_id: int, rule_type: RuleType, tiers: list, operator_id: int,
    operation: Optional[ChangeOperation] = None,
) -> None:
    """Create or overwrite an org's rule of a type, bumping version + change log.

    ``operation`` defaults to create/update based on whether the rule exists;
    pass ``ChangeOperation.APPLY`` when copying to descendants.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PerformanceRule).where(
            PerformanceRule.org_id == org_id,
            PerformanceRule.rule_type == rule_type,
        )
    )
    rule = result.scalars().first()
    if rule is None:
        rule = PerformanceRule(
            org_id=org_id, rule_type=rule_type, tiers=tiers,
            status=RuleStatus.ACTIVE, version=1, created_by=operator_id,
            created_at=now, updated_at=now,
        )
        db.add(rule)
        await db.flush()
        await db.refresh(rule)
        db.add(PerformanceRuleChangeLog(
            rule_id=rule.id, operation_type=operation or ChangeOperation.CREATE,
            changed_by=operator_id, old_value=None,
            new_value={"tiers": tiers}, created_at=now,
        ))
    else:
        old_value = {"tiers": rule.tiers}
        rule.tiers = tiers
        rule.version += 1
        rule.updated_at = now
        db.add(rule)
        await db.flush()
        db.add(PerformanceRuleChangeLog(
            rule_id=rule.id, operation_type=operation or ChangeOperation.UPDATE,
            changed_by=operator_id, old_value=old_value,
            new_value={"tiers": tiers}, created_at=now,
        ))
    await db.flush()


# ---------------------------------------------------------------------------
# 一键应用到全部下级组织
# ---------------------------------------------------------------------------
async def apply_rule_to_descendants(
    db: AsyncSession, org_id: int, rule_type_str: str, operator_id: int
) -> dict:
    """Copy the org's current rule of *rule_type* to every descendant org."""
    await _get_org_or_404(db, org_id)
    try:
        rule_type = RuleType(rule_type_str)
    except ValueError:
        raise BadRequestException(message="无效的提成方式类型")

    result = await db.execute(
        select(PerformanceRule).where(
            PerformanceRule.org_id == org_id,
            PerformanceRule.rule_type == rule_type,
            PerformanceRule.status == RuleStatus.ACTIVE,
        )
    )
    source = result.scalars().first()
    if source is None:
        raise BadRequestException(message="当前组织未配置该绩效提成方式，无法应用到下级组织")

    subtree = await organization_service.get_subtree(db, org_id)
    desc_ids = distributor_service._collect_org_ids(subtree) - {org_id}
    for did in desc_ids:
        await _upsert_rule(db, did, rule_type, source.tiers, operator_id, operation=ChangeOperation.APPLY)

    return {"applied": len(desc_ids), "orgIds": sorted(str(x) for x in desc_ids)}


# ---------------------------------------------------------------------------
# Personal intra-org overrides
# ---------------------------------------------------------------------------
def _personal_rule_to_dict(rule: PersonalPerformanceRule) -> dict:
    return {
        "ruleId": str(rule.id),
        "tiers": rule.tiers,
        "version": rule.version,
        "updatedAt": rule.updated_at.isoformat() if rule.updated_at else None,
    }


async def get_personal_rules_for_org(db: AsyncSession, org_id: int) -> dict:
    """List configured personal intra-org overrides for one organization."""
    await _get_org_or_404(db, org_id)
    result = await db.execute(
        select(PersonalPerformanceRule, Distributor.id)
        .join(Distributor, Distributor.id == PersonalPerformanceRule.distributor_id)
        .where(Distributor.org_id == org_id)
        .order_by(Distributor.id)
    )
    return {
        "items": [
            {
                "distributorId": str(distributor_id),
                **_personal_rule_to_dict(rule),
            }
            for rule, distributor_id in result.all()
        ]
    }


async def get_personal_rule(db: AsyncSession, distributor_id: int) -> dict:
    """Return personal override and org-level fallback tiers for the editor."""
    distributor = await distributor_service.get_distributor_or_404(db, distributor_id)
    personal = (
        await db.execute(
            select(PersonalPerformanceRule).where(
                PersonalPerformanceRule.distributor_id == distributor.id
            )
        )
    ).scalars().first()
    org_rule = (
        await db.execute(
            select(PerformanceRule).where(
                PerformanceRule.org_id == distributor.org_id,
                PerformanceRule.rule_type == RuleType.INTRA_ORG,
                PerformanceRule.status == RuleStatus.ACTIVE,
            )
        )
    ).scalars().first()
    return {
        "distributorId": str(distributor.id),
        "orgId": str(distributor.org_id),
        "personalRule": _personal_rule_to_dict(personal) if personal else None,
        "organizationRule": _rule_to_dict(org_rule) if org_rule else None,
    }


async def save_personal_rule(
    db: AsyncSession,
    distributor_id: int,
    data: PersonalPerformanceRuleUpdateRequest,
    operator_id: Optional[int],
) -> dict:
    """Create or update a personal tier ladder that overrides the org rule."""
    distributor = await distributor_service.get_distributor_or_404(db, distributor_id)
    validate_tiers(data.tiers)
    tiers = [tier.model_dump() for tier in data.tiers]
    result = await db.execute(
        select(PersonalPerformanceRule).where(
            PersonalPerformanceRule.distributor_id == distributor.id
        )
    )
    rule = result.scalars().first()
    now = datetime.now(timezone.utc)
    if rule is None:
        rule = PersonalPerformanceRule(
            distributor_id=distributor.id,
            tiers=tiers,
            version=1,
            created_by=operator_id,
            updated_by=operator_id,
            created_at=now,
            updated_at=now,
        )
        db.add(rule)
    else:
        rule.tiers = tiers
        rule.version += 1
        rule.updated_by = operator_id
        rule.updated_at = now
        db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return _personal_rule_to_dict(rule)


async def clear_personal_rule(db: AsyncSession, distributor_id: int) -> dict:
    """Remove the personal override so the distributor inherits org tiers."""
    await distributor_service.get_distributor_or_404(db, distributor_id)
    result = await db.execute(
        select(PersonalPerformanceRule).where(
            PersonalPerformanceRule.distributor_id == distributor_id
        )
    )
    rule = result.scalars().first()
    if rule is not None:
        await db.delete(rule)
        await db.flush()
    return {"distributorId": str(distributor_id), "inherited": True}


# ---------------------------------------------------------------------------
# FR-007: change history
# ---------------------------------------------------------------------------
async def get_history(db: AsyncSession, org_id: int) -> dict:
    await _get_org_or_404(db, org_id)
    result = await db.execute(
        select(PerformanceRule.id, PerformanceRule.rule_type)
        .where(PerformanceRule.org_id == org_id)
    )
    rule_map = {rid: (rt.value if hasattr(rt, "value") else str(rt)) for rid, rt in result.all()}
    if not rule_map:
        return {"items": []}

    logs_result = await db.execute(
        select(PerformanceRuleChangeLog)
        .where(PerformanceRuleChangeLog.rule_id.in_(list(rule_map.keys())))
        .order_by(PerformanceRuleChangeLog.created_at.desc())
    )
    from ..models.user import AdminAccount

    items = []
    for log in logs_result.scalars().all():
        acc = await db.get(AdminAccount, log.changed_by)
        items.append({
            "ruleId": str(log.rule_id),
            "ruleType": rule_map.get(log.rule_id),
            "operationType": log.operation_type.value if hasattr(log.operation_type, "value") else str(log.operation_type),
            "changedBy": acc.username if acc else str(log.changed_by),
            "oldValue": log.old_value,
            "newValue": log.new_value,
            "createdAt": log.created_at.isoformat() if log.created_at else None,
        })
    return {"items": items}
