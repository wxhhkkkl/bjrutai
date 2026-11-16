"""Local shipment and receipt facts are versioned, idempotent, and order scoped."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from src.models.audit import AuditLog
from src.models.mall_base import utc_now
from src.models.mall_operations import MallCommand, MallJob
from src.models.mall_trade import MallAftersale, MallOrder, MallShipment
from tests.conftest import TestAsyncSession, auth_header, make_access_token, seed_user
from tests.contract.test_admin_mall_orders import admin
from tests.unit.test_mall_order_actions import unattempted
from tests.unit.test_mall_payment_service import payable, success


async def paid_order(db, monkeypatch):
    from src.services.mall_payment_service import apply_verified_payment

    actor, order, skus, payment = await payable(db, monkeypatch)
    await apply_verified_payment(db, payment.id, success(payment, order))
    await db.commit()
    await db.refresh(order)
    return actor, order, skus


@pytest.mark.asyncio
async def test_dispatch_requires_paid_ready_order_and_creates_one_local_package(
    client, db_session, monkeypatch
):
    actor, order, skus = await paid_order(db_session, monkeypatch)
    initial_version = order.version
    admin_id, _, headers = await admin(
        db_session,
        ["mall.orders.read", "mall.orders.write", "mall.shipments.write"],
    )
    headers["Idempotency-Key"] = "contract-local-ship-001"
    url = f"/api/v1/admin/mall/orders/{order.id}/ship"
    body = {
        "expectedVersion": initial_version,
        "courierCode": "yuantong",
        "trackingNo": "YT202611060001",
    }

    first = await client.post(url, headers=headers, json=body)
    assert first.status_code == 200, first.text
    package = first.json()["data"]
    assert package["courierCode"] == "yuantong"
    assert package["trackingNo"] == "YT202611060001"
    assert package["platformSyncStatus"] == "not_required"
    assert package["autoReceiveAt"]
    assert "13800001234" not in first.text and "虚构路" not in first.text

    replay = await client.post(url, headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["data"]["id"] == package["id"]
    order_response = await client.get(
        f"/api/v1/admin/mall/orders/{order.id}",
        headers={k: v for k, v in headers.items() if k != "Idempotency-Key"},
    )
    assert order_response.json()["data"]["status"] == "pending_receipt"
    assert "correctMallTracking" in order_response.json()["data"]["availableActions"]
    assert "shipMallOrder" not in order_response.json()["data"]["availableActions"]
    assert "13800001234" not in order_response.text
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallShipment).where(MallShipment.order_id == order.id)
        )
        == 1
    )
    assert (await db_session.get(MallOrder, order.id)).version == initial_version + 1
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_order_auto_receive",
            MallJob.entity_id == package["id"],
        )
    )
    assert job is not None and job.entity_version == package["version"]
    event = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "mall_admin_order_shipped")
    )
    assert event.user_id is None and event.detail["adminAccountId"] == str(admin_id)


@pytest.mark.asyncio
async def test_dispatch_is_rejected_when_unpaid_and_write_permission_is_scoped(
    client, db_session, monkeypatch
):
    _, _, _, _, order = await unattempted(db_session, monkeypatch)
    order_id = order.id
    _, _, write_only_orders = await admin(db_session, ["mall.orders.write"])
    url = f"/api/v1/admin/mall/orders/{order_id}/ship"
    data = {"expectedVersion": order.version, "courierCode": "yuantong", "trackingNo": "YT2026"}
    assert (await client.post(url, headers=write_only_orders, json=data)).status_code == 403

    _, _, shipping_admin = await admin(db_session, ["mall.shipments.write"])
    shipping_admin["Idempotency-Key"] = "contract-unpaid-ship-001"
    response = await client.post(url, headers=shipping_admin, json=data)
    assert response.status_code == 409
    assert "13800001234" not in response.text and "虚构路" not in response.text
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallShipment).where(MallShipment.order_id == order_id)
        )
        == 0
    )
    commands = (
        await db_session.scalars(
            select(MallCommand).where(
                MallCommand.action == "shipMallOrder",
                MallCommand.key == "contract-unpaid-ship-001",
            )
        )
    ).all()
    assert not commands, [(row.actor_type, row.status, row.entity_id) for row in commands]


@pytest.mark.asyncio
async def test_tracking_correction_is_separate_versioned_audit_and_does_not_dispatch_again(
    client, db_session, monkeypatch
):
    _, order, _ = await paid_order(db_session, monkeypatch)
    initial_version = order.version
    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    root = f"/api/v1/admin/mall/orders/{order.id}"
    headers["Idempotency-Key"] = "contract-correction-ship-001"
    created = await client.post(
        root + "/ship",
        headers=headers,
        json={
            "expectedVersion": initial_version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060001",
        },
    )
    assert created.status_code == 200, created.text
    package = created.json()["data"]
    await db_session.refresh(order)

    headers["Idempotency-Key"] = "contract-correction-track-001"
    changed = await client.patch(
        f"/api/v1/admin/mall/shipments/{package['id']}",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "shipmentVersion": package["version"],
            "courierCode": "shunfeng",
            "trackingNo": "SF202611060099",
            "reason": "录单时选择了错误承运商",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["trackingNo"] == "SF202611060099"
    assert changed.json()["data"]["version"] == package["version"] + 1
    await db_session.refresh(order)
    assert order.status == "pending_receipt" and order.shipped_at
    assert order.version == initial_version + 2
    events = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "mall_admin_tracking_corrected")
        )
    ).all()
    assert len(events) == 1
    assert "beforeTrackingNo" not in events[0].detail
    assert "afterTrackingNo" not in events[0].detail
    assert "reason" not in events[0].detail
    assert len(events[0].detail["beforeTrackingDigest"]) == 64
    assert len(events[0].detail["afterTrackingDigest"]) == 64
    assert events[0].detail["beforeTrackingDigest"] != events[0].detail["afterTrackingDigest"]
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallShipment).where(MallShipment.order_id == order.id)
        )
        == 1
    )
    old_job = await db_session.scalar(
        select(MallJob).where(MallJob.dedupe_key == f"mall-auto-receive:{package['id']}:1")
    )
    new_job = await db_session.scalar(
        select(MallJob).where(MallJob.dedupe_key == f"mall-auto-receive:{package['id']}:2")
    )
    assert old_job is not None and new_job is not None


@pytest.mark.asyncio
async def test_buyer_confirms_receipt_once_and_private_admin_note_stays_private(
    client, db_session, monkeypatch
):
    actor, order, _ = await paid_order(db_session, monkeypatch)
    initial_version = order.version
    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    headers["Idempotency-Key"] = "contract-receipt-ship-001"
    ship = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=headers,
        json={
            "expectedVersion": initial_version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060001",
        },
    )
    assert ship.status_code == 200, ship.text
    await db_session.refresh(order)
    order.internal_note = "内部核对，不对买家展示"
    await db_session.commit()

    buyer_headers = {
        **auth_header(make_access_token(user_id=actor.actor_id, user_type="personal")),
        "Idempotency-Key": "contract-buyer-confirm-receipt-001",
    }
    url = f"/api/v1/mall/orders/{order.id}/confirm-receipt"
    data = {"expectedVersion": order.version}
    response = await client.post(url, headers=buyer_headers, json=data)
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    assert detail["status"] == "completed" and detail["receivedAt"]
    assert detail["availableActions"] == []
    assert "internalNote" not in detail and "内部核对" not in response.text
    replay = await client.post(url, headers=buyer_headers, json=data)
    assert replay.status_code == 200 and replay.json()["data"]["version"] == detail["version"]

    other_user_id = await seed_user(db_session, user_type="personal", openid="receipt-alien-test")
    await db_session.commit()
    other_user_headers = {
        **auth_header(make_access_token(user_id=other_user_id, user_type="personal")),
        "Idempotency-Key": "contract-other-confirm-receipt-001",
    }
    assert (await client.post(url, headers=other_user_headers, json=data)).status_code == 404


@pytest.mark.asyncio
async def test_auto_receipt_waits_for_deadline_and_defers_while_aftersale_is_open(
    client, db_session, monkeypatch
):
    from src.services.mall_receipt_service import fulfillment_handlers
    from src.tasks.mall_tasks import run_mall_worker_once

    actor, order, _ = await paid_order(db_session, monkeypatch)
    _, _, headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    headers["Idempotency-Key"] = "contract-auto-receive-ship-001"
    response = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611060001",
        },
    )
    assert response.status_code == 200, response.text
    package_id = int(response.json()["data"]["id"])
    shipment = await db_session.get(MallShipment, package_id)
    job = await db_session.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_order_auto_receive", MallJob.entity_id == package_id
        )
    )
    shipment.auto_receive_at = utc_now() - timedelta(seconds=1)
    job.next_run_at = utc_now() - timedelta(seconds=1)
    db_session.add(
        MallAftersale(
            aftersale_no="A-auto-receive-" + str(order.id),
            order_id=order.id,
            buyer_user_id=actor.actor_id,
            method="refund_only",
            reason="待处理售后",
        )
    )
    await db_session.commit()

    handlers = fulfillment_handlers(TestAsyncSession)
    assert await run_mall_worker_once(TestAsyncSession, handlers=handlers, enabled=True)
    await db_session.refresh(order)
    await db_session.refresh(job)
    assert order.status == "pending_receipt" and order.received_at is None
    assert job.status == "retry" and job.next_run_at > utc_now()

    aftersale = await db_session.scalar(
        select(MallAftersale).where(MallAftersale.order_id == order.id)
    )
    aftersale.status = "closed"
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    assert await run_mall_worker_once(TestAsyncSession, handlers=handlers, enabled=True)
    await db_session.refresh(order)
    await db_session.refresh(job)
    assert order.status == "completed" and order.received_at is not None
    assert job.status == "done"
