"""End-to-end performance projection, frozen attribution, and redemption flows."""

from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.mall_deps import MallActor
from src.core.exceptions import BadRequestException
from src.models.commission_result import CommissionResult
from src.models.distributor import Distributor, OrgRole
from src.models.mall_consumption import MallConsumption
from src.models.performance_adjustment import PerformanceAdjustment
from src.models.performance_evidence import PerformanceEvidence
from src.models.performance_rule import RuleType
from src.models.personal_performance_rule import PersonalPerformanceRule
from src.services import commission_service, settlement_service
from src.services.mall_attribution_service import attribute_mall_consumption
from src.services.mall_consumption_service import performance_base
from src.services.performance_adjustment_application_service import (
    adjustment_summaries_for_results,
)
from src.services.performance_adjustment_service import (
    propose_adjustment,
    review_performance_adjustment,
)
from src.services.performance_period_service import bump_period
from tests.conftest import seed_admin, seed_user
from tests.mall_consumption_fixtures import (
    add_bill,
    add_mall_source,
    add_performance_rule,
    performance_context,
)


async def _add_org_admin(db: AsyncSession, org_id: int) -> int:
    user_id = await seed_user(
        db,
        openid=f"mall-performance-admin-{org_id}",
        user_type="distributor",
        name="绩效组织管理员",
    )
    distributor = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole.ADMIN)
    db.add(distributor)
    await db.flush()
    return distributor.id


@pytest.mark.asyncio
async def test_month_settlement_merges_bill_and_mall_with_personal_and_management_rules(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    manager_id = await _add_org_admin(db_session, context["orgId"])
    await add_bill(db_session, context, 800000, datetime(2026, 7, 15))
    await add_mall_source(db_session, context, 300000, datetime(2026, 7, 20))
    await add_performance_rule(
        db_session,
        context,
        tiers=[
            {"minCent": 0, "maxCent": 1000000, "ratio": 0.05},
            {"minCent": 1000000, "maxCent": None, "ratio": 0.08},
        ],
    )
    await add_performance_rule(
        db_session,
        context,
        rule_type="org_management",
        tiers=[{"minCent": 0, "maxCent": None, "ratio": 0.02}],
    )
    db_session.add(
        PersonalPerformanceRule(
            distributor_id=context["distributorId"],
            tiers=[{"minCent": 0, "maxCent": None, "ratio": 0.07}],
            version=1,
        )
    )
    await db_session.flush()

    await settlement_service.settle(db_session, "2026-07", operator_id=1)
    await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)

    rows = (
        await db_session.scalars(
            select(CommissionResult).where(CommissionResult.period == "2026-07")
        )
    ).all()
    by_key = {(row.distributor_id, row.rule_type): row for row in rows}
    personal = by_key[(context["distributorId"], RuleType.INTRA_ORG)]
    management = by_key[(manager_id, RuleType.ORG_MANAGEMENT)]
    assert personal.base_cent == management.base_cent == 1100000
    assert personal.ratio == "0.070000"
    assert personal.commission_cent == 77000
    assert personal.rule_snapshot["source"] == "personal"
    assert management.ratio == "0.020000"
    assert management.commission_cent == 22000


@pytest.mark.asyncio
async def test_monthly_commission_rounds_once_after_combining_source_cents(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 1, datetime(2026, 7, 15))
    await add_mall_source(db_session, context, 1, datetime(2026, 7, 20))
    await add_performance_rule(
        db_session,
        context,
        tiers=[{"minCent": 0, "maxCent": None, "ratio": 0.5}],
    )

    await commission_service.compute_commission(db_session, "2026-07")

    result = await db_session.scalar(
        select(CommissionResult).where(
            CommissionResult.period == "2026-07",
            CommissionResult.distributor_id == context["distributorId"],
            CommissionResult.rule_type == RuleType.INTRA_ORG,
        )
    )
    assert result is not None
    assert result.base_cent == 2
    assert result.commission_cent == 1


@pytest.mark.asyncio
async def test_ac052_frozen_attribution_without_original_result_is_applied_and_redeemed(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 15))
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 20), attributed=False
    )
    await add_performance_rule(
        db_session,
        context,
        tiers=[{"minCent": 1000000, "maxCent": None, "ratio": 0.08}],
    )
    await settlement_service.settle(db_session, "2026-07", operator_id=1)
    await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)

    anchor = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == "2026-07",
            PerformanceEvidence.distributor_id == context["distributorId"],
            PerformanceEvidence.rule_type == RuleType.INTRA_ORG.value,
        )
    )
    assert anchor is not None
    assert anchor.result_id is None
    assert anchor.result_presence == "not_generated"
    assert anchor.result_absence_reason == "below_first_tier"
    assert anchor.original_base_cent == 800000
    assert anchor.original_commission_cent == 0
    assert await db_session.scalar(
        select(func.count(CommissionResult.id)).where(
            CommissionResult.period == "2026-07",
            CommissionResult.distributor_id == context["distributorId"],
            CommissionResult.rule_type == RuleType.INTRA_ORG,
        )
    ) == 0

    admin_id = await seed_admin(db_session, username="ac052-performance-reviewer")
    actor = MallActor(
        actor_type="admin",
        actor_id=admin_id,
        permissions=frozenset({"mall.attribution.write"}),
    )
    first = await attribute_mall_consumption(
        db_session,
        actor=actor,
        consumption_id=source.id,
        expected_version=source.source_version,
        distributor_id=context["distributorId"],
        customer_id=context["customerId"],
        evidence_file_ids=[],
        reason="确认支付时有效的客户绑定记录",
        idempotency_key="ac052-frozen-attribution-command-001",
    )
    replay = await attribute_mall_consumption(
        db_session,
        actor=actor,
        consumption_id=source.id,
        expected_version=1,
        distributor_id=context["distributorId"],
        customer_id=context["customerId"],
        evidence_file_ids=[],
        reason="确认支付时有效的客户绑定记录",
        idempotency_key="ac052-frozen-attribution-command-001",
    )
    assert first.handling == replay.handling == "adjustment_pending"
    assert first.source.business_period == "2026-07"
    assert first.source.performance_base_cent == 300000

    adjustments = (
        await db_session.scalars(
            select(PerformanceAdjustment).where(PerformanceAdjustment.evidence_id == anchor.id)
        )
    ).all()
    assert len(adjustments) == 1
    adjustment = adjustments[0]
    assert adjustment.status == "proposed"
    assert adjustment.origin_result_id is None
    assert adjustment.delta_cent == 88000
    assert adjustment.remaining_cent == 88000
    await review_performance_adjustment(
        db_session,
        adjustment_id=adjustment.id,
        expected_version=adjustment.version,
        admin_id=admin_id,
    )

    await commission_service.compute_commission(db_session, "2026-08")
    await settlement_service.review_settlement(db_session, "2026-08", operator_id=1)
    target = await db_session.scalar(
        select(CommissionResult).where(
            CommissionResult.period == "2026-08",
            CommissionResult.distributor_id == context["distributorId"],
            CommissionResult.rule_type == RuleType.INTRA_ORG,
        )
    )
    assert target is not None
    assert target.origin_kind == "adjustment_only"
    assert target.base_cent == target.commission_cent == 0
    amounts = (await adjustment_summaries_for_results(db_session, [target]))[target.id]
    assert amounts["normalCommissionCent"] == 0
    assert amounts["confirmedAdjustmentCent"] == 88000
    assert amounts["redeemableCent"] == 88000

    redeemed = await commission_service.redeem_commission_points(
        db_session,
        "2026-08",
        context["distributorId"],
        RuleType.INTRA_ORG.value,
        operator_id=admin_id,
    )
    assert redeemed["redeemableCent"] == redeemed["redeemedPoints"] * 100 == 88000
    await db_session.refresh(target)
    await db_session.refresh(adjustment)
    assert target.commission_cent == 0
    assert target.redeemed_points_x100 == 88000
    assert adjustment.remaining_cent == 0
    assert await db_session.scalar(
        select(func.count(CommissionResult.id)).where(
            CommissionResult.period == "2026-07",
            CommissionResult.distributor_id == context["distributorId"],
            CommissionResult.rule_type == RuleType.INTRA_ORG,
        )
    ) == 0


@pytest.mark.asyncio
async def test_negative_frozen_differences_offset_next_month_once_and_keep_original_rows(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    manager_id = await _add_org_admin(db_session, context["orgId"])
    _, source = await add_bill_and_mall_inputs(db_session, context)
    await add_performance_rule(
        db_session,
        context,
        tiers=[
            {"minCent": 0, "maxCent": 1000000, "ratio": 0.05},
            {"minCent": 1000000, "maxCent": None, "ratio": 0.08},
        ],
    )
    await add_performance_rule(
        db_session,
        context,
        rule_type="org_management",
        tiers=[{"minCent": 0, "maxCent": None, "ratio": 0.02}],
    )
    await settlement_service.settle(db_session, "2026-07", operator_id=1)
    await settlement_service.review_settlement(db_session, "2026-07", operator_id=1)

    original_rows = (
        await db_session.scalars(
            select(CommissionResult).where(CommissionResult.period == "2026-07")
        )
    ).all()
    originals = {(row.distributor_id, row.rule_type): row for row in original_rows}
    personal_result = originals[(context["distributorId"], RuleType.INTRA_ORG)]
    management_result = originals[(manager_id, RuleType.ORG_MANAGEMENT)]
    personal_anchor = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == "2026-07",
            PerformanceEvidence.distributor_id == context["distributorId"],
            PerformanceEvidence.rule_type == RuleType.INTRA_ORG.value,
        )
    )
    management_anchor = await db_session.scalar(
        select(PerformanceEvidence).where(
            PerformanceEvidence.period == "2026-07",
            PerformanceEvidence.distributor_id == manager_id,
            PerformanceEvidence.rule_type == RuleType.ORG_MANAGEMENT.value,
        )
    )
    assert personal_result.commission_cent == 88000
    assert management_result.commission_cent == 22000

    source.successful_goods_refund_cent = source.original_goods_cent
    source.performance_base_cent = performance_base(
        source.original_goods_cent, source.successful_goods_refund_cent
    )
    source.source_version += 1
    source.version += 1
    await bump_period(db_session, source.business_period)
    await db_session.flush()

    personal_adjustment = await propose_adjustment(
        db_session,
        personal_anchor.id,
        trigger_source_type="mall",
        trigger_source_id=source.id,
        trigger_version=source.source_version,
    )
    management_adjustment = await propose_adjustment(
        db_session,
        management_anchor.id,
        trigger_source_type="mall",
        trigger_source_id=source.id,
        trigger_version=source.source_version,
    )
    assert personal_adjustment.delta_cent == -48000
    assert management_adjustment.delta_cent == -6000
    reviewer_id = await seed_admin(db_session, username="negative-adjustment-reviewer")
    await review_performance_adjustment(
        db_session,
        adjustment_id=personal_adjustment.id,
        expected_version=personal_adjustment.version,
        admin_id=reviewer_id,
    )
    await review_performance_adjustment(
        db_session,
        adjustment_id=management_adjustment.id,
        expected_version=management_adjustment.version,
        admin_id=reviewer_id,
    )
    assert personal_result.commission_cent == 88000
    assert management_result.commission_cent == 22000

    await add_bill(db_session, context, 250000, datetime(2026, 8, 15))
    await settlement_service.settle(db_session, "2026-08", operator_id=1)
    await settlement_service.review_settlement(db_session, "2026-08", operator_id=1)

    target_rows = (
        await db_session.scalars(
            select(CommissionResult).where(CommissionResult.period == "2026-08")
        )
    ).all()
    targets = {(row.distributor_id, row.rule_type): row for row in target_rows}
    member_target = targets[(context["distributorId"], RuleType.INTRA_ORG)]
    manager_target = targets[(manager_id, RuleType.ORG_MANAGEMENT)]
    assert member_target.commission_cent == 12500
    assert manager_target.commission_cent == 5000

    summaries = await adjustment_summaries_for_results(
        db_session, [member_target, manager_target]
    )
    member_summary = summaries[member_target.id]
    manager_summary = summaries[manager_target.id]
    assert member_summary["normalCommissionCent"] == 12500
    assert member_summary["confirmedAdjustmentCent"] == -12500
    assert member_summary["appliedDebtCent"] == 12500
    assert member_summary["redeemableCent"] == 0
    assert member_summary["pendingDebtCent"] == 35500
    assert manager_summary["normalCommissionCent"] == 5000
    assert manager_summary["confirmedAdjustmentCent"] == -5000
    assert manager_summary["appliedDebtCent"] == 5000
    assert manager_summary["redeemableCent"] == 0
    assert manager_summary["pendingDebtCent"] == 1000
    await db_session.refresh(personal_adjustment)
    await db_session.refresh(management_adjustment)
    assert personal_adjustment.remaining_cent == -35500
    assert management_adjustment.remaining_cent == -1000
    assert personal_result.commission_cent == 88000
    assert management_result.commission_cent == 22000

    with pytest.raises(BadRequestException, match="净可兑现积分不足"):
        await commission_service.redeem_commission_points(
            db_session,
            "2026-08",
            context["distributorId"],
            RuleType.INTRA_ORG.value,
            operator_id=reviewer_id,
        )


async def add_bill_and_mall_inputs(db: AsyncSession, context: dict):
    await add_bill(db, context, 800000, datetime(2026, 7, 15))
    return await add_mall_source(db, context, 300000, datetime(2026, 7, 20))
