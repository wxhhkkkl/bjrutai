"""Capture and freeze the exact inputs behind monthly performance results."""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ConflictException, NotFoundException
from ..models.bill import Bill, TransactionStatus
from ..models.binding import Customer
from ..models.commission_result import CommissionResult
from ..models.distributor import Distributor, OrgRole
from ..models.mall_consumption import MallConsumption
from ..models.organization import Organization
from ..models.performance_evidence import (
    PerformanceEvidence,
    PerformanceEvidenceSource,
    PerformancePeriodVersion,
)
from ..models.performance_rule import (
    PerformanceRule,
    RuleStatus,
    RuleType,
)
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus
from ..models.personal_performance_rule import PersonalPerformanceRule
from .consumption_service import period_start_end
from .performance_period_service import lock_period

ALGORITHM_VERSION = "mall-performance-v1"


def _value(value):
    return value.value if hasattr(value, "value") else value


def _datetime_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="microseconds")


def _timestamp_version(value: datetime | None) -> int:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = value - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _digest(value: dict) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _source_payload(source: dict) -> dict:
    return {
        "sourceType": source["source_type"],
        "sourceId": int(source["source_id"]),
        "sourceVersion": int(source["source_version"]),
        "attributedDistributorId": source["attributed_distributor_id"],
        "calculationOrgId": source["calculation_org_id"],
        "occurredAt": _datetime_text(source["occurred_at"]),
        "businessPeriod": source["business_period"],
        "baseCent": int(source["base_cent"]),
        "snapshot": source["source_snapshot"] or {},
    }


def _evidence_payload(spec: dict) -> dict:
    return {
        "period": spec["period"],
        "distributorId": spec["distributor_id"],
        "ruleType": spec["rule_type"],
        "orgId": spec["org_id"],
        "frozenMembers": spec["frozen_members"],
        "organizationPath": spec["organization_path_snapshot"],
        "ruleSource": spec["rule_source"],
        "ruleSnapshot": spec["rule_snapshot"],
        "algorithmVersion": spec["algorithm_version"],
        "legacyBaseCent": spec["legacy_base_cent"],
        "mallBaseCent": spec["mall_base_cent"],
        "originalBaseCent": spec["original_base_cent"],
        "originalCommissionCent": spec["original_commission_cent"],
        "resultPresence": spec["result_presence"],
        "resultAbsenceReason": spec["result_absence_reason"],
        "resultId": spec["result_id"],
        "evidenceStatus": spec["evidence_status"],
        "sources": sorted(
            (_source_payload(source) for source in spec["sources"]),
            key=lambda source: (source["sourceType"], source["sourceId"]),
        ),
    }


def _freeze_fingerprint(rows: list[tuple[str, str]]) -> str:
    return _digest({"evidence": sorted(rows)})


def _rule_path(org_id: int, parents: dict[int, int | None]) -> list[int]:
    path = []
    current = org_id
    seen = set()
    while current is not None and current not in seen:
        path.append(current)
        seen.add(current)
        current = parents.get(current)
    return path


def _descendant_ids(org_id: int, children: dict[int | None, list[int]]) -> set[int]:
    found = set()
    stack = [org_id]
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(children.get(current, []))
    return found


async def _collect_specs(db: AsyncSession, period: str) -> list[dict]:
    """Build deterministic calculation units from the live facts and rules."""
    from .commission_service import _personal_rule_snapshot, _rule_snapshot

    start, end = period_start_end(period)
    distributors = (await db.execute(select(Distributor).order_by(Distributor.id))).scalars().all()
    distributor_by_id = {row.id: row for row in distributors}
    organizations = (await db.execute(select(Organization.id, Organization.parent_id))).all()
    parents = {int(org_id): parent_id for org_id, parent_id in organizations}
    children: dict[int | None, list[int]] = {}
    for org_id, parent_id in organizations:
        children.setdefault(parent_id, []).append(int(org_id))

    active_rules = (
        (
            await db.execute(
                select(PerformanceRule).where(PerformanceRule.status == RuleStatus.ACTIVE)
            )
        )
        .scalars()
        .all()
    )
    rule_by_scope = {(rule.org_id, rule.rule_type): rule for rule in active_rules}
    personal_rules = (await db.execute(select(PersonalPerformanceRule))).scalars().all()
    personal_by_distributor = {rule.distributor_id: rule for rule in personal_rules}

    sources_by_distributor: dict[int, list[dict]] = {}
    bill_owner = func.coalesce(Bill.attributed_distributor_id, Customer.distributor_id)
    bill_rows = (
        await db.execute(
            select(Bill, Customer.distributor_id)
            .join(Customer, Customer.id == Bill.customer_id)
            .where(
                bill_owner.is_not(None),
                Bill.transaction_time >= start,
                Bill.transaction_time < end,
                Bill.transaction_status.notin_(
                    [TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]
                ),
            )
            .order_by(Bill.transaction_time, Bill.id)
        )
    ).all()
    for bill, customer_distributor_id in bill_rows:
        distributor_id = (
            bill.attributed_distributor_id
            if bill.attributed_distributor_id is not None
            else customer_distributor_id
        )
        distributor = distributor_by_id.get(distributor_id)
        if distributor is None:
            continue
        occurred_at = bill.transaction_time
        status = str(_value(bill.transaction_status))
        source = {
            "source_type": "bill",
            "source_id": bill.id,
            "source_version": _timestamp_version(bill.updated_at),
            "attributed_distributor_id": distributor_id,
            "calculation_org_id": distributor.org_id,
            "occurred_at": occurred_at,
            "business_period": occurred_at.strftime("%Y-%m"),
            "base_cent": int(bill.paid_amount_cent or 0),
            "source_snapshot": {
                "transactionId": bill.transaction_id,
                "status": status,
                "paidAmountCent": int(bill.paid_amount_cent or 0),
                "totalAmountCent": int(bill.total_amount_cent or 0),
                "discountAmountCent": int(bill.discount_amount_cent or 0),
                "refundAmountCent": int(bill.refund_amount_cent or 0),
                "source": bill.source,
                "attributedOrgId": bill.attributed_org_id,
            },
        }
        sources_by_distributor.setdefault(distributor_id, []).append(source)

    mall_rows = (
        (
            await db.execute(
                select(MallConsumption)
                .where(
                    MallConsumption.business_period == period,
                    MallConsumption.status == "assigned",
                    MallConsumption.attributed_distributor_id.is_not(None),
                )
                .order_by(MallConsumption.paid_at, MallConsumption.id)
            )
        )
        .scalars()
        .all()
    )
    for source_row in mall_rows:
        distributor_id = source_row.attributed_distributor_id
        distributor = distributor_by_id.get(distributor_id)
        if distributor is None:
            continue
        source = {
            "source_type": "mall",
            "source_id": source_row.id,
            "source_version": int(source_row.source_version or source_row.version or 1),
            "attributed_distributor_id": distributor_id,
            "calculation_org_id": distributor.org_id,
            "occurred_at": source_row.paid_at,
            "business_period": source_row.business_period,
            "base_cent": int(source_row.performance_base_cent or 0),
            "source_snapshot": {
                "orderId": source_row.order_id,
                "status": source_row.status,
                "originalGoodsCent": int(source_row.original_goods_cent),
                "successfulGoodsRefundCent": int(source_row.successful_goods_refund_cent),
                "performanceBaseCent": int(source_row.performance_base_cent),
                "tradeOrgId": source_row.trade_org_id,
            },
        }
        sources_by_distributor.setdefault(distributor_id, []).append(source)

    results = (
        (
            await db.execute(
                select(CommissionResult).where(
                    CommissionResult.period == period,
                    CommissionResult.origin_kind == "normal",
                )
            )
        )
        .scalars()
        .all()
    )
    result_by_calculation = {(row.distributor_id, row.rule_type): row for row in results}
    intra_rule_orgs = {
        org_id for org_id, rule_type in rule_by_scope if rule_type == RuleType.INTRA_ORG
    }
    intra_ids = set(sources_by_distributor) | set(personal_by_distributor)
    intra_ids.update(row.id for row in distributors if row.org_id in intra_rule_orgs)
    intra_ids.update(
        distributor_id
        for distributor_id, rule_type in result_by_calculation
        if rule_type == RuleType.INTRA_ORG
    )

    specs = []
    for distributor_id in sorted(intra_ids):
        distributor = distributor_by_id.get(distributor_id)
        if distributor is None:
            continue
        personal_rule = personal_by_distributor.get(distributor_id)
        organization_rule = rule_by_scope.get((distributor.org_id, RuleType.INTRA_ORG))
        if personal_rule:
            rule_type = RuleType.INTRA_ORG
            rule_snapshot = _personal_rule_snapshot(personal_rule, organization_rule)
            rule_source = "personal"
            tiers = personal_rule.tiers
        elif organization_rule:
            rule_type = RuleType.INTRA_ORG
            rule_snapshot = _rule_snapshot(organization_rule)
            rule_source = "org"
            tiers = organization_rule.tiers
        else:
            rule_type = RuleType.INTRA_ORG
            rule_snapshot = {}
            rule_source = "missing"
            tiers = None
        scoped_sources = sources_by_distributor.get(distributor_id, [])
        specs.append(
            _make_spec(
                period=period,
                distributor=distributor,
                rule_type=rule_type,
                org_id=distributor.org_id,
                member_ids=[distributor_id],
                org_path=_rule_path(distributor.org_id, parents),
                sources=scoped_sources,
                rule_source=rule_source,
                rule_snapshot=rule_snapshot,
                tiers=tiers,
                result=result_by_calculation.get((distributor_id, rule_type)),
            )
        )

    for admin in sorted(
        (row for row in distributors if row.org_role == OrgRole.ADMIN),
        key=lambda row: row.id,
    ):
        scope = _descendant_ids(admin.org_id, children)
        member_ids = sorted(row.id for row in distributors if row.org_id in scope)
        has_sources = any(sources_by_distributor.get(identity) for identity in member_ids)
        result = result_by_calculation.get((admin.id, RuleType.ORG_MANAGEMENT))
        rule = rule_by_scope.get((admin.org_id, RuleType.ORG_MANAGEMENT))
        if not (rule or has_sources or result):
            continue
        scoped_sources = [
            source for identity in member_ids for source in sources_by_distributor.get(identity, [])
        ]
        specs.append(
            _make_spec(
                period=period,
                distributor=admin,
                rule_type=RuleType.ORG_MANAGEMENT,
                org_id=admin.org_id,
                member_ids=member_ids,
                org_path=_rule_path(admin.org_id, parents),
                sources=scoped_sources,
                rule_source="org" if rule else "missing",
                rule_snapshot=_rule_snapshot(rule) if rule else {},
                tiers=rule.tiers if rule else None,
                result=result,
            )
        )

    # An existing calculation row must always have an evidence anchor, even if
    # current configuration no longer contains the rule that produced it.
    represented = {(spec["distributor_id"], spec["rule_type"]) for spec in specs}
    for row in results:
        key = (row.distributor_id, row.rule_type)
        if key not in represented:
            distributor = distributor_by_id.get(row.distributor_id)
            if distributor is None:
                raise ConflictException(message="历史绩效人员不存在，不能冻结该月份")
            specs.append(
                _make_spec(
                    period=period,
                    distributor=distributor,
                    rule_type=row.rule_type,
                    org_id=row.org_id,
                    member_ids=[row.distributor_id],
                    org_path=_rule_path(row.org_id, parents),
                    sources=sources_by_distributor.get(row.distributor_id, []),
                    rule_source="missing",
                    rule_snapshot={},
                    tiers=None,
                    result=row,
                )
            )
    return sorted(specs, key=lambda row: row["evidence_key"])


def _make_spec(
    *,
    period: str,
    distributor: Distributor,
    rule_type: RuleType,
    org_id: int,
    member_ids: list[int],
    org_path: list[int],
    sources: list[dict],
    rule_source: str,
    rule_snapshot: dict,
    tiers: list | None,
    result: CommissionResult | None,
) -> dict:
    from .commission_service import _apply_tiers

    source_rows = sorted(
        sources,
        key=lambda source: (source["source_type"], source["source_id"]),
    )
    legacy_base = sum(
        source["base_cent"] for source in source_rows if source["source_type"] == "bill"
    )
    mall_base = sum(
        source["base_cent"] for source in source_rows if source["source_type"] == "mall"
    )
    original_base = legacy_base + mall_base
    ratio = _apply_tiers(tiers, original_base) if tiers else 0.0
    if rule_source == "missing":
        if result is not None:
            raise ConflictException(message="绩效规则缺失但存在结果，请人工核实原始规则")
        presence = "not_generated"
        absence_reason = "missing_rule"
        commission_cent = 0
        evidence_status = "manual_required"
    elif ratio > 0:
        if result is None:
            raise ConflictException(message="核算结果缺失，请重新核算后再审核")
        if (
            result.base_cent != original_base
            or result.org_id != org_id
            or int(round(original_base * ratio)) != result.commission_cent
            or abs(float(result.ratio) - ratio) >= 0.000001
        ):
            raise ConflictException(message="绩效结果与当前来源或规则不一致，请重新核算")
        presence = "present"
        absence_reason = None
        commission_cent = result.commission_cent
        evidence_status = "complete"
    else:
        if result is not None:
            raise ConflictException(message="当前规则不应生成该绩效结果，请重新核算")
        matching = next(
            (
                tier
                for tier in sorted(tiers or [], key=lambda item: item["minCent"])
                if original_base >= tier["minCent"]
                and (tier.get("maxCent") is None or original_base < tier["maxCent"])
            ),
            None,
        )
        presence = "not_generated"
        absence_reason = "below_first_tier" if matching is None else "zero_ratio"
        commission_cent = 0
        evidence_status = "complete"

    spec = {
        "period": period,
        "distributor_id": distributor.id,
        "rule_type": rule_type.value,
        "org_id": org_id,
        "frozen_members": member_ids,
        "organization_path_snapshot": org_path,
        "rule_source": rule_source,
        "rule_snapshot": rule_snapshot,
        "algorithm_version": ALGORITHM_VERSION,
        "legacy_base_cent": legacy_base,
        "mall_base_cent": mall_base,
        "original_base_cent": original_base,
        "original_commission_cent": commission_cent,
        "result_presence": presence,
        "result_absence_reason": absence_reason,
        "result_id": result.id if result else None,
        "evidence_status": evidence_status,
        "evidence_key": f"{period}:{distributor.id}:{rule_type.value}",
        "sources": source_rows,
    }
    spec["input_digest"] = _digest(_evidence_payload(spec))
    return spec


async def capture_period_evidence(
    db: AsyncSession, period: str, *, period_row: PerformancePeriodVersion | None = None
) -> dict:
    """Persist a replaceable evidence snapshot for a pending calculation."""
    period_row = period_row or await lock_period(db, period)
    if period_row.status != "open":
        raise ConflictException(message="已冻结期间不能重新捕获绩效证据")
    settlement = (
        await db.execute(
            select(PerformanceSettlement)
            .where(PerformanceSettlement.period == period)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if settlement is None:
        raise NotFoundException(message="核算月份不存在")
    if settlement.status != SettlementStatus.PENDING:
        raise ConflictException(message="只有待审核核算可以捕获绩效证据")

    specs = await _collect_specs(db, period)
    evidence_ids = select(PerformanceEvidence.id).where(
        PerformanceEvidence.settlement_id == settlement.id
    )
    await db.execute(
        delete(PerformanceEvidenceSource).where(
            PerformanceEvidenceSource.evidence_id.in_(evidence_ids)
        )
    )
    await db.execute(
        delete(PerformanceEvidence).where(PerformanceEvidence.settlement_id == settlement.id)
    )
    await db.flush()

    for spec in specs:
        evidence = PerformanceEvidence(
            settlement_id=settlement.id,
            evidence_key=spec["evidence_key"],
            result_id=spec["result_id"],
            period=spec["period"],
            distributor_id=spec["distributor_id"],
            rule_type=spec["rule_type"],
            org_id=spec["org_id"],
            frozen_members=spec["frozen_members"],
            organization_path_snapshot=spec["organization_path_snapshot"],
            rule_source=spec["rule_source"],
            rule_snapshot=spec["rule_snapshot"],
            algorithm_version=spec["algorithm_version"],
            legacy_base_cent=spec["legacy_base_cent"],
            mall_base_cent=spec["mall_base_cent"],
            original_base_cent=spec["original_base_cent"],
            original_commission_cent=spec["original_commission_cent"],
            result_presence=spec["result_presence"],
            result_absence_reason=spec["result_absence_reason"],
            input_digest=spec["input_digest"],
            evidence_status=spec["evidence_status"],
        )
        db.add(evidence)
        await db.flush()
        db.add_all(
            [
                PerformanceEvidenceSource(
                    evidence_id=evidence.id,
                    source_type=source["source_type"],
                    source_id=source["source_id"],
                    source_version=source["source_version"],
                    attributed_distributor_id=source["attributed_distributor_id"],
                    calculation_org_id=source["calculation_org_id"],
                    occurred_at=source["occurred_at"],
                    business_period=source["business_period"],
                    base_cent=source["base_cent"],
                    source_snapshot=source["source_snapshot"],
                )
                for source in spec["sources"]
            ]
        )
        if spec["result_id"]:
            result = await db.get(CommissionResult, spec["result_id"])
            result.evidence_version = ALGORITHM_VERSION
    period_row.recomputed_revision = period_row.revision
    period_row.freeze_fingerprint = None
    await db.flush()
    return {
        "period": period,
        "revision": period_row.revision,
        "evidenceCount": len(specs),
        "fingerprint": _freeze_fingerprint(
            [(spec["evidence_key"], spec["input_digest"]) for spec in specs]
        ),
    }


async def verify_period_evidence(
    db: AsyncSession, period: str, *, period_row: PerformancePeriodVersion
) -> str:
    """Require both the period revision and captured facts to remain identical."""
    if period_row.recomputed_revision != period_row.revision:
        raise ConflictException(message="核算输入已变化，请重新核算后再提交审核")
    current_specs = await _collect_specs(db, period)
    current = {spec["evidence_key"]: spec["input_digest"] for spec in current_specs}
    evidence_rows = (
        (
            await db.execute(
                select(PerformanceEvidence)
                .where(PerformanceEvidence.period == period)
                .order_by(PerformanceEvidence.evidence_key)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    stored = {}
    for evidence in evidence_rows:
        source_rows = (
            (
                await db.execute(
                    select(PerformanceEvidenceSource)
                    .where(PerformanceEvidenceSource.evidence_id == evidence.id)
                    .order_by(
                        PerformanceEvidenceSource.source_type,
                        PerformanceEvidenceSource.source_id,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        spec = {
            "period": evidence.period,
            "distributor_id": evidence.distributor_id,
            "rule_type": evidence.rule_type,
            "org_id": evidence.org_id,
            "frozen_members": evidence.frozen_members,
            "organization_path_snapshot": evidence.organization_path_snapshot,
            "rule_source": evidence.rule_source,
            "rule_snapshot": evidence.rule_snapshot,
            "algorithm_version": evidence.algorithm_version,
            "legacy_base_cent": evidence.legacy_base_cent,
            "mall_base_cent": evidence.mall_base_cent,
            "original_base_cent": evidence.original_base_cent,
            "original_commission_cent": evidence.original_commission_cent,
            "result_presence": evidence.result_presence,
            "result_absence_reason": evidence.result_absence_reason,
            "result_id": evidence.result_id,
            "evidence_status": evidence.evidence_status,
            "sources": [
                {
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "source_version": row.source_version,
                    "attributed_distributor_id": row.attributed_distributor_id,
                    "calculation_org_id": row.calculation_org_id,
                    "occurred_at": row.occurred_at,
                    "business_period": row.business_period,
                    "base_cent": row.base_cent,
                    "source_snapshot": row.source_snapshot,
                }
                for row in source_rows
            ],
        }
        if _digest(_evidence_payload(spec)) != evidence.input_digest:
            raise ConflictException(message="冻结证据内容已变化，需人工核实")
        stored[evidence.evidence_key] = evidence.input_digest

    if current != stored:
        raise ConflictException(message="核算来源、规则或范围已变化，请重新核算后再提交审核")
    return _freeze_fingerprint(list(stored.items()))


async def freeze_period_evidence(
    db: AsyncSession,
    period: str,
    *,
    period_row: PerformancePeriodVersion,
    fingerprint: str,
    frozen_at: datetime,
) -> None:
    rows = (
        (
            await db.execute(
                select(PerformanceEvidence)
                .where(PerformanceEvidence.period == period)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    for evidence in rows:
        evidence.frozen_at = frozen_at
        if evidence.result_id is not None:
            result = await db.get(CommissionResult, evidence.result_id)
            if result is not None:
                result.evidence_version = evidence.algorithm_version
    period_row.status = "frozen"
    period_row.freeze_fingerprint = fingerprint
    await db.flush()
