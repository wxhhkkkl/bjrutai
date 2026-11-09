"""Selection -> private address -> trustworthy quote, with all outbounds off."""

import pytest
from sqlalchemy import func, select

from src.core.config import get_settings
from src.models.mall_consumption import MallConsumption
from src.models.mall_trade import MallOrder
from tests.conftest import auth_header, make_access_token
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed


@pytest.mark.asyncio
async def test_selection_to_quote_is_private_and_does_not_create_inventory_or_performance(
    client, db_session, monkeypatch
):
    actor, settings, _, skus = await checkout_seed(db_session)
    settings.freight_mode = "free"
    await db_session.commit()
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "selection-cart-intent-001"
    cart = await client.post(
        "/api/v1/mall/cart", headers=headers, json={"skuId": str(skus[0].id), "quantity": 2}
    )
    assert cart.status_code == 200 and cart.json()["data"]["valid"]
    headers["Idempotency-Key"] = "selection-address-intent-001"
    address = await client.post(
        "/api/v1/mall/addresses", headers=headers, json={**ADDRESS, "isDefault": True}
    )
    assert address.status_code == 200
    address_id = address.json()["data"]["id"]
    body = {"addressId": address_id, "items": [{"skuId": str(skus[0].id), "quantity": 2}]}
    quote = await client.post("/api/v1/mall/checkout/quote", headers=headers, json=body)
    assert quote.status_code == 200
    assert quote.json()["data"]["freightAmountCent"] == 0
    assert quote.json()["data"]["payableAmountCent"] == 20000
    assert ADDRESS["phone"] not in quote.text and ADDRESS["addressLine"] not in quote.text
    # A changed forbidden region is not silently charged or accepted.
    settings.blocked_regions = ["110000"]
    settings.version += 1
    await db_session.commit()
    assert (
        await client.post("/api/v1/mall/checkout/quote", headers=headers, json=body)
    ).status_code == 409
    await db_session.refresh(skus[0])
    assert (skus[0].available_qty, skus[0].reserved_qty) == (10, 0)
    assert await db_session.scalar(select(func.count()).select_from(MallOrder)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MallConsumption)) == 0
