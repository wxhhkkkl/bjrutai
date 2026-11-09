"""Original-period replay and adjustment idempotency tests."""

from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commission_result import CommissionResult
from src.models.mall_consumption import MallConsumption
from src.models.performance_adjustment import PerformanceAdjustment
from src.models.performance_evidence import PerformanceEvidence
from src.models.performance_rule import RuleType
from tests.mall_consumption_fixtures import (
    add_frozen_evidence,
    add_mall_source,
    performance_context,
)


PERSONAL_TIERS = [{"minCent": 1000000, "maxCent": None, "ratio": 0.08}]
MANAGEMENT_TIERS = [{"minCent": 0, "maxCent": None, "ratio": 0.02}]


@pytest.mark.asyncio
async def test_unassigned_order_adds_positive_delta_without_original_result_and_replays_once(
    db_session: AsyncSession,
):
    from src.services.performance_adjustment_service import propose_adjustment

    context = await performance_context(db_session)
    await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    evidence = await add_frozen_evidence(
        db_session,
        context,
        rule_snapshot={"tiers": PERSONAL_TIERS, "version": 4},
        original_base_cent=800000,
        legacy_base_cent=800000,
        result_presence="not_generated",
        result_absence_reason="below_first_tier",
    )
    source = await db_session.scalar(
        select(MallConsumption).where(MallConsumption.status == "unassigned")
    )
    source.customer_id = context["customerId"]
    source.attributed_distributor_id = context["distributorId"]
    source.trade_org_id = context["orgId"]
    source.status = "assigned"
    source.attribution_evidence = {"basis": "authorized_binding_confirmation"}
    source.source_version += 1
    await db_session.flush()

    for _ in range(2):
        await propose_adjustment(
            db_session,
            evidence.id,
            trigger_source_type="mall",
            trigger_source_id=source.id,
            trigger_version=source.source_version,
        )

    adjustment = await db_session.scalar(
        select(PerformanceAdjustment).where(
            PerformanceAdjustment.evidence_id == evidence.id,
            PerformanceAdjustment.trigger_source_type == "mall",
            PerformanceAdjustment.trigger_source_id == source.id,
            PerformanceAdjustment.trigger_version == source.source_version,
        )
    )
    assert adjustment is not None
    assert adjustment.origin_result_id is None
    assert adjustment.original_commission_cent == 0
    assert adjustment.replayed_commission_cent == 88000
    assert adjustment.prior_confirmed_adjustment_cent == 0
    assert adjustment.delta_cent == 88000
    assert adjustment.status == "proposed"
    assert await db_session.scalar(
        select(func.count(PerformanceAdjustment.id)).where(
            PerformanceAdjustment.evidence_id == evidence.id,
            PerformanceAdjustment.trigger_source_type == "mall",
            PerformanceAdjustment.trigger_source_id == source.id,
            PerformanceAdjustment.trigger_version == source.source_version,
        )
    ) == 1
    assert evidence.result_presence == "not_generated"


@pytest.mark.asyncio
async def test_delta_subtracts_cumulative_confirmed_adjustments_only(db_session: AsyncSession):
    from src.services.performance_adjustment_service import propose_adjustment

    context = await performance_context(db_session)
    _, first_source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15)
    )
    evidence = await add_frozen_evidence(
        db_session,
        context,
        rule_snapshot={"tiers": PERSONAL_TIERS, "version": 4},
        original_base_cent=800000,
        legacy_base_cent=800000,
    )
    prior = PerformanceAdjustment(
        adjustment_no="ADJ-PRIOR-001",
        origin_period="2026-07",
        origin_result_id=None,
        evidence_id=evidence.id,
        trigger_source_type="mall",
        trigger_source_id=first_source.id,
        trigger_version=1,
        beneficiary_id=context["distributorId"],
        rule_type=RuleType.INTRA_ORG.value,
        original_commission_cent=0,
        replayed_commission_cent=88000,
        prior_confirmed_adjustment_cent=0,
        delta_cent=88000,
        status="reviewed",
        remaining_cent=88000,
    )
    db_session.add(prior)
    _, next_source = await add_mall_source(
        db_session, context, 100000, datetime(2026, 7, 20)
    )
    await db_session.flush()

    await propose_adjustment(
        db_session,
        evidence.id,
        trigger_source_type="mall",
        trigger_source_id=next_source.id,
        trigger_version=next_source.source_version,
    )
    adjustment = await db_session.scalar(
        select(PerformanceAdjustment).where(
            PerformanceAdjustment.evidence_id == evidence.id,
            PerformanceAdjustment.trigger_source_id == next_source.id,
        )
    )
    assert adjustment.replayed_commission_cent == 96000
    assert adjustment.prior_confirmed_adjustment_cent == 88000
    assert adjustment.delta_cent == 8000


@pytest.mark.asyncio
async def test_refund_replays_personal_and_management_tiers_from_separate_frozen_rules(
    db_session: AsyncSession,
):
    from src.services.performance_adjustment_service import propose_adjustment

    context = await performance_context(db_session)
    _, source = await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15))
    personal_result = CommissionResult(
        period="2026-07",
        distributor_id=context["distributorId"],
        org_id=context["orgId"],
        rule_type=RuleType.INTRA_ORG,
        base_cent=1100000,
        ratio="0.08",
        commission_cent=88000,
        rule_snapshot={"tiers": PERSONAL_TIERS},
    )
    management_result = CommissionResult(
        period="2026-07",
        distributor_id=context["distributorId"],
        org_id=context["orgId"],
        rule_type=RuleType.ORG_MANAGEMENT,
        base_cent=1100000,
        ratio="0.02",
        commission_cent=22000,
        rule_snapshot={"tiers": MANAGEMENT_TIERS},
    )
    db_session.add_all([personal_result, management_result])
    await db_session.flush()
    personal = await add_frozen_evidence(
        db_session,
        context,
        rule_type=RuleType.INTRA_ORG.value,
        result_id=personal_result.id,
        rule_snapshot={"tiers": PERSONAL_TIERS, "version": 4},
        original_base_cent=1100000,
        legacy_base_cent=800000,
        mall_base_cent=300000,
        original_commission_cent=88000,
        result_presence="present",
        result_absence_reason=None,
    )
    management = await add_frozen_evidence(
        db_session,
        context,
        rule_type=RuleType.ORG_MANAGEMENT.value,
        result_id=management_result.id,
        rule_snapshot={"tiers": MANAGEMENT_TIERS, "version": 3},
        original_base_cent=1100000,
        legacy_base_cent=800000,
        mall_base_cent=300000,
        original_commission_cent=22000,
        result_presence="present",
        result_absence_reason=None,
    )
    source.successful_goods_refund_cent = 300000
    source.performance_base_cent = 0
    source.source_version += 1
    await db_session.flush()

    for evidence in (personal, management):
        await propose_adjustment(
            db_session,
            evidence.id,
            trigger_source_type="mall",
            trigger_source_id=source.id,
            trigger_version=source.source_version,
        )

    rows = (
        await db_session.scalars(
            select(PerformanceAdjustment).where(
                PerformanceAdjustment.evidence_id.in_([personal.id, management.id])
            )
        )
    ).all()
    by_rule = {row.rule_type: row for row in rows}
    assert by_rule[RuleType.INTRA_ORG.value].replayed_commission_cent == 0
    assert by_rule[RuleType.INTRA_ORG.value].delta_cent == -88000
    assert by_rule[RuleType.ORG_MANAGEMENT.value].replayed_commission_cent == 16000
    assert by_rule[RuleType.ORG_MANAGEMENT.value].delta_cent == -6000
    assert personal_result.commission_cent == 88000
    assert management_result.commission_cent == 22000


@pytest.mark.asyncio
async def test_missing_original_rule_stays_manual_and_does_not_guess_current_rule(
    db_session: AsyncSession,
):
    from src.services.performance_adjustment_service import propose_adjustment

    context = await performance_context(db_session)
    _, source = await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15))
    evidence = await add_frozen_evidence(
        db_session,
        context,
        rule_snapshot={},
        original_base_cent=800000,
        legacy_base_cent=800000,
        evidence_status="manual_required",
    )
    await propose_adjustment(
        db_session,
        evidence.id,
        trigger_source_type="mall",
        trigger_source_id=source.id,
        trigger_version=source.source_version,
    )
    adjustment = await db_session.scalar(
        select(PerformanceAdjustment).where(
            PerformanceAdjustment.evidence_id == evidence.id,
            PerformanceAdjustment.trigger_source_id == source.id,
        )
    )
    assert adjustment is not None
    assert adjustment.status == "manual_required"
    assert adjustment.replayed_commission_cent == 0
    assert adjustment.delta_cent == 0


@pytest.mark.asyncio
async def test_proposing_negative_delta_never_rewrites_already_redeemed_original_result(
    db_session: AsyncSession,
):
    from src.services.performance_adjustment_service import propose_adjustment

    context = await performance_context(db_session)
    _, source = await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15))
    redeemed_at = datetime(2026, 8, 1)
    result = CommissionResult(
        period="2026-07",
        distributor_id=context["distributorId"],
        org_id=context["orgId"],
        rule_type=RuleType.INTRA_ORG,
        base_cent=1100000,
        ratio="0.08",
        commission_cent=88000,
        rule_snapshot={"tiers": PERSONAL_TIERS},
        redeemed_points_x100=88000,
        points_redeemed_by=1001,
        points_redeemed_at=redeemed_at,
    )
    db_session.add(result)
    await db_session.flush()
    evidence = await add_frozen_evidence(
        db_session,
        context,
        result_id=result.id,
        rule_snapshot={"tiers": PERSONAL_TIERS, "version": 4},
        original_base_cent=1100000,
        legacy_base_cent=800000,
        mall_base_cent=300000,
        original_commission_cent=88000,
        result_presence="present",
        result_absence_reason=None,
    )
    source.successful_goods_refund_cent = 300000
    source.performance_base_cent = 0
    source.source_version += 1
    await db_session.flush()

    await propose_adjustment(
        db_session,
        evidence.id,
        trigger_source_type="mall",
        trigger_source_id=source.id,
        trigger_version=source.source_version,
    )
    await db_session.refresh(result)
    assert result.commission_cent == 88000
    assert result.redeemed_points_x100 == 88000
    assert result.points_redeemed_by == 1001
    assert result.points_redeemed_at == redeemed_at
