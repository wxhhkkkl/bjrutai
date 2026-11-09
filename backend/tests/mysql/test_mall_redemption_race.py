"""InnoDB ordering of a mall debt application against point redemption."""

import asyncio
from datetime import datetime
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.core.exceptions import AppException
from src.models.commission_result import CommissionResult
from src.models.distributor import Distributor, OrgRole
from src.models.organization import Organization
from src.models.performance_adjustment import (
    PerformanceAdjustment,
    PerformanceAdjustmentApplication,
)
from src.models.performance_evidence import PerformanceEvidence
from src.models.performance_rule import RuleType
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.models.user import User, UserType


async def _race_result(sessions, adjustment_id, target_result_id, distributor_id):
    async def apply_debt():
        from src.services.performance_adjustment_application_service import (
            apply_adjustment_to_result,
        )

        async with sessions() as db:
            try:
                await apply_adjustment_to_result(db, adjustment_id, target_result_id)
                await db.commit()
                return "applied"
            except AppException as error:
                await db.rollback()
                return f"blocked:{error.status_code}"

    async def redeem_points():
        from src.services.commission_service import redeem_commission_points

        async with sessions() as db:
            try:
                await redeem_commission_points(
                    db,
                    "2026-08",
                    distributor_id,
                    RuleType.INTRA_ORG.value,
                    operator_id=9001,
                )
                await db.commit()
                return "redeemed"
            except AppException as error:
                await db.rollback()
                return f"blocked:{error.status_code}"

    return await asyncio.wait_for(asyncio.gather(apply_debt(), redeem_points()), timeout=15)


@pytest.mark.asyncio
async def test_adjustment_application_and_points_redemption_serialize_without_rewriting_history(
    mall_mysql_sessions,
):
    token = uuid4().hex
    async with mall_mysql_sessions() as db:
        org = Organization(name=f"调整并发-{token[:8]}", level=1)
        db.add(org)
        await db.flush()
        user = User(openid=f"mall-adjustment-{token}", user_type=UserType.PROMOTER, name="核销并发")
        db.add(user)
        await db.flush()
        distributor = Distributor(
            user_id=user.id,
            org_id=org.id,
            org_role=OrgRole.MEMBER,
        )
        db.add(distributor)
        await db.flush()

        origin_settlement = PerformanceSettlement(
            period="2026-07", status=SettlementStatus.REVIEWED
        )
        target_settlement = PerformanceSettlement(
            period="2026-08", status=SettlementStatus.REVIEWED
        )
        db.add_all([origin_settlement, target_settlement])
        await db.flush()
        redeemed_at = datetime(2026, 8, 2, 10, 0, 0)
        origin_result = CommissionResult(
            period="2026-07",
            distributor_id=distributor.id,
            org_id=org.id,
            rule_type=RuleType.INTRA_ORG,
            base_cent=1100000,
            ratio="0.08",
            commission_cent=88000,
            rule_snapshot={"tiers": [{"minCent": 1000000, "ratio": 0.08}]},
            redeemed_points_x100=88000,
            points_redeemed_by=7001,
            points_redeemed_at=redeemed_at,
        )
        target_result = CommissionResult(
            period="2026-08",
            distributor_id=distributor.id,
            org_id=org.id,
            rule_type=RuleType.INTRA_ORG,
            base_cent=10000,
            ratio="0.08",
            commission_cent=10000,
            rule_snapshot={"tiers": [{"minCent": 0, "ratio": 0.08}]},
        )
        db.add_all([origin_result, target_result])
        await db.flush()
        evidence = PerformanceEvidence(
            settlement_id=origin_settlement.id,
            evidence_key=f"2026-07:{distributor.id}:intra_org:{token[:8]}",
            result_id=origin_result.id,
            period="2026-07",
            distributor_id=distributor.id,
            rule_type=RuleType.INTRA_ORG.value,
            org_id=org.id,
            frozen_members=[distributor.id],
            organization_path_snapshot=[org.id],
            rule_source="org",
            rule_snapshot={"tiers": [{"minCent": 1000000, "ratio": 0.08}]},
            algorithm_version="mall-performance-v1",
            legacy_base_cent=800000,
            mall_base_cent=300000,
            original_base_cent=1100000,
            original_commission_cent=88000,
            result_presence="present",
            input_digest="f" * 64,
            frozen_at=datetime(2026, 8, 1),
            evidence_status="complete",
        )
        db.add(evidence)
        await db.flush()
        adjustment = PerformanceAdjustment(
            adjustment_no=f"ADJ-{token[:20]}",
            origin_period="2026-07",
            origin_result_id=origin_result.id,
            evidence_id=evidence.id,
            trigger_source_type="mall",
            trigger_source_id=7001,
            trigger_version=2,
            beneficiary_id=distributor.id,
            rule_type=RuleType.INTRA_ORG.value,
            original_commission_cent=88000,
            replayed_commission_cent=40000,
            prior_confirmed_adjustment_cent=0,
            delta_cent=-48000,
            status="reviewed",
            remaining_cent=-48000,
        )
        db.add(adjustment)
        await db.flush()
        adjustment_id = adjustment.id
        target_result_id = target_result.id
        distributor_id = distributor.id
        origin_result_id = origin_result.id
        await db.commit()

    started = perf_counter()
    outcomes = await _race_result(
        mall_mysql_sessions, adjustment_id, target_result_id, distributor_id
    )
    elapsed = perf_counter() - started
    print(f"T129 measure: performance-debt versus redemption race elapsed={elapsed:.3f}s")
    assert "redeemed" in outcomes or "applied" in outcomes

    async with mall_mysql_sessions() as db:
        origin = await db.get(CommissionResult, origin_result_id)
        target = await db.get(CommissionResult, target_result_id)
        adjustment = await db.get(PerformanceAdjustment, adjustment_id)
        applications = (
            await db.scalars(
                select(PerformanceAdjustmentApplication).where(
                    PerformanceAdjustmentApplication.adjustment_id == adjustment_id
                )
            )
        ).all()
        settled_adjustment_cent = sum(row.settled_cent for row in applications)

        assert origin.commission_cent == 88000
        assert origin.redeemed_points_x100 == 88000
        assert origin.points_redeemed_by == 7001
        assert origin.points_redeemed_at == redeemed_at
        assert target.commission_cent == 10000
        assert target.redeemed_points_x100 in (None, 0, 10000)
        assert settled_adjustment_cent in (0, -10000)
        if target.redeemed_points_x100 == 10000:
            assert settled_adjustment_cent == 0
        else:
            assert settled_adjustment_cent == -10000
        assert adjustment.remaining_cent == -48000 - settled_adjustment_cent
        assert (
            await db.scalar(
                select(func.count(PerformanceAdjustmentApplication.id)).where(
                    PerformanceAdjustmentApplication.adjustment_id == adjustment_id
                )
            )
            <= 1
        )
