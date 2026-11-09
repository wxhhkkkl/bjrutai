"""Fictional fulfillment samples keep local, platform and buyer facts distinct."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from src.core.config import get_settings
from src.models.mall_base import utc_now
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallAftersale, MallOrder, MallOrderItem, MallShipment
from src.tasks.mall_tasks import run_mall_worker_once
from tests.conftest import TestAsyncSession, auth_header, make_access_token
from tests.contract.test_admin_mall_orders import admin
from tests.contract.test_mall_fulfillment import paid_order
from tests.unit.test_mall_order_actions import unattempted


@pytest.mark.asyncio
async def test_paid_fulfillment_keeps_fake_logistics_separate_from_receipt_and_platform(
    client, db_session, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_environment", "test")
    monkeypatch.setattr(settings, "mall_kuaidi100_mode", "fake")
    monkeypatch.setattr(settings, "mall_kuaidi100_outbound_enabled", False)

    blocked_buyer, blocked_order, _ = await paid_order(db_session, monkeypatch)
    blocked_order_id = blocked_order.id
    blocked_order_version = blocked_order.version
    db_session.add(
        MallAftersale(
            aftersale_no=f"A-blocked-ship-{blocked_order_id}",
            order_id=blocked_order_id,
            buyer_user_id=blocked_buyer.actor_id,
            method="refund_only",
            reason="发货前待处理售后",
        )
    )
    await db_session.commit()

    _, _, admin_headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    blocked_headers = {**admin_headers, "Idempotency-Key": "integration-blocked-ship-0001"}
    blocked = await client.post(
        f"/api/v1/admin/mall/orders/{blocked_order_id}/ship",
        headers=blocked_headers,
        json={
            "expectedVersion": blocked_order_version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060101",
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallShipment)
            .where(MallShipment.order_id == blocked_order_id)
        )
        == 0
    )

    aftersale = await db_session.scalar(
        select(MallAftersale).where(MallAftersale.order_id == blocked_order_id)
    )
    aftersale.status = "rejected"
    await db_session.commit()
    buyer = blocked_buyer
    order = await db_session.get(MallOrder, blocked_order_id)
    order_id = blocked_order_id
    order_version = order.version
    root = f"/api/v1/admin/mall/orders/{order_id}"
    order_items = list(
        (
            await db_session.scalars(
                select(MallOrderItem)
                .where(MallOrderItem.order_id == order_id)
                .order_by(MallOrderItem.id)
            )
        ).all()
    )
    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))
    paid_buyer_detail = (
        await client.get(f"/api/v1/mall/orders/{order_id}", headers=buyer_headers)
    ).json()["data"]
    paid_admin_detail = (await client.get(root, headers=admin_headers)).json()["data"]
    for detail in (paid_buyer_detail, paid_admin_detail):
        assert detail["status"] == "pending_shipment"
        assert detail["payableAmountCent"] == order.payable_amount_cent
        assert detail["paymentId"] is not None
        assert detail["shipment"] is None
        assert detail["timeline"] and detail["availableActions"]
    assert "internalNote" not in paid_buyer_detail and "buyer" not in paid_buyer_detail
    assert set(paid_admin_detail["buyer"]) == {"id", "displayName"}
    ship_body = {
        "expectedVersion": order_version,
        "courierCode": "yuantong",
        "trackingNo": "YT202611060102",
    }
    ship_headers = {**admin_headers, "Idempotency-Key": "integration-local-ship-0001"}
    dispatched = await client.post(root + "/ship", headers=ship_headers, json=ship_body)
    assert dispatched.status_code == 200, dispatched.text
    package = dispatched.json()["data"]
    assert package["platformSyncStatus"] == "not_required"
    assert package["platformConfirmedAt"] is None
    replay = await client.post(root + "/ship", headers=ship_headers, json=ship_body)
    assert replay.status_code == 200 and replay.json()["data"]["id"] == package["id"]

    await db_session.refresh(order)
    corrected = await client.patch(
        f"/api/v1/admin/mall/shipments/{package['id']}",
        headers={**admin_headers, "Idempotency-Key": "integration-correct-waybill-0001"},
        json={
            "expectedVersion": order.version,
            "shipmentVersion": package["version"],
            "courierCode": "shunfeng",
            "trackingNo": "SF202611060102",
            "reason": "虚构验收样本中的录单更正",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["data"]["trackingNo"] == "SF202611060102"

    logistics_url = f"/api/v1/mall/orders/{order_id}/logistics"
    pending = await client.get(logistics_url, headers=buyer_headers)
    assert pending.status_code == 200
    assert pending.json()["data"]["queryStatus"] == "pending"
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_logistics_query",
            MallJob.entity_id == int(package["id"]),
            MallJob.entity_version == corrected.json()["data"]["version"],
        )
    )
    assert job is not None
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    from src.services.mall_logistics_service import logistics_handlers

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=logistics_handlers(TestAsyncSession),
        enabled=True,
    )
    fake_snapshot = (await client.get(logistics_url, headers=buyer_headers)).json()["data"]
    assert fake_snapshot["source"] == "fake"
    assert fake_snapshot["queryStatus"] == "available"
    assert fake_snapshot["stateCode"] == "0"
    assert "13800000000" not in str(fake_snapshot["events"])

    detail = (await client.get(f"/api/v1/mall/orders/{order_id}", headers=buyer_headers)).json()[
        "data"
    ]
    assert detail["status"] == "pending_receipt"
    assert detail["shipment"]["trackingNo"] == "SF202611060102"
    assert detail["shipment"]["platformSyncStatus"] == "not_required"
    assert detail["shipment"]["platformConfirmedAt"] is None
    assert "confirmMallReceipt" in detail["availableActions"]
    assert "internalNote" not in detail
    admin_pending_receipt = (await client.get(root, headers=admin_headers)).json()["data"]
    assert admin_pending_receipt["status"] == "pending_receipt"
    assert admin_pending_receipt["shipment"]["trackingNo"] == "SF202611060102"
    assert "correctMallTracking" in admin_pending_receipt["availableActions"]

    received = await client.post(
        f"/api/v1/mall/orders/{order_id}/confirm-receipt",
        headers={**buyer_headers, "Idempotency-Key": "integration-confirm-receipt-0001"},
        json={"expectedVersion": detail["version"]},
    )
    assert received.status_code == 200, received.text
    received_detail = received.json()["data"]
    assert received_detail["status"] == "completed" and received_detail["receivedAt"]
    assert received_detail["shipment"]["platformConfirmedAt"] is None
    assert received_detail["availableActions"] == []
    admin_received = (await client.get(root, headers=admin_headers)).json()["data"]
    assert admin_received["status"] == "completed"
    assert admin_received["receivedAt"] == received_detail["receivedAt"]
    assert admin_received["paymentId"] == received_detail["paymentId"]
    assert admin_received["shipment"]["id"] == received_detail["shipment"]["id"]
    assert admin_received["internalNote"] is None
    aftersale = await client.post(
        "/api/v1/mall/aftersales",
        headers={**buyer_headers, "Idempotency-Key": "integration-received-aftersale-001"},
        json={
            "orderId": str(order_id),
            "expectedOrderVersion": received_detail["version"],
            "method": "refund_only",
            "items": [{"orderItemId": str(order_items[1].id), "quantity": 1}],
            "reason": "收货后15天窗口内申请",
        },
    )
    assert aftersale.status_code == 200, aftersale.text
    assert aftersale.json()["data"]["status"] == "submitted"
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallShipment).where(MallShipment.order_id == order_id)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_order_details_keep_missing_relations_explicit_and_private_notes_role_scoped(
    client, db_session, monkeypatch
):
    buyer, _, _, _, order = await unattempted(db_session, monkeypatch)
    _, _, admin_headers = await admin(
        db_session, ["mall.orders.read", "mall.orders.write", "mall.shipments.write"]
    )
    buyer_headers = auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal"))
    root = f"/api/v1/admin/mall/orders/{order.id}"

    buyer_detail = (
        await client.get(f"/api/v1/mall/orders/{order.id}", headers=buyer_headers)
    ).json()["data"]
    admin_detail = (await client.get(root, headers=admin_headers)).json()["data"]
    for detail in (buyer_detail, admin_detail):
        assert detail["payableAmountCent"] == order.payable_amount_cent
        assert detail["createdAt"]
        assert detail["timeline"]
        assert detail["paymentId"] is None
        assert detail["invoiceRequestId"] is None
        assert detail["consumptionId"] is None
        assert detail["shipment"] is None
        assert detail["aftersaleIds"] == []
    assert "internalNote" not in buyer_detail and "buyer" not in buyer_detail
    assert admin_detail["internalNote"] is None
    assert set(admin_detail["buyer"]) == {"id", "displayName"}
    assert admin_detail["buyer"]["id"] == str(buyer.actor_id)

    admin_headers["Idempotency-Key"] = "integration-private-note-0001"
    noted = await client.patch(
        root + "/note",
        headers=admin_headers,
        json={"expectedVersion": admin_detail["version"], "internalNote": "核对电话13800001234"},
    )
    assert noted.status_code == 200, noted.text
    admin_after_note = (await client.get(root, headers=admin_headers)).json()["data"]
    buyer_after_note = (
        await client.get(f"/api/v1/mall/orders/{order.id}", headers=buyer_headers)
    ).json()["data"]
    assert "13800001234" not in admin_after_note["internalNote"]
    assert "138****1234" in admin_after_note["internalNote"]
    assert "internalNote" not in buyer_after_note
    assert all(event["action"] != "internal_note_updated" for event in buyer_after_note["timeline"])

    admin_headers["Idempotency-Key"] = "integration-close-order-0001"
    closed = await client.post(
        root + "/cancel",
        headers=admin_headers,
        json={"expectedVersion": admin_after_note["version"], "reason": "虚构样本关闭"},
    )
    assert closed.status_code == 202, closed.text
    buyer_closed = (
        await client.get(f"/api/v1/mall/orders/{order.id}", headers=buyer_headers)
    ).json()["data"]
    admin_closed = (await client.get(root, headers=admin_headers)).json()["data"]
    assert buyer_closed["status"] == admin_closed["status"] == "closed"
    assert buyer_closed["closedAt"] and admin_closed["closedAt"]
    assert "核对电话" not in str(buyer_closed["timeline"])
    assert admin_closed["internalNote"] == admin_after_note["internalNote"]


@pytest.mark.asyncio
async def test_auto_receipt_without_aftersale_completes_and_keeps_the_request_window_open(
    client, db_session, monkeypatch
):
    from src.services.mall_receipt_service import fulfillment_handlers

    actor, order, _ = await paid_order(db_session, monkeypatch)
    order_id, order_version = order.id, order.version
    order_items = list(
        (
            await db_session.scalars(
                select(MallOrderItem)
                .where(MallOrderItem.order_id == order_id)
                .order_by(MallOrderItem.id)
            )
        ).all()
    )
    _, _, admin_headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    admin_headers["Idempotency-Key"] = "integration-auto-receipt-ship-001"
    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order_id}/ship",
        headers=admin_headers,
        json={
            "expectedVersion": order_version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060103",
        },
    )
    assert shipped.status_code == 200, shipped.text
    shipment_id = int(shipped.json()["data"]["id"])
    shipment = await db_session.get(MallShipment, shipment_id)
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_order_auto_receive", MallJob.entity_id == shipment_id
        )
    )
    assert shipment.auto_receive_at - shipment.shipped_at == timedelta(days=15)
    assert not (
        await db_session.scalars(select(MallAftersale).where(MallAftersale.order_id == order_id))
    ).all()
    shipment.auto_receive_at = utc_now() - timedelta(seconds=1)
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers=fulfillment_handlers(TestAsyncSession),
        enabled=True,
    )
    buyer_headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    detail = (await client.get(f"/api/v1/mall/orders/{order_id}", headers=buyer_headers)).json()[
        "data"
    ]
    assert detail["status"] == "completed" and detail["receivedAt"]
    request = await client.post(
        "/api/v1/mall/aftersales",
        headers={**buyer_headers, "Idempotency-Key": "integration-auto-received-aftersale-001"},
        json={
            "orderId": str(order_id),
            "expectedOrderVersion": detail["version"],
            "method": "refund_only",
            "items": [{"orderItemId": str(order_items[1].id), "quantity": 1}],
            "reason": "无售后自动收货后的有效期申请",
        },
    )
    assert request.status_code == 200, request.text
    assert request.json()["data"]["status"] == "submitted"
