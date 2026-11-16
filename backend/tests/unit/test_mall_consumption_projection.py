from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import TransactionStatus
from src.models.commission_result import CommissionResult
from src.models.distributor import Distributor, OrgRole
from src.models.mall_consumption import MallConsumption
from src.models.performance_rule import RuleType
from src.services import commission_service
from src.services.contribution_query_service import ConsumptionQueryService
from tests.mall_consumption_fixtures import (
    add_bill,
    add_mall_source,
    add_performance_rule,
    performance_context,
)


@pytest.mark.asyncio
async def test_unified_projection_merges_old_bills_and_mall_performance_base(
    db_session: AsyncSession,
):
    from src.services.consumption_projection_service import ConsumptionProjectionService

    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15))
    await add_mall_source(db_session, context, 90000, datetime(2026, 7, 20), attributed=False)
    await add_mall_source(db_session, context, 100000, datetime(2026, 6, 20))

    service = ConsumptionProjectionService()
    totals = await service.aggregate_by_distributor(
        db_session, [context["distributorId"]], month="2026-07"
    )
    assert totals == {context["distributorId"]: 1100000}


@pytest.mark.asyncio
async def test_partial_refund_keeps_full_base_and_full_goods_refund_sets_zero(
    db_session: AsyncSession,
):
    from src.services.consumption_projection_service import ConsumptionProjectionService

    context = await performance_context(db_session)
    await add_mall_source(
        db_session,
        context,
        100000,
        datetime(2026, 7, 10),
        successful_goods_refund_cent=50000,
        performance_base_cent=100000,
    )
    await add_mall_source(
        db_session,
        context,
        70000,
        datetime(2026, 7, 11),
        successful_goods_refund_cent=70000,
        performance_base_cent=0,
    )

    totals = await ConsumptionProjectionService().aggregate_by_distributor(
        db_session, [context["distributorId"]], month="2026-07"
    )
    assert totals == {context["distributorId"]: 100000}


@pytest.mark.asyncio
async def test_existing_commission_calculator_counts_mall_for_personal_and_management_rules(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15))
    distributor = await db_session.get(Distributor, context["distributorId"])
    distributor.org_role = OrgRole.ADMIN
    await add_performance_rule(
        db_session,
        context,
        tiers=[{"minCent": 1000000, "maxCent": None, "ratio": 0.08}],
    )
    await add_performance_rule(
        db_session,
        context,
        rule_type=RuleType.ORG_MANAGEMENT.value,
        tiers=[{"minCent": 1000000, "maxCent": None, "ratio": 0.02}],
    )

    result = await commission_service.compute_commission(db_session, "2026-07")
    rows = (
        await db_session.scalars(
            select(CommissionResult).where(CommissionResult.period == "2026-07")
        )
    ).all()
    by_type = {row.rule_type: row for row in rows}
    assert result["computed"] == 2
    assert by_type[RuleType.INTRA_ORG].base_cent == 1100000
    assert by_type[RuleType.INTRA_ORG].commission_cent == 88000
    assert by_type[RuleType.ORG_MANAGEMENT].base_cent == 1100000
    assert by_type[RuleType.ORG_MANAGEMENT].commission_cent == 22000


@pytest.mark.asyncio
async def test_unfrozen_org_aggregate_uses_current_org_and_leaves_trade_org_evidence_unchanged(
    db_session: AsyncSession,
):
    from src.models.distributor import Distributor
    from src.models.organization import Organization
    from src.services.consumption_projection_service import ConsumptionProjectionService

    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15))
    moved_org = Organization(name="后调入组织", level=1)
    db_session.add(moved_org)
    await db_session.flush()
    distributor = await db_session.get(Distributor, context["distributorId"])
    distributor.org_id = moved_org.id
    await db_session.flush()

    service = ConsumptionProjectionService()
    original_org = await service.aggregate_by_organization(
        db_session, {context["orgId"]}, month="2026-07"
    )
    current_org = await service.aggregate_by_organization(
        db_session, {moved_org.id}, month="2026-07"
    )
    source = await db_session.scalar(select(MallConsumption))
    assert source.trade_org_id == context["orgId"]
    assert original_org == {}
    assert current_org == {moved_org.id: 1100000}


@pytest.mark.asyncio
async def test_global_person_cursor_namespaces_source_ids_and_keeps_one_order(
    db_session: AsyncSession,
):
    from src.services.consumption_projection_service import ConsumptionProjectionService

    context = await performance_context(db_session)
    for day in range(1, 17):
        occurred = datetime(2026, 7, day)
        await add_bill(db_session, context, day * 100, occurred)
        await add_mall_source(db_session, context, day * 200, occurred)

    service = ConsumptionProjectionService()
    first = await service.list_person_details(
        db_session, context["distributorId"], month="2026-07", page_size=20
    )
    second = await service.list_person_details(
        db_session,
        context["distributorId"],
        month="2026-07",
        cursor=first["nextCursor"],
        page_size=20,
    )
    items = first["items"] + second["items"]

    assert len(items) == 32
    assert len({item["id"] for item in items}) == 32
    assert {item["source"] for item in items} == {"legacy_bill", "mall_order"}
    assert all(item["sourceId"] for item in items)
    assert items[0]["occurredAt"] >= items[-1]["occurredAt"]


@pytest.mark.asyncio
async def test_existing_promoter_projection_api_keeps_legacy_bill_service_compatible(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 8000, datetime(2026, 7, 10), status=TransactionStatus.PAID)
    service = ConsumptionQueryService()
    result = await service.get_overview(db_session, context["personUserId"], "2026-07")
    assert result["monthlyAmountCent"] == 8000
