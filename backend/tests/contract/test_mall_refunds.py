"""Refund ledger and finance actions only expose stable, permissioned identities."""

import pytest
from sqlalchemy import func, select

from src.models.mall_finance import MallRefund
from src.models.mall_operations import MallJob
from tests.conftest import auth_header, make_access_token
from tests.unit.test_mall_aftersale_service import admin_actor
from tests.unit.test_mall_refund_service import refund_ready


@pytest.mark.asyncio
async def test_finance_refund_list_detail_query_and_retry_reuse_one_refund_identity(
    client, db_session, monkeypatch
):
    _, _, aftersale, _, _, _ = await refund_ready(db_session, monkeypatch)
    finance = await admin_actor(
        db_session, ["mall.refunds.read", "mall.refunds.query", "mall.refunds.execute"]
    )
    headers = auth_header(make_access_token(user_id=finance.actor_id, user_type="admin"))
    headers["Idempotency-Key"] = "contract-admin-refund-execute-001"
    created = await client.post(
        f"/api/v1/admin/mall/aftersales/{aftersale.id}/execute-refund",
        headers=headers,
        json={"expectedVersion": aftersale.version},
    )
    assert created.status_code == 200, created.text
    refund = created.json()["data"]
    assert refund["status"] == "prepared" and refund["confirmedAt"] is None

    listed = await client.get("/api/v1/admin/mall/refunds?status=prepared", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["outRefundNo"] == refund["outRefundNo"]
    detail = await client.get(f"/api/v1/admin/mall/refunds/{refund['id']}", headers=headers)
    assert detail.status_code == 200 and detail.json()["data"]["id"] == refund["id"]

    headers["Idempotency-Key"] = "contract-admin-refund-query-001"
    query_body = {"expectedVersion": refund["version"]}
    queued_query = await client.post(
        f"/api/v1/admin/mall/refunds/{refund['id']}/query",
        headers=headers,
        json=query_body,
    )
    assert queued_query.status_code == 202, queued_query.text
    query_result = queued_query.json()["data"]
    assert query_result["status"] == "pending"
    assert query_result["entityId"] == refund["id"]
    replay_query = await client.post(
        f"/api/v1/admin/mall/refunds/{refund['id']}/query",
        headers=headers,
        json=query_body,
    )
    assert replay_query.json()["data"]["jobId"] == query_result["jobId"]

    headers["Idempotency-Key"] = "contract-admin-refund-retry-001"
    retry_body = {"expectedVersion": refund["version"], "reason": "渠道状态待复核"}
    queued_retry = await client.post(
        f"/api/v1/admin/mall/refunds/{refund['id']}/retry",
        headers=headers,
        json=retry_body,
    )
    assert queued_retry.status_code == 202, queued_retry.text
    retry_result = queued_retry.json()["data"]
    assert retry_result["entityId"] == refund["id"]
    assert retry_result["jobId"] != query_result["jobId"]
    replay_retry = await client.post(
        f"/api/v1/admin/mall/refunds/{refund['id']}/retry",
        headers=headers,
        json=retry_body,
    )
    assert replay_retry.json()["data"]["jobId"] == retry_result["jobId"]
    assert await db_session.scalar(select(func.count()).select_from(MallRefund)) == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(MallJob.kind == "mall_refund_execute", MallJob.entity_id == int(refund["id"]))
        )
        == 1
    )


@pytest.mark.asyncio
async def test_buyer_withdraw_return_shipment_and_admin_receipt_are_contract_complete(
    client, db_session, monkeypatch
):
    from src.models.mall_operations import MallSettings
    from tests.unit.test_mall_aftersale_service import paid_order

    buyer, order, skus, items = await paid_order(db_session, monkeypatch)
    settings = await db_session.get(MallSettings, 1)
    settings.return_address_snapshot = {
        "recipientName": "商城退货收件人",
        "addressLine": "北京虚构退货地址",
    }
    await db_session.commit()
    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))
    buyer_headers["Idempotency-Key"] = "contract-aftersale-withdraw-create-001"
    withdrawable = await client.post(
        "/api/v1/mall/aftersales",
        headers=buyer_headers,
        json={
            "orderId": str(order.id),
            "expectedOrderVersion": order.version,
            "method": "return_refund",
            "items": [{"orderItemId": str(items[1].id), "quantity": 1}],
            "reason": "暂不退货",
        },
    )
    assert withdrawable.status_code == 200, withdrawable.text
    buyer_headers["Idempotency-Key"] = "contract-aftersale-withdraw-001"
    withdrawn = await client.post(
        f"/api/v1/mall/aftersales/{withdrawable.json()['data']['id']}/withdraw",
        headers=buyer_headers,
        json={
            "expectedVersion": withdrawable.json()["data"]["version"],
            "reason": "问题已自行解决",
        },
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["data"]["status"] == "withdrawn"
    await db_session.refresh(order)

    buyer_headers["Idempotency-Key"] = "contract-aftersale-return-create-001"
    created = await client.post(
        "/api/v1/mall/aftersales",
        headers=buyer_headers,
        json={
            "orderId": str(order.id),
            "expectedOrderVersion": order.version,
            "method": "return_refund",
            "items": [{"orderItemId": str(items[1].id), "quantity": 1}],
            "reason": "商品需退回验收",
        },
    )
    assert created.status_code == 200, created.text
    aftersale = created.json()["data"]

    reviewer = await admin_actor(db_session, ["mall.aftersales.review", "mall.returns.receive"])
    admin_headers = auth_header(make_access_token(user_id=reviewer.actor_id, user_type="admin"))
    admin_headers["Idempotency-Key"] = "contract-aftersale-return-approve-001"
    approved = await client.post(
        f"/api/v1/admin/mall/aftersales/{aftersale['id']}/decision",
        headers=admin_headers,
        json={
            "expectedVersion": aftersale["version"],
            "decision": "approve",
            "reason": "同意退回验收",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "awaiting_return"
    buyer_detail = await client.get(
        f"/api/v1/mall/aftersales/{aftersale['id']}", headers=buyer_headers
    )
    assert "北京虚构退货地址" in buyer_detail.json()["data"]["returnInstructions"]

    buyer_headers["Idempotency-Key"] = "contract-aftersale-return-waybill-001"
    shipped = await client.post(
        f"/api/v1/mall/aftersales/{aftersale['id']}/return-shipment",
        headers=buyer_headers,
        json={
            "expectedVersion": approved.json()["data"]["version"],
            "courierCode": "yuantong",
            "trackingNo": "YT202611060099",
        },
    )
    assert shipped.status_code == 200, shipped.text
    assert shipped.json()["data"]["status"] == "awaiting_receipt"
    line_id = shipped.json()["data"]["items"][0]["id"]

    admin_headers["Idempotency-Key"] = "contract-aftersale-return-receive-002"
    received = await client.post(
        f"/api/v1/admin/mall/aftersales/{aftersale['id']}/receipt",
        headers=admin_headers,
        json={
            "expectedVersion": shipped.json()["data"]["version"],
            "result": "accepted",
            "sellableItems": [{"aftersaleItemId": line_id, "quantity": 1}],
            "reason": "外观及包装合格，可再次销售",
        },
    )
    assert received.status_code == 200, received.text
    assert received.json()["data"]["status"] == "awaiting_refund"
    assert skus[1].available_qty == 9
