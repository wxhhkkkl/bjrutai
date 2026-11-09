"""Buyer address-to-payment flow with synthetic payment verification only."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.core.config import get_settings
from src.models.mall_base import utc_now
from src.models.mall_catalog import MallSku, MallStockMovement
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment
from src.models.mall_trade import MallOrder
from src.models.user import User
from src.services.mall_payment_service import apply_verified_payment
from tests.conftest import auth_header, make_access_token
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed
from tests.unit.test_mall_payment_service import success


@pytest.mark.asyncio
async def test_address_to_payment_creates_one_order_and_one_consumption_source(
    client, db_session, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_environment", "test")
    monkeypatch.setattr(settings, "mall_enabled", True)
    monkeypatch.setattr(settings, "mall_purchase_enabled", True)
    monkeypatch.setattr(settings, "mall_gateway_mode", "test")
    monkeypatch.setattr(settings, "mall_gateway_outbound_enabled", False)
    monkeypatch.setattr(settings, "wechat_app_id", "wx-test")
    monkeypatch.setattr(settings, "mall_wechat_mchid", "test-merchant", raising=False)

    actor, _, _, skus = await checkout_seed(db_session)
    original_sku_ids = [sku.id for sku in skus]
    buyer = await db_session.get(User, actor.actor_id)
    buyer.openid = "payment-test-openid"
    await db_session.commit()

    identity = uuid4().hex
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    address_response = await client.post(
        "/api/v1/mall/addresses",
        headers={**headers, "Idempotency-Key": f"purchase-address-{identity}"},
        json=ADDRESS,
    )
    assert address_response.status_code == 200, address_response.text
    address_id = address_response.json()["data"]["id"]

    quote_response = await client.post(
        "/api/v1/mall/checkout/quote",
        headers=headers,
        json={
            "addressId": address_id,
            "items": [
                {"skuId": str(sku_id), "quantity": quantity}
                for sku_id, quantity in zip(original_sku_ids, (1, 2), strict=True)
            ],
        },
    )
    assert quote_response.status_code == 200, quote_response.text
    quote = quote_response.json()["data"]

    order_response = await client.post(
        "/api/v1/mall/orders",
        headers={**headers, "Idempotency-Key": f"purchase-order-{identity}"},
        json={
            "quoteToken": quote["quoteToken"],
            "consentVersion": "mall-test-v1",
            "consentConfirmed": True,
        },
    )
    assert order_response.status_code == 200, order_response.text
    order_view = order_response.json()["data"]
    order_id = int(order_view["id"])
    assert order_view["payableAmountCent"] == 21000  # 商品200 + 整单一次运费10。

    order = await db_session.get(MallOrder, order_id)
    payment_url = f"/api/v1/mall/orders/{order_id}/payment"
    payment_headers = {**headers, "Idempotency-Key": f"purchase-payment-{identity}"}
    payment_body = {"expectedVersion": order.version}
    first_payment = await client.post(payment_url, headers=payment_headers, json=payment_body)
    replay_payment = await client.post(payment_url, headers=payment_headers, json=payment_body)
    assert first_payment.status_code == replay_payment.status_code == 200
    first = first_payment.json()["data"]
    replay = replay_payment.json()["data"]
    assert first["payment"]["id"] == replay["payment"]["id"]
    assert first["payment"]["outTradeNo"] == replay["payment"]["outTradeNo"]
    assert first["payment"]["status"] == "creating"
    assert first["canInvoke"] is False and first["invokeParams"] is None
    assert await db_session.scalar(select(func.count()).select_from(MallPayment)) == 1

    payment = await db_session.get(MallPayment, int(first["payment"]["id"]))
    paid_fact = replace(
        success(payment, order, paid_at=utc_now()),
        transaction_id=f"SYN-PURCHASE-{identity[:20]}",
    )
    for _ in range(20):
        await apply_verified_payment(db_session, payment.id, paid_fact)
    await db_session.commit()

    await db_session.refresh(order)
    paid_status = await client.get(payment_url, headers=headers)
    order_status = await client.get(f"/api/v1/mall/orders/{order_id}", headers=headers)
    assert paid_status.status_code == order_status.status_code == 200
    assert paid_status.json()["data"]["status"] == "succeeded"
    assert order_status.json()["data"]["status"] == "pending_shipment"
    assert order_status.json()["data"]["paidAmountCent"] == order.payable_amount_cent
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallPayment).where(MallPayment.order_id == order_id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallConsumption)
            .where(MallConsumption.order_id == order_id)
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(MallStockMovement.kind == "sale")
        )
        == 2
    )
    persisted_skus = (
        await db_session.scalars(select(MallSku).where(MallSku.id.in_(original_sku_ids)))
    ).all()
    assert sorted((sku.available_qty, sku.reserved_qty) for sku in persisted_skus) == [
        (8, 0),
        (9, 0),
    ]
    assert settings.mall_gateway_mode == "test" and not settings.mall_gateway_outbound_enabled
    assert "test-merchant" not in paid_status.text and "payment-test-openid" not in paid_status.text
