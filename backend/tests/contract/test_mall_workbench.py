"""Permission scoped workbench counts and failure behavior."""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.mall_base import utc_now
from tests.contract.test_admin_mall_orders import admin
from tests.unit.test_mall_payment_service import payable

WORKBENCH_FIELDS = {
    "pendingShipment",
    "pendingAftersale",
    "pendingReturnReceipt",
    "paymentUnknown",
    "refundAbnormal",
    "unassigned",
    "pendingAdjustment",
    "pendingInvoice",
    "pendingRedInvoice",
    "lowStock",
    "paidTodayCent",
    "refundedTodayCent",
}


@pytest.mark.asyncio
async def test_finance_role_sees_payment_work_without_order_read_permission(
    client, db_session, monkeypatch
):
    _, _, _, payment = await payable(db_session, monkeypatch)
    now = utc_now()
    payment.status = "unknown"
    payment.last_error_code = "gateway_timeout"
    payment.last_query_at = now - timedelta(minutes=11)
    payment.unknown_since = now - timedelta(minutes=11)

    _, _, headers = await admin(db_session, ["mall.payments.read"])
    response = await client.get("/api/v1/admin/mall/workbench", headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert set(data) == WORKBENCH_FIELDS
    assert data["paymentUnknown"] == 1
    assert data["pendingShipment"] == data["pendingAftersale"] == 0
    assert data["pendingInvoice"] == data["lowStock"] == data["unassigned"] == 0
    assert data["paidTodayCent"] == data["refundedTodayCent"] == 0


@pytest.mark.asyncio
async def test_authorized_empty_workbench_returns_explicit_zeroes(client, db_session):
    _, _, headers = await admin(db_session, ["mall.invoices.read"])
    response = await client.get("/api/v1/admin/mall/workbench", headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert set(data) == WORKBENCH_FIELDS
    assert all(value == 0 for value in data.values())

    _, _, unprivileged_headers = await admin(db_session, [])
    denied = await client.get("/api/v1/admin/mall/workbench", headers=unprivileged_headers)
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_workbench_query_failure_is_not_returned_as_an_empty_summary(
    client, db_session, monkeypatch
):
    from src.services import mall_workbench_service

    async def fail_query(*_args, **_kwargs):
        raise RuntimeError("synthetic workbench read failure")

    monkeypatch.setattr(mall_workbench_service, "get_mall_workbench", fail_query)
    _, _, headers = await admin(db_session, ["mall.invoices.read"])
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as safe_client:
        response = await safe_client.get("/api/v1/admin/mall/workbench", headers=headers)

    assert response.status_code >= 500
    assert response.json().get("code") not in (None, 0)
