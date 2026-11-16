"""Verified attribution changes only previously unassigned mall sources."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.mall_deps import MallActor
from src.models.binding import Customer
from src.models.commission_result import CommissionResult
from src.models.mall_base import utc_now
from src.models.mall_operations import MallFile, MallJob
from src.models.performance_adjustment import PerformanceAdjustment
from src.models.performance_evidence import PerformancePeriodVersion
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.services.mall_attribution_service import attribute_mall_consumption
from tests.mall_consumption_fixtures import (
    add_frozen_evidence,
    add_mall_source,
    add_performance_rule,
    performance_context,
)


@pytest.mark.asyncio
async def test_authorized_historical_binding_assigns_original_period_source_once(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    actor = MallActor("admin", 41, frozenset({"mall.attribution.write"}))

    result = await attribute_mall_consumption(
        db_session,
        actor=actor,
        consumption_id=source.id,
        expected_version=source.source_version,
        distributor_id=context["distributorId"],
        customer_id=context["customerId"],
        evidence_file_ids=[],
        reason="支付日前已生效的授权绑定记录",
        idempotency_key="attribution-unit-command-001",
    )

    await db_session.flush()
    period = await db_session.scalar(
        select(PerformancePeriodVersion).where(
            PerformancePeriodVersion.period == source.business_period
        )
    )
    assert result.source.status == "assigned"
    assert result.source.customer_id == context["customerId"]
    assert result.source.attributed_distributor_id == context["distributorId"]
    assert result.source.business_period == "2026-07"
    assert result.source.trade_org_id is None
    assert result.source.source_version == 2
    assert result.handling == "ready_for_settlement"
    assert period.revision == 1 and period.status == "open"


@pytest.mark.asyncio
async def test_pending_settlement_recomputes_and_replays_the_same_command_once(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    await add_performance_rule(
        db_session,
        context,
        tiers=[{"minCent": 0, "maxCent": None, "ratio": 0.08}],
    )
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.PENDING))
    await db_session.flush()
    actor = MallActor("admin", 42, frozenset({"mall.attribution.write"}))
    arguments = {
        "actor": actor,
        "consumption_id": source.id,
        "expected_version": source.source_version,
        "distributor_id": context["distributorId"],
        "customer_id": context["customerId"],
        "evidence_file_ids": [],
        "reason": "支付时已生效的授权绑定记录",
        "idempotency_key": "attribution-unit-replay-001",
    }

    first = await attribute_mall_consumption(db_session, **arguments)
    replay = await attribute_mall_consumption(db_session, **arguments)

    result = await db_session.scalar(
        select(CommissionResult).where(
            CommissionResult.period == "2026-07",
            CommissionResult.distributor_id == context["distributorId"],
        )
    )
    period = await db_session.get(PerformancePeriodVersion, "2026-07")
    assert first.handling == replay.handling == "recomputed"
    assert first.source.source_version == replay.source.source_version == 2
    assert result.commission_cent == 24000
    assert period.revision == 1 and period.recomputed_revision == 1


@pytest.mark.asyncio
async def test_frozen_attribution_builds_adjustment_without_rewriting_result(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    evidence = await add_frozen_evidence(
        db_session,
        context,
        rule_snapshot={"tiers": [{"minCent": 0, "maxCent": None, "ratio": 0.08}], "version": 4},
        original_base_cent=0,
        original_commission_cent=0,
        result_presence="not_generated",
        result_absence_reason="below_first_tier",
    )
    actor = MallActor("admin", 43, frozenset({"mall.attribution.write"}))

    result = await attribute_mall_consumption(
        db_session,
        actor=actor,
        consumption_id=source.id,
        expected_version=source.source_version,
        distributor_id=context["distributorId"],
        customer_id=context["customerId"],
        evidence_file_ids=[],
        reason="支付时已生效的授权绑定记录",
        idempotency_key="attribution-frozen-evidence-001",
    )

    period = await db_session.get(PerformancePeriodVersion, "2026-07")
    adjustment = await db_session.scalar(
        select(PerformanceAdjustment).where(
            PerformanceAdjustment.evidence_id == evidence.id,
            PerformanceAdjustment.trigger_source_type == "mall",
            PerformanceAdjustment.trigger_source_id == source.id,
        )
    )
    assert result.handling == "adjustment_pending"
    assert period.status == "frozen" and period.revision == 0
    assert evidence.result_presence == "not_generated" and evidence.original_commission_cent == 0
    assert adjustment is not None
    assert adjustment.origin_result_id is None
    assert adjustment.original_commission_cent == 0
    assert adjustment.replayed_commission_cent == 24000
    assert adjustment.delta_cent == 24000
    assert adjustment.status == "proposed"
    assert adjustment.trigger_version == source.source_version
    assert await db_session.scalar(select(CommissionResult.id)) is None


@pytest.mark.asyncio
async def test_frozen_attribution_without_original_anchor_stays_manual(db_session: AsyncSession):
    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    db_session.add(PerformanceSettlement(period="2026-07", status=SettlementStatus.REVIEWED))
    await db_session.flush()

    result = await attribute_mall_consumption(
        db_session,
        actor=MallActor("admin", 44, frozenset({"mall.attribution.write"})),
        consumption_id=source.id,
        expected_version=source.source_version,
        distributor_id=context["distributorId"],
        customer_id=context["customerId"],
        evidence_file_ids=[],
        reason="支付时已生效的授权绑定记录",
        idempotency_key="attribution-no-anchor-001",
    )

    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.entity_id == source.id,
            MallJob.kind.startswith("mall_performance_attribution"),
        )
    )
    assert result.handling == "manual_required"
    assert job.status == "manual" and job.last_error_code == "performance_evidence_missing"
    assert await db_session.scalar(select(CommissionResult.id)) is None


@pytest.mark.asyncio
async def test_verified_file_can_prove_late_attribution_without_phone_matching(db_session):
    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    customer = await db_session.get(Customer, context["customerId"])
    customer.bound_at = datetime(2026, 7, 16)
    file = MallFile(
        object_key="mall/verified/attribution/file-1",
        purpose="attribution_evidence",
        owner_actor_type="admin",
        owner_actor_id=45,
        order_id=source.order_id,
        mime="application/pdf",
        size=128,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now(),
    )
    db_session.add(file)
    await db_session.flush()

    result = await attribute_mall_consumption(
        db_session,
        actor=MallActor("admin", 45, frozenset({"mall.attribution.write"})),
        consumption_id=source.id,
        expected_version=source.source_version,
        distributor_id=context["distributorId"],
        customer_id=context["customerId"],
        evidence_file_ids=[file.id],
        reason="已核验授权资料",
        idempotency_key="attribution-file-evidence-001",
    )

    assert result.source.status == "assigned"
    assert result.source.attribution_evidence["basis"] == "admin_verified_files"
    assert result.source.attribution_evidence["evidenceFileIds"] == [str(file.id)]
    assert file.status == "bound" and file.order_id == source.order_id


@pytest.mark.asyncio
async def test_attribution_rejects_stale_version_and_assigned_source(db_session: AsyncSession):
    from src.core.exceptions import ConflictException

    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    actor = MallActor("admin", 46, frozenset({"mall.attribution.write"}))
    kwargs = {
        "actor": actor,
        "consumption_id": source.id,
        "expected_version": source.source_version + 1,
        "distributor_id": context["distributorId"],
        "customer_id": context["customerId"],
        "evidence_file_ids": [],
        "reason": "支付时已生效的授权绑定记录",
        "idempotency_key": "attribution-stale-version-001",
    }
    with pytest.raises(ConflictException, match="来源已变化"):
        await attribute_mall_consumption(db_session, **kwargs)
    source.attributed_distributor_id = context["distributorId"]
    source.status = "assigned"
    await db_session.flush()
    kwargs.update(
        expected_version=source.source_version,
        idempotency_key="attribution-already-assigned-001",
    )
    with pytest.raises(ConflictException, match="仅未归属"):
        await attribute_mall_consumption(db_session, **kwargs)
