"""Permissioned finance reads, channel verification and export contracts."""

import pytest
from sqlalchemy import func, select

from src.models.mall_finance import MallPayment
from src.models.mall_operations import MallJob
from tests.contract.test_admin_mall_orders import admin
from tests.unit.test_mall_payment_service import payable


@pytest.mark.asyncio
async def test_payment_ledger_is_read_scoped_and_channel_query_reuses_unknown_payment(
    client, db_session, monkeypatch
):
    buyer, order, _, payment = await payable(db_session, monkeypatch)
    payment.status = "unknown"
    payment.last_error_code = "gateway_timeout"
    await db_session.commit()

    _, _, reader_headers = await admin(db_session, ["mall.payments.read"])
    listing = await client.get(
        "/api/v1/admin/mall/payments?pageSize=20"
        f"&status=unknown&orderNo={order.order_no}"
        "&fromAt=2000-01-01T00%3A00%3A00Z&toAt=2100-01-01T00%3A00%3A00Z",
        headers=reader_headers,
    )
    assert listing.status_code == 200, listing.text
    listed = next(row for row in listing.json()["data"]["items"] if row["id"] == str(payment.id))
    assert listed["orderId"] == str(order.id)
    assert listed["status"] == "unknown"
    assert listed["confirmedAt"] is None
    assert all(
        field not in listing.text
        for field in ("prepayCiphertext", "appidSnapshot", "mchidSnapshot", "openId")
    )

    detail = await client.get(f"/api/v1/admin/mall/payments/{payment.id}", headers=reader_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["status"] == "unknown"

    reader_headers["Idempotency-Key"] = "finance-read-cannot-query-001"
    denied = await client.post(
        f"/api/v1/admin/mall/payments/{payment.id}/query",
        headers=reader_headers,
        json={"expectedVersion": payment.version},
    )
    assert denied.status_code == 403

    _, _, query_headers = await admin(db_session, ["mall.payments.query"])
    query_headers["Idempotency-Key"] = "finance-channel-query-intent-001"
    body = {"expectedVersion": payment.version}
    first = await client.post(
        f"/api/v1/admin/mall/payments/{payment.id}/query",
        headers=query_headers,
        json=body,
    )
    assert first.status_code == 202, first.text
    assert first.json()["data"]["entityId"] == str(payment.id)
    replay = await client.post(
        f"/api/v1/admin/mall/payments/{payment.id}/query",
        headers=query_headers,
        json=body,
    )
    assert replay.status_code == 202, replay.text
    assert replay.json()["data"]["jobId"] == first.json()["data"]["jobId"]

    assert payment.status == "unknown"  # queued verification is not a channel success fact
    assert await db_session.scalar(select(func.count()).select_from(MallPayment)) == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(MallJob.kind == "mall_payment_query", MallJob.entity_id == payment.id)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_payment_and_refund_exports_need_finance_export_and_replay_with_same_scope(
    client, db_session
):
    _, _, read_headers = await admin(db_session, ["mall.payments.read", "mall.refunds.read"])
    body = {
        "from": "2026-11-06T00:00:00+08:00",
        "to": "2026-11-07T00:00:00+08:00",
        "format": "csv",
    }
    read_headers["Idempotency-Key"] = "finance-export-denied-payment-01"
    denied_payment = await client.post(
        "/api/v1/admin/mall/payments/export", headers=read_headers, json=body
    )
    assert denied_payment.status_code == 403
    read_headers["Idempotency-Key"] = "finance-export-denied-refund-001"
    denied_refund = await client.post(
        "/api/v1/admin/mall/refunds/export", headers=read_headers, json=body
    )
    assert denied_refund.status_code == 403

    _, _, export_headers = await admin(db_session, ["mall.finance.export"])
    export_headers["Idempotency-Key"] = "finance-export-payment-intent-01"
    first = await client.post(
        "/api/v1/admin/mall/payments/export", headers=export_headers, json=body
    )
    assert first.status_code == 202, first.text
    replay = await client.post(
        "/api/v1/admin/mall/payments/export", headers=export_headers, json=body
    )
    assert replay.status_code == 202, replay.text
    assert replay.json()["data"]["jobId"] == first.json()["data"]["jobId"]

    export_request_id = first.json()["data"]["requestId"]
    export_status = await client.get(
        f"/api/v1/admin/mall/finance/exports/{export_request_id}",
        headers=export_headers,
    )
    assert export_status.status_code == 200, export_status.text
    assert export_status.json()["data"]["requestId"] == export_request_id
    assert export_status.json()["data"]["status"] == "pending"

    _, _, other_headers = await admin(db_session, ["mall.finance.export"])
    other_reader = await client.get(
        f"/api/v1/admin/mall/finance/exports/{export_request_id}",
        headers=other_headers,
    )
    assert other_reader.status_code == 404

    export_headers["Idempotency-Key"] = "finance-export-refund-intent-01"
    refund_export = await client.post(
        "/api/v1/admin/mall/refunds/export", headers=export_headers, json=body
    )
    assert refund_export.status_code == 202, refund_export.text

    invalid_range = {**body, "to": body["from"]}
    export_headers["Idempotency-Key"] = "finance-export-empty-range-01"
    rejected = await client.post(
        "/api/v1/admin/mall/payments/export", headers=export_headers, json=invalid_range
    )
    assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_refund_ledger_accepts_status_order_and_time_filters(client, db_session):
    _, _, headers = await admin(db_session, ["mall.refunds.read"])
    response = await client.get(
        "/api/v1/admin/mall/refunds?status=unknown&orderNo=LT-ORDER-404"
        "&fromAt=2000-01-01T00%3A00%3A00Z&toAt=2100-01-01T00%3A00%3A00Z",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == []
