"""Frozen performance evidence contracts for the mall consumption source."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commission_result import CommissionResult
from src.models.performance_evidence import PerformanceEvidence, PerformanceEvidenceSource
from src.models.performance_rule import RuleType
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.services import settlement_service
from tests.mall_consumption_fixtures import (
    add_bill,
    add_mall_source,
    add_performance_rule,
    performance_context,
)


@pytest.mark.asyncio
async def test_review_returns_409_when_source_changes_after_evidence_capture(
    db_session: AsyncSession,
):
    from src.services.performance_evidence_service import capture_period_evidence

    context = await performance_context(db_session)
    bill = await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    await add_performance_rule(db_session, context)
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING))
    await db_session.flush()
    from src.services.commission_service import compute_commission

    await compute_commission(db_session, "2026-07")

    await capture_period_evidence(db_session, "2026-07")
    bill.total_amount_cent += 100
    bill.paid_amount_cent += 100
    await db_session.flush()

    from src.core.exceptions import ConflictException

    with pytest.raises(ConflictException) as error:
        await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)

    assert error.value.status_code == 409
    settlement = await db_session.scalar(
        select(PerformanceSettlement).where(PerformanceSettlement.period == "2026-07")
    )
    assert settlement.status == SettlementStatus.PENDING


@pytest.mark.asyncio
async def test_frozen_scope_and_rule_stay_original_after_org_and_rule_change(
    db_session: AsyncSession,
):
    from src.models.distributor import Distributor
    from src.models.organization import Organization
    from src.services.performance_evidence_service import capture_period_evidence

    context = await performance_context(db_session)
    bill = await add_bill(db_session, context, 1100000, datetime(2026, 7, 10))
    bill.attributed_distributor_id = context["distributorId"]
    bill.attributed_org_id = context["orgId"]
    tiers = [{"minCent": 0, "maxCent": None, "ratio": 0.08}]
    rule = await add_performance_rule(db_session, context, tiers=tiers, version=7)
    result = CommissionResult(
        period="2026-07",
        distributor_id=context["distributorId"],
        org_id=context["orgId"],
        rule_type=RuleType.INTRA_ORG,
        base_cent=1100000,
        ratio="0.08",
        commission_cent=88000,
        rule_snapshot={"tiers": tiers, "version": 7},
    )
    db_session.add_all(
        [result, PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING)]
    )
    await db_session.flush()

    await capture_period_evidence(db_session, "2026-07")
    await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)
    evidence = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == "2026-07",
            PerformanceEvidence.distributor_id == context["distributorId"],
            PerformanceEvidence.rule_type == RuleType.INTRA_ORG.value,
        )
    )
    assert evidence is not None
    original_evidence_id = evidence.id
    original_result_id = evidence.result_id
    original_org_id = evidence.org_id
    original_members = list(evidence.frozen_members)
    original_org_path = list(evidence.organization_path_snapshot)
    original_rule = dict(evidence.rule_snapshot)
    original_source = await db_session.scalar(
        select(PerformanceEvidenceSource).where(
            PerformanceEvidenceSource.evidence_id == evidence.id,
            PerformanceEvidenceSource.source_type == "bill",
            PerformanceEvidenceSource.source_id == bill.id,
        )
    )
    assert original_source is not None

    new_org = Organization(name="新组织", level=1)
    db_session.add(new_org)
    await db_session.flush()
    distributor = await db_session.get(Distributor, context["distributorId"])
    distributor.org_id = new_org.id
    rule.tiers = [{"minCent": 0, "maxCent": None, "ratio": 0.99}]
    rule.version += 1
    await db_session.flush()

    await db_session.refresh(evidence)
    assert evidence.id == original_evidence_id
    assert evidence.result_id == original_result_id
    assert evidence.org_id == original_org_id == context["orgId"]
    assert evidence.frozen_members == original_members
    assert evidence.organization_path_snapshot == original_org_path
    assert evidence.rule_snapshot == original_rule
    assert evidence.rule_snapshot["version"] == 7


@pytest.mark.asyncio
async def test_below_first_tier_keeps_zero_value_anchor_without_inserting_result(
    db_session: AsyncSession,
):
    from src.services.performance_evidence_service import capture_period_evidence

    context = await performance_context(db_session)
    await add_bill(db_session, context, 8000, datetime(2026, 7, 10))
    tiers = [{"minCent": 10000, "maxCent": None, "ratio": 0.08}]
    await add_performance_rule(db_session, context, tiers=tiers, version=4)
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING))
    await db_session.flush()

    await capture_period_evidence(db_session, "2026-07")
    evidence = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == "2026-07",
            PerformanceEvidence.distributor_id == context["distributorId"],
            PerformanceEvidence.rule_type == RuleType.INTRA_ORG.value,
        )
    )
    assert evidence is not None
    assert evidence.result_presence == "not_generated"
    assert evidence.result_id is None
    assert evidence.original_base_cent == 8000
    assert evidence.original_commission_cent == 0
    assert evidence.result_absence_reason == "below_first_tier"
    assert (
        await db_session.scalar(
            select(CommissionResult.id).where(
                CommissionResult.period == "2026-07",
                CommissionResult.distributor_id == context["distributorId"],
                CommissionResult.rule_type == RuleType.INTRA_ORG,
            )
        )
        is None
    )
    await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)
    await db_session.refresh(evidence)
    assert evidence.frozen_at is not None


@pytest.mark.asyncio
async def test_missing_original_rule_stays_manual_after_later_rule_is_added(
    db_session: AsyncSession,
):
    from src.services.performance_evidence_service import capture_period_evidence

    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15), attributed=False)
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING))
    await db_session.flush()

    await capture_period_evidence(db_session, "2026-07")
    evidence = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == "2026-07",
            PerformanceEvidence.distributor_id == context["distributorId"],
            PerformanceEvidence.rule_type == RuleType.INTRA_ORG.value,
        )
    )
    assert evidence is not None
    assert evidence.evidence_status == "manual_required"
    assert evidence.rule_source == "missing"
    assert evidence.result_presence == "not_generated"
    assert evidence.original_commission_cent == 0

    await add_performance_rule(
        db_session,
        context,
        tiers=[{"minCent": 0, "maxCent": None, "ratio": 0.99}],
        version=99,
    )
    await db_session.flush()
    await db_session.refresh(evidence)
    assert evidence.evidence_status == "manual_required"
    assert evidence.rule_snapshot == {}
    assert evidence.original_commission_cent == 0


@pytest.mark.asyncio
async def test_management_evidence_captures_descendant_sources_and_frozen_scope(db_session):
    from src.models.binding import BindingStatus, Customer
    from src.models.distributor import Distributor, OrgRole
    from src.schemas.organization import OrgCreate
    from src.services import organization_service
    from src.services.commission_service import compute_commission
    from src.services.performance_evidence_service import capture_period_evidence
    from tests.conftest import seed_promoter, seed_user

    context = await performance_context(db_session)
    parent_distributor = await db_session.get(Distributor, context["distributorId"])
    parent_distributor.org_role = OrgRole.ADMIN
    child_org = await organization_service.create_org(
        db_session,
        OrgCreate(name="绩效冻结下级", orgType="promoter", parentId=context["orgId"]),
    )
    member_user_id = await seed_user(
        db_session, openid="performance-evidence-child", user_type="promoter", name="下级成员"
    )
    member_distributor_id = await seed_promoter(
        db_session, user_id=member_user_id, node_id=child_org.id
    )
    buyer_user_id = await seed_user(
        db_session, openid="performance-evidence-child-buyer", user_type="personal", name="买家"
    )
    customer = Customer(
        user_id=buyer_user_id,
        distributor_id=member_distributor_id,
        name="商城客户",
        phone="13800138000",
        phone_masked="138****8000",
        id_card_encrypted="test-ciphertext",
        id_card_masked="110***********1234",
        binding_status=BindingStatus.BOUND,
        bound_at=datetime(2026, 1, 1),
        version=1,
    )
    db_session.add(customer)
    await db_session.flush()
    member_context = {
        **context,
        "buyerUserId": buyer_user_id,
        "customerId": customer.id,
        "distributorId": member_distributor_id,
        "orgId": child_org.id,
    }
    bill = await add_bill(db_session, member_context, 500000, datetime(2026, 7, 10))
    _, mall_source = await add_mall_source(
        db_session, member_context, 200000, datetime(2026, 7, 15)
    )
    await add_performance_rule(
        db_session,
        member_context,
        tiers=[{"minCent": 0, "maxCent": None, "ratio": 0.08}],
    )
    await add_performance_rule(
        db_session,
        context,
        rule_type="org_management",
        tiers=[{"minCent": 0, "maxCent": None, "ratio": 0.1}],
    )
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING))
    await db_session.flush()
    await compute_commission(db_session, "2026-07")
    await capture_period_evidence(db_session, "2026-07")

    evidence = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == "2026-07",
            PerformanceEvidence.distributor_id == context["distributorId"],
            PerformanceEvidence.rule_type == RuleType.ORG_MANAGEMENT.value,
        )
    )
    assert evidence is not None
    assert evidence.frozen_members == sorted([context["distributorId"], member_distributor_id])
    assert evidence.organization_path_snapshot == [context["orgId"]]
    assert evidence.legacy_base_cent == 500000
    assert evidence.mall_base_cent == 200000
    assert evidence.original_commission_cent == 70000

    source_rows = (
        (
            await db_session.execute(
                select(PerformanceEvidenceSource)
                .where(PerformanceEvidenceSource.evidence_id == evidence.id)
                .order_by(PerformanceEvidenceSource.source_type)
            )
        )
        .scalars()
        .all()
    )
    assert [(row.source_type, row.source_id) for row in source_rows] == [
        ("bill", bill.id),
        ("mall", mall_source.id),
    ]
    assert {row.calculation_org_id for row in source_rows} == {child_org.id}
