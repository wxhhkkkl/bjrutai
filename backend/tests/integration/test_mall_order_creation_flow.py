"""Local order flow with no payment call, no funds and no performance entry."""

import pytest
from sqlalchemy import func, select

from src.core.config import get_settings
from src.models.mall_catalog import MallSku
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallOrder
from src.services.mall_order_service import close_never_paid_order
from tests.conftest import auth_header, make_access_token
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed


@pytest.mark.asyncio
async def test_quote_order_snapshot_and_never_paid_close_flow(client, db_session, monkeypatch):
    actor, _, _, skus = await checkout_seed(db_session)
    sku_ids = [row.id for row in skus]
    await db_session.commit()
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "flow-create-address-001"
    address = (await client.post("/api/v1/mall/addresses", headers=headers, json=ADDRESS)).json()[
        "data"
    ]
    quote = (
        await client.post(
            "/api/v1/mall/checkout/quote",
            headers=headers,
            json={
                "addressId": address["id"],
                "items": [{"skuId": str(identity), "quantity": 1} for identity in sku_ids],
            },
        )
    ).json()["data"]
    headers["Idempotency-Key"] = "flow-create-order-001"
    payload = {
        "quoteToken": quote["quoteToken"],
        "consentVersion": "mall-test-v1",
        "consentConfirmed": True,
    }
    response = await client.post("/api/v1/mall/orders", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    order = response.json()["data"]
    assert order["payableAmountCent"] == 16000
    assert (await client.post("/api/v1/mall/orders", headers=headers, json=payload)).json()["data"][
        "id"
    ] == order["id"]
    headers["Idempotency-Key"] = "flow-change-address-001"
    changed = await client.patch(
        f'/api/v1/mall/addresses/{address["id"]}',
        headers=headers,
        json={
            "expectedVersion": address["version"],
            "phone": "13900005678",
            "addressLine": "改后的虚构路",
        },
    )
    assert changed.status_code == 200
    detail = (await client.get(f'/api/v1/mall/orders/{order["id"]}', headers=headers)).json()[
        "data"
    ]
    assert detail["address"]["phoneMasked"] == "138****1234"
    assert "13900005678" not in str(detail) and "改后的虚构路" not in str(detail)
    assert detail["paymentStatus"] == "not_started"
    assert set(detail["availableActions"]) == {"cancelMallOrder", "changeMallOrderAddress"}
    assert await db_session.scalar(select(func.count()).select_from(MallPayment)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MallConsumption)) == 0
    saved = await db_session.get(MallOrder, int(order["id"]))
    job = await db_session.scalar(
        select(MallJob).where(MallJob.kind == "mall_order_expire", MallJob.entity_id == saved.id)
    )
    assert job.next_run_at == saved.expires_at
    # This is the narrow internal no-payment-history service, not a channel close API.
    await close_never_paid_order(db_session, actor, saved.id, expected_version=saved.version)
    await db_session.commit()
    await close_never_paid_order(db_session, actor, saved.id, expected_version=1)
    await db_session.commit()
    detail = (await client.get(f'/api/v1/mall/orders/{order["id"]}', headers=headers)).json()[
        "data"
    ]
    assert detail["status"] == "closed"
    stock = (await db_session.scalars(select(MallSku).where(MallSku.id.in_(sku_ids)))).all()
    assert all((row.available_qty, row.reserved_qty) == (10, 0) for row in stock)
