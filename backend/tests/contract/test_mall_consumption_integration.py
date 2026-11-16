from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.services.report_service import ReportService
from tests.conftest import make_access_token
from tests.mall_consumption_fixtures import add_bill, add_mall_source, performance_context


def _buyer_headers(user_id):
    token = create_access_token(data={"sub": str(user_id), "user_type": "promoter"})
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    token = make_access_token(user_id=1, user_type="admin", permissions=["contributions.read"])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_buyer_summary_merges_bill_and_mall_sources(
    client: AsyncClient, db_session: AsyncSession
):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15))

    summary = (
        await client.get(
            "/api/v1/contributions/overview?month=2026-07",
            headers=_buyer_headers(context["personUserId"]),
        )
    ).json()["data"]
    assert summary["monthlyAmountCent"] == 1100000


@pytest.mark.asyncio
async def test_buyer_global_details_keep_source_type_and_native_source_id(
    client: AsyncClient, db_session: AsyncSession
):
    context = await performance_context(db_session)
    await add_bill(db_session, context, 800000, datetime(2026, 7, 10))
    order, _ = await add_mall_source(db_session, context, 300000, datetime(2026, 7, 15))

    result = (
        await client.get(
            "/api/v1/contributions?month=2026-07&pageSize=1",
            headers=_buyer_headers(context["personUserId"]),
        )
    ).json()["data"]
    assert result["items"][0]["source"] == "mall_order"
    assert result["items"][0]["sourceId"] == str(order.id)
    assert result["items"][0]["id"] != str(order.id)


@pytest.mark.asyncio
async def test_admin_summary_includes_mall_only_sources(
    client: AsyncClient, db_session: AsyncSession
):
    context = await performance_context(db_session)
    for day in range(1, 17):
        occurred = datetime(2026, 7, day)
        await add_bill(db_session, context, day * 100, occurred)
        await add_mall_source(db_session, context, day * 200, occurred)

    dashboard = (
        await client.get(
            "/api/v1/admin/contributions/dashboard?month=2026-07&period=1m",
            headers=_admin_headers(),
        )
    ).json()["data"]
    assert dashboard["stats"]["monthlyAmountCent"] == sum(day * 300 for day in range(1, 17))


@pytest.mark.asyncio
async def test_admin_latest30_is_a_single_global_page(
    client: AsyncClient, db_session: AsyncSession
):
    context = await performance_context(db_session)
    for day in range(1, 17):
        occurred = datetime(2026, 7, day)
        await add_bill(db_session, context, day * 100, occurred)
        await add_mall_source(db_session, context, day * 200, occurred)

    dashboard = (
        await client.get(
            "/api/v1/admin/contributions/dashboard?month=2026-07&period=1m",
            headers=_admin_headers(),
        )
    ).json()["data"]
    assert len(dashboard["latest"]) == 30
    assert {item["sourceType"] for item in dashboard["latest"]} == {
        "legacy_bill",
        "mall_order",
    }
    assert all(item["sourceId"] for item in dashboard["latest"])


@pytest.mark.asyncio
async def test_performance_allocation_report_includes_assigned_mall_sources(
    db_session: AsyncSession,
):
    context = await performance_context(db_session)
    for day in range(1, 17):
        occurred = datetime(2026, 7, day)
        await add_bill(db_session, context, day * 100, occurred)
        await add_mall_source(db_session, context, day * 200, occurred)

    report = await ReportService()._build_allocation_section(
        db_session, datetime(2026, 7, 1), datetime(2026, 8, 1)
    )
    assert report["summary"]["总记录数"] == 32
    assert (
        report["details"][0]["消费金额(元)"]
        == f"{sum(day * 300 for day in range(1, 17)) / 100:.2f}"
    )


@pytest.mark.asyncio
async def test_mall_only_month_and_later_attribution_keep_original_payment_period(
    client: AsyncClient, db_session: AsyncSession
):
    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 31, 16), attributed=False
    )
    headers = _buyer_headers(context["personUserId"])
    assert source.business_period == "2026-08"  # 16:00 UTC is midnight in Beijing.

    before = (
        await client.get("/api/v1/contributions/overview?month=2026-08", headers=headers)
    ).json()["data"]
    assert before["monthlyAmountCent"] == 0

    source.status = "assigned"
    source.attributed_distributor_id = context["distributorId"]
    source.trade_org_id = context["orgId"]
    source.customer_id = context["customerId"]
    await db_session.flush()

    after = (
        await client.get("/api/v1/contributions/overview?month=2026-08", headers=headers)
    ).json()["data"]
    assert after["monthlyAmountCent"] == 300000
    july_after = (
        await client.get("/api/v1/contributions/overview?month=2026-07", headers=headers)
    ).json()["data"]
    assert july_after["monthlyAmountCent"] == 0
    assert source.business_period == "2026-08"
