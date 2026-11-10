"""Local receipt is independent from WeChat platform receipt confirmation."""

import pytest
from sqlalchemy import select

from src.core.config import get_settings
from src.models.audit import AuditLog
from src.models.mall_trade import MallShipment
from tests.conftest import auth_header, make_access_token
from tests.contract.test_admin_mall_orders import admin
from tests.contract.test_mall_fulfillment import paid_order


@pytest.mark.asyncio
async def test_buyer_receipt_does_not_forge_wechat_platform_confirmation(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(get_settings(), "app_environment", "test")
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    order_id = order.id
    buyer_id = buyer.actor_id
    _, _, admin_headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    admin_headers["Idempotency-Key"] = "shipping-local-platform-separation-001"

    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order_id}/ship",
        headers=admin_headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611090001",
        },
    )
    assert shipped.status_code == 200, shipped.text
    shipment_id = int(shipped.json()["data"]["id"])
    await db_session.refresh(order)
    shipment = await db_session.scalar(
        select(MallShipment).where(MallShipment.id == shipment_id)
    )
    assert shipment.platform_sync_status == "not_required"
    assert shipment.platform_confirmation_status == "unknown"
    assert shipment.platform_confirmed_at is None

    buyer_headers = auth_header(
        make_access_token(user_id=buyer_id, user_type="personal")
    )
    buyer_headers["Idempotency-Key"] = "buyer-local-receipt-platform-separation-001"
    received = await client.post(
        f"/api/v1/mall/orders/{order.id}/confirm-receipt",
        headers=buyer_headers,
        json={"expectedVersion": order.version},
    )
    assert received.status_code == 200, received.text
    assert received.json()["data"]["status"] == "completed"

    await db_session.refresh(shipment)
    assert shipment.platform_sync_status == "not_required"
    assert shipment.platform_confirmation_status == "unknown"
    assert shipment.platform_confirmed_at is None


@pytest.mark.asyncio
async def test_manual_platform_report_is_audited_and_replay_safe(
    client, db_session, monkeypatch
):
    buyer, order, _ = await paid_order(db_session, monkeypatch)
    order_id = order.id
    buyer_id = buyer.actor_id
    admin_id, _, admin_headers = await admin(
        db_session, ["mall.orders.read", "mall.shipments.write"]
    )
    admin_headers["Idempotency-Key"] = "shipping-manual-report-dispatch-001"
    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order_id}/ship",
        headers=admin_headers,
        json={
            "expectedVersion": order.version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611090002",
        },
    )
    assert shipped.status_code == 200, shipped.text
    shipment = shipped.json()["data"]
    assert shipment["platformReportStatus"] == "pending"
    assert shipment["platformReportedAt"] is None
    shipment_version = shipment["version"]
    report_url = f"/api/v1/admin/mall/shipments/{shipment['id']}/platform-report"
    body = {"expectedVersion": shipment_version}
    admin_headers["Idempotency-Key"] = "shipping-manual-platform-report-001"

    reported = await client.post(report_url, headers=admin_headers, json=body)
    assert reported.status_code == 200, reported.text
    result = reported.json()["data"]
    assert result["platformReportStatus"] == "manual_reported"
    assert result["platformReportedAt"]
    assert result["platformConfirmedAt"] is None
    assert result["version"] == shipment_version

    replay = await client.post(report_url, headers=admin_headers, json=body)
    assert replay.status_code == 200
    assert replay.json()["data"]["platformReportStatus"] == "manual_reported"

    admin_headers["Idempotency-Key"] = "shipping-manual-platform-report-duplicate-001"
    duplicate = await client.post(report_url, headers=admin_headers, json=body)
    assert duplicate.status_code == 409

    event = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "mall_admin_platform_shipment_reported")
    )
    assert event is not None and event.user_id is None
    assert event.detail["adminAccountId"] == str(admin_id)
    assert event.detail["shipmentVersion"] == shipment_version
    assert "trackingNo" not in event.detail
    assert "13800001234" not in str(event.detail)

    buyer_headers = auth_header(
        make_access_token(user_id=buyer_id, user_type="personal")
    )
    buyer_order = await client.get(
        f"/api/v1/mall/orders/{order_id}", headers=buyer_headers
    )
    assert buyer_order.status_code == 200
    buyer_shipment = buyer_order.json()["data"]["shipment"]
    assert buyer_shipment["platformReportStatus"] == "manual_reported"
    assert buyer_shipment["platformConfirmedAt"] is None


@pytest.mark.asyncio
async def test_tracking_correction_resets_manual_platform_report_and_workbench_count(
    client, db_session, monkeypatch
):
    _, order, _ = await paid_order(db_session, monkeypatch)
    order_id = order.id
    order_version = order.version
    _, _, admin_headers = await admin(
        db_session, ["mall.orders.read", "mall.shipments.write"]
    )
    admin_headers["Idempotency-Key"] = "shipping-manual-reset-dispatch-001"
    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order_id}/ship",
        headers=admin_headers,
        json={
            "expectedVersion": order_version,
            "courierCode": "yuantong",
            "trackingNo": "YT202611090003",
        },
    )
    assert shipped.status_code == 200, shipped.text
    shipment = shipped.json()["data"]

    workbench = await client.get(
        "/api/v1/admin/mall/workbench",
        headers={key: value for key, value in admin_headers.items() if key != "Idempotency-Key"},
    )
    assert workbench.status_code == 200, workbench.text
    assert workbench.json()["data"]["pendingPlatformReport"] == 1
    pending_list = await client.get(
        "/api/v1/admin/mall/orders?pendingPlatformReport=true",
        headers={key: value for key, value in admin_headers.items() if key != "Idempotency-Key"},
    )
    assert pending_list.status_code == 200, pending_list.text
    assert pending_list.json()["data"]["total"] == 1

    admin_headers["Idempotency-Key"] = "shipping-manual-reset-report-001"
    report_url = f"/api/v1/admin/mall/shipments/{shipment['id']}/platform-report"
    reported = await client.post(
        report_url,
        headers=admin_headers,
        json={"expectedVersion": shipment["version"]},
    )
    assert reported.status_code == 200, reported.text
    assert reported.json()["data"]["platformReportStatus"] == "manual_reported"
    workbench = await client.get(
        "/api/v1/admin/mall/workbench",
        headers={key: value for key, value in admin_headers.items() if key != "Idempotency-Key"},
    )
    assert workbench.json()["data"]["pendingPlatformReport"] == 0
    registered_list = await client.get(
        "/api/v1/admin/mall/orders?pendingPlatformReport=true",
        headers={key: value for key, value in admin_headers.items() if key != "Idempotency-Key"},
    )
    assert registered_list.status_code == 200
    assert registered_list.json()["data"]["total"] == 0

    detail = await client.get(
        f"/api/v1/admin/mall/orders/{order_id}",
        headers={key: value for key, value in admin_headers.items() if key != "Idempotency-Key"},
    )
    current = detail.json()["data"]
    current_shipment = current["shipment"]
    admin_headers["Idempotency-Key"] = "shipping-manual-reset-correction-001"
    corrected = await client.patch(
        f"/api/v1/admin/mall/shipments/{shipment['id']}",
        headers=admin_headers,
        json={
            "expectedVersion": current["version"],
            "shipmentVersion": current_shipment["version"],
            "courierCode": "zto",
            "trackingNo": "ZTO202611090003",
            "reason": "承运商录入错误",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["data"]["platformReportStatus"] == "pending"
    assert corrected.json()["data"]["platformReportedAt"] is None
    assert corrected.json()["data"]["version"] == shipment["version"] + 1
    admin_headers["Idempotency-Key"] = "shipping-manual-report-stale-version-001"
    stale_report = await client.post(
        report_url,
        headers=admin_headers,
        json={"expectedVersion": shipment["version"]},
    )
    assert stale_report.status_code == 409

    workbench = await client.get(
        "/api/v1/admin/mall/workbench",
        headers={key: value for key, value in admin_headers.items() if key != "Idempotency-Key"},
    )
    assert workbench.status_code == 200, workbench.text
    assert workbench.json()["data"]["pendingPlatformReport"] == 1
