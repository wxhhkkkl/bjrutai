"""Local receipt is independent from WeChat platform receipt confirmation."""

import pytest
from sqlalchemy import select

from src.core.config import get_settings
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
    _, _, admin_headers = await admin(db_session, ["mall.orders.read", "mall.shipments.write"])
    admin_headers["Idempotency-Key"] = "shipping-local-platform-separation-001"

    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
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
        make_access_token(user_id=buyer.actor_id, user_type="personal")
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
