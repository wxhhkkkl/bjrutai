"""The aftersale API is owner-scoped and separates review from refund success."""

import pytest

from tests.conftest import auth_header, make_access_token, seed_user
from tests.contract.test_admin_mall_orders import admin
from tests.unit.test_mall_aftersale_service import paid_order


async def keep_manual_review(db, order):
    """Virtual goods stay under merchant review even before shipment."""
    order.policy_snapshot = {**(order.policy_snapshot or {}), "deliveryMethod": "virtual"}
    await db.flush()


@pytest.mark.asyncio
async def test_buyer_submission_is_idempotent_private_and_uses_server_amounts(
    client, db_session, monkeypatch
):
    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    await keep_manual_review(db_session, order)
    headers = {
        **auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
        "Idempotency-Key": "contract-aftersale-submit-001",
    }
    url = "/api/v1/mall/aftersales"
    body = {
        "orderId": str(order.id),
        "expectedOrderVersion": order.version,
        "method": "refund_only",
        "items": [{"orderItemId": str(items[1].id), "quantity": 1}],
        "reason": "商品与页面描述不一致",
        "description": "情况请联系13800138000",
    }

    first = await client.post(url, headers=headers, json=body)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["status"] == "submitted" and data["goodsRefundCent"] == 5000
    assert data["freightRefundCent"] == 0 and data["items"][0]["quantity"] == 1
    assert "13800138000" not in first.text
    assert first.headers["cache-control"] == "no-store"

    replay = await client.post(url, headers=headers, json=body)
    assert replay.json()["data"]["id"] == data["id"]
    assert (
        await client.post(url, headers=headers, json={**body, "reason": "另一个原因"})
    ).status_code == 409
    page = await client.get("/api/v1/mall/aftersales", headers=headers)
    assert page.json()["data"]["total"] == 1
    assert page.json()["data"]["items"][0]["id"] == data["id"]

    other_id = await seed_user(db_session, user_type="personal", openid="aftersale-other-buyer")
    await db_session.commit()
    other = auth_header(make_access_token(user_id=other_id, user_type="personal"))
    assert (
        await client.get(f"/api/v1/mall/aftersales/{data['id']}", headers=other)
    ).status_code == 404


@pytest.mark.asyncio
async def test_admin_decision_needs_review_permission_and_rejection_releases_hold(
    client, db_session, monkeypatch
):
    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    await keep_manual_review(db_session, order)
    buyer_headers = {
        **auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
        "Idempotency-Key": "contract-aftersale-admin-create-001",
    }
    created = await client.post(
        "/api/v1/mall/aftersales",
        headers=buyer_headers,
        json={
            "orderId": str(order.id),
            "expectedOrderVersion": order.version,
            "method": "refund_only",
            "items": [{"orderItemId": str(items[1].id), "quantity": 1}],
            "reason": "收到商品有问题",
        },
    )
    assert created.status_code == 200, created.text
    aftersale_id = created.json()["data"]["id"]

    _, _, read_only = await admin(db_session, ["mall.aftersales.read"])
    read_only["Idempotency-Key"] = "contract-aftersale-denied-001"
    body = {
        "expectedVersion": created.json()["data"]["version"],
        "decision": "reject",
        "reason": "请补充商品照片",
    }
    denied = await client.post(
        f"/api/v1/admin/mall/aftersales/{aftersale_id}/decision",
        headers=read_only,
        json=body,
    )
    assert denied.status_code == 403

    _, _, reviewer = await admin(db_session, ["mall.aftersales.review"])
    reviewer["Idempotency-Key"] = "contract-aftersale-reject-001"
    decided = await client.post(
        f"/api/v1/admin/mall/aftersales/{aftersale_id}/decision",
        headers=reviewer,
        json=body,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["data"]["status"] == "rejected"
    assert order.refund_reserved_cent == 0


@pytest.mark.asyncio
async def test_finance_queues_original_channel_refund_without_claiming_success(
    client, db_session, monkeypatch
):
    from src.models.mall_finance import MallPayment

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    await keep_manual_review(db_session, order)
    buyer_headers = {
        **auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
        "Idempotency-Key": "contract-refund-ready-create-001",
    }
    created = await client.post(
        "/api/v1/mall/aftersales",
        headers=buyer_headers,
        json={
            "orderId": str(order.id),
            "expectedOrderVersion": order.version,
            "method": "refund_only",
            "items": [{"orderItemId": str(items[1].id), "quantity": 1}],
            "reason": "商品申请退款",
        },
    )
    assert created.status_code == 200, created.text
    aftersale_id = created.json()["data"]["id"]
    _, _, finance_headers = await admin(
        db_session, ["mall.aftersales.review", "mall.refunds.execute"]
    )
    finance_headers["Idempotency-Key"] = "contract-refund-approve-001"
    approved = await client.post(
        f"/api/v1/admin/mall/aftersales/{aftersale_id}/decision",
        headers=finance_headers,
        json={
            "expectedVersion": created.json()["data"]["version"],
            "decision": "approve",
            "reason": "订单及金额已复核",
        },
    )
    assert approved.status_code == 200, approved.text
    finance_headers["Idempotency-Key"] = "contract-refund-execute-001"
    queued = await client.post(
        f"/api/v1/admin/mall/aftersales/{aftersale_id}/execute-refund",
        headers=finance_headers,
        json={"expectedVersion": approved.json()["data"]["version"]},
    )
    assert queued.status_code == 200, queued.text
    data = queued.json()["data"]
    assert data["status"] == "prepared" and data["totalCent"] == 5000
    assert data["paymentId"] == str(order.active_payment_id)
    assert data["outRefundNo"].startswith("R")
    assert data["channelRefundId"] is None and data["confirmedAt"] is None
    assert order.refund_reserved_cent == 5000 and order.refunded_goods_cent == 0
    assert (await db_session.get(MallPayment, order.active_payment_id)).status == "succeeded"


@pytest.mark.asyncio
async def test_admin_aftersale_list_filters_by_status(client, db_session, monkeypatch):
    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    await keep_manual_review(db_session, order)
    buyer_headers = {
        **auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
        "Idempotency-Key": "contract-aftersale-filter-create-001",
    }
    created = await client.post(
        "/api/v1/mall/aftersales",
        headers=buyer_headers,
        json={
            "orderId": str(order.id),
            "expectedOrderVersion": order.version,
            "method": "refund_only",
            "items": [{"orderItemId": str(items[1].id), "quantity": 1}],
            "reason": "状态筛选用例",
        },
    )
    assert created.status_code == 200, created.text
    _, _, reader = await admin(db_session, ["mall.aftersales.read"])
    submitted = await client.get("/api/v1/admin/mall/aftersales?status=submitted", headers=reader)
    disputed = await client.get("/api/v1/admin/mall/aftersales?status=disputed", headers=reader)
    assert submitted.status_code == 200 and submitted.json()["data"]["total"] == 1
    assert disputed.status_code == 200 and disputed.json()["data"]["total"] == 0
