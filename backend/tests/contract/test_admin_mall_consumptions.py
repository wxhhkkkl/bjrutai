"""Admin read access to mall performance sources uses the existing contribution permission."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_access_token
from tests.mall_consumption_fixtures import add_mall_source, performance_context


def _admin_headers(permissions):
    token = make_access_token(user_id=1, user_type="admin", permissions=permissions)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_mall_consumption_list_merges_cursor_and_masks_order_private_data(
    client: AsyncClient, db_session: AsyncSession
):
    context = await performance_context(db_session)
    first_order, first_source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    second_order, second_source = await add_mall_source(
        db_session, context, 500000, datetime(2026, 7, 16), attributed=True
    )
    headers = _admin_headers(["contributions.read"])

    first = await client.get(
        "/api/v1/admin/mall/consumptions", headers=headers, params={"pageSize": 1}
    )
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    page = first.json()["data"]
    assert page["total"] == 2
    assert page["items"][0]["sourceType"] == "mall"
    assert page["items"][0]["sourceRecordId"] == str(second_source.id)
    assert page["items"][0]["businessPeriod"] == "2026-07"
    assert page["items"][0]["orderId"] == str(second_order.id)
    assert page["nextCursor"]
    assert not {"address", "addressSnapshot", "phone", "phoneMasked"}.intersection(page["items"][0])

    second = await client.get(
        "/api/v1/admin/mall/consumptions",
        headers=headers,
        params={"pageSize": 1, "cursor": page["nextCursor"]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["items"][0]["sourceRecordId"] == str(first_source.id)
    assert second.json()["data"]["items"][0]["orderId"] == str(first_order.id)


@pytest.mark.asyncio
async def test_admin_mall_consumption_list_requires_contributions_read(
    client: AsyncClient, db_session: AsyncSession
):
    response = await client.get(
        "/api/v1/admin/mall/consumptions",
        headers=_admin_headers(["performance.settle"]),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_mall_consumption_list_rejects_invalid_cursor(
    client: AsyncClient, db_session: AsyncSession
):
    response = await client.get(
        "/api/v1/admin/mall/consumptions",
        headers=_admin_headers(["contributions.read"]),
        params={"cursor": "not-a-cursor"},
    )
    assert response.status_code == 400
