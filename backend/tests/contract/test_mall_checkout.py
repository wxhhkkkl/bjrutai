import json

import pytest
from sqlalchemy import select

from src.models.audit import AuditLog
from src.models.mall_operations import MallCommand
from tests.conftest import auth_header, make_access_token, seed_user
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed


@pytest.mark.asyncio
async def test_order_creation_replay_ownership_and_snapshot_reads(client, db_session, monkeypatch):
    from src.core.config import get_settings
    from src.models.mall_trade import MallAddress

    actor, _, product, skus = await checkout_seed(db_session)
    alien_id = await seed_user(db_session, user_type="personal", openid="other-order-buyer")
    await db_session.commit()
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "order-address-contract-001"
    address = (await client.post("/api/v1/mall/addresses", headers=headers, json=ADDRESS)).json()[
        "data"
    ]
    quote = (
        await client.post(
            "/api/v1/mall/checkout/quote",
            headers=headers,
            json={
                "addressId": address["id"],
                "items": [{"skuId": str(skus[0].id), "quantity": 1}],
            },
        )
    ).json()["data"]
    headers["Idempotency-Key"] = "order-create-contract-001"
    body = {
        "quoteToken": quote["quoteToken"],
        "consentVersion": "mall-test-v1",
        "consentConfirmed": True,
        "buyerNote": "测试备注",
    }
    root = "/api/v1/mall/orders"
    assert (
        await client.post(root, headers=headers, json={**body, "payableAmountCent": 1})
    ).status_code == 422
    created = await client.post(root, headers=headers, json=body)
    assert created.status_code == 200, created.text
    order = created.json()["data"]
    assert order["status"] == "pending_payment" and order["payableAmountCent"] == 11000
    assert created.headers["cache-control"] == "no-store"
    assert ADDRESS["phone"] not in created.text and ADDRESS["addressLine"] not in created.text
    assert (await client.post(root, headers=headers, json=body)).json()["data"]["id"] == order["id"]
    assert (
        await client.post(root, headers=headers, json={**body, "buyerNote": "不同内容"})
    ).status_code == 409
    product.name = "新商品名称"
    saved = await db_session.get(MallAddress, int(address["id"]))
    saved.address_line = "新的虚构地址"
    await db_session.commit()
    detail = await client.get(root + "/" + order["id"], headers=headers)
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["items"][0]["productName"] == "测试谷物" and data["buyerNote"] == "测试备注"
    assert data["shipment"] is None and data["paymentId"] is None
    assert "internalNote" not in data and data["timeline"][0]["action"] == "created"
    assert set(data["availableActions"]) == {"cancelMallOrder", "changeMallOrderAddress"}
    assert (await client.get(root, headers=headers)).json()["data"]["total"] == 1
    alien = auth_header(make_access_token(user_id=alien_id, user_type="personal"))
    assert (await client.get(root + "/" + order["id"], headers=alien)).status_code == 404
    assert (await client.get(root, headers=alien)).json()["data"]["items"] == []

    # An unknown attempt with a missing pointer must not be presented as unpaid.
    from datetime import datetime

    from src.models.mall_finance import MallPayment

    attempt = MallPayment(
        order_id=int(order["id"]),
        out_trade_no="history-without-pointer",
        status="unknown",
        amount_cent=11000,
        appid_snapshot="test-app",
        mchid_snapshot="test-merchant",
        prepay_ciphertext="opaque-test-only",
        expires_at=datetime(2026, 11, 6),
    )
    db_session.add(attempt)
    await db_session.commit()
    detail = await client.get(root + "/" + order["id"], headers=headers)
    assert detail.json()["data"]["paymentStatus"] == "unknown"
    assert detail.json()["data"]["paymentId"] == str(attempt.id)
    assert "opaque-test-only" not in detail.text and "test-merchant" not in detail.text


@pytest.mark.asyncio
async def test_address_private_crud_replay_and_audit_never_persist_response_or_raw_log(
    client, db_session
):
    actor, _, _, _ = await checkout_seed(db_session)
    other = await seed_user(db_session, user_type="personal", openid="checkout-other")
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "address-create-test-001"
    root = "/api/v1/mall/addresses"
    assert (await client.get(root)).status_code == 401
    response = await client.post(root, headers=headers, json=ADDRESS)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    address = response.json()["data"]
    assert address["phoneMasked"] == "138****1234"
    assert ADDRESS["phone"] not in response.text and ADDRESS["addressLine"] not in response.text
    assert (await client.post(root, headers=headers, json=ADDRESS)).json()["data"]["id"] == address[
        "id"
    ]
    assert (
        await client.post(root, headers=headers, json={**ADDRESS, "phone": "13900001234"})
    ).status_code == 409
    headers["Idempotency-Key"] = "address-patch-test-001"
    updated = await client.patch(
        f'{root}/{address["id"]}',
        headers=headers,
        json={"expectedVersion": address["version"], "recipientName": "修改后"},
    )
    assert updated.status_code == 200
    alien = auth_header(make_access_token(user_id=other, user_type="personal"))
    alien["Idempotency-Key"] = "address-alien-test-001"
    assert (
        await client.patch(
            f'{root}/{address["id"]}',
            headers=alien,
            json={"expectedVersion": 2, "recipientName": "越权"},
        )
    ).status_code == 404
    assert (await client.get(root, headers=alien)).json()["data"]["items"] == []
    headers["Idempotency-Key"] = "address-archive-test-001"
    archived = await client.post(
        f'{root}/{address["id"]}/archive', headers=headers, json={"expectedVersion": 2}
    )
    assert archived.status_code == 200 and archived.json()["data"]["status"] == "archived"
    assert (
        await client.post(
            f'{root}/{address["id"]}/archive', headers=headers, json={"expectedVersion": 2}
        )
    ).status_code == 200
    assert (await client.get(root, headers=headers)).json()["data"]["items"] == []
    logs = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action.like("mall_address%")))
    ).all()
    assert logs
    safe = json.dumps([log.detail for log in logs], ensure_ascii=False)
    assert ADDRESS["phone"] not in safe and ADDRESS["addressLine"] not in safe
    commands = (await db_session.scalars(select(MallCommand))).all()
    assert all(len(command.payload_hash) == 64 for command in commands)


@pytest.mark.asyncio
async def test_cart_idempotency_quantity_pagination_and_remove(client, db_session):
    actor, _, _, skus = await checkout_seed(db_session)
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "cart-add-probe-001"
    root = "/api/v1/mall/cart"
    body = {"skuId": str(skus[0].id), "quantity": 2}
    response = await client.post(root, headers=headers, json=body)
    assert response.status_code == 200, response.text
    item = response.json()["data"]
    assert (await client.post(root, headers=headers, json=body)).json()["data"]["quantity"] == 2
    headers["Idempotency-Key"] = "cart-add-probe-002"
    assert (
        await client.post(root, headers=headers, json={"skuId": str(skus[1].id), "quantity": 1})
    ).status_code == 200
    page = (await client.get(root + "?pageSize=1", headers=headers)).json()["data"]
    assert len(page["items"]) == 1 and page["nextCursor"]
    next_page = (
        await client.get(
            root, params={"pageSize": 1, "cursor": page["nextCursor"]}, headers=headers
        )
    ).json()["data"]
    assert page["items"][0]["id"] != next_page["items"][0]["id"]
    headers["Idempotency-Key"] = "cart-patch-probe-001"
    assert (
        await client.patch(
            f'{root}/{item["id"]}', headers=headers, json={"expectedVersion": 1, "quantity": 3}
        )
    ).status_code == 200
    headers["Idempotency-Key"] = "cart-patch-stale-001"
    assert (
        await client.patch(
            f'{root}/{item["id"]}', headers=headers, json={"expectedVersion": 1, "quantity": 4}
        )
    ).status_code == 409
    headers["Idempotency-Key"] = "cart-remove-probe-001"
    removal = {"expectedVersion": 2}
    assert (
        await client.post(f'{root}/{item["id"]}/remove', headers=headers, json=removal)
    ).status_code == 200
    assert (
        await client.post(f'{root}/{item["id"]}/remove', headers=headers, json=removal)
    ).status_code == 200
    await db_session.refresh(skus[0])
    assert skus[0].available_qty == 10 and skus[0].reserved_qty == 0


@pytest.mark.asyncio
async def test_quote_route_rejects_client_price_and_returns_expiring_masked_facts(
    client, db_session, monkeypatch
):
    from src.core.config import get_settings

    actor, _, _, skus = await checkout_seed(db_session)
    await db_session.commit()
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "quote-address-probe-001"
    response = await client.post("/api/v1/mall/addresses", headers=headers, json=ADDRESS)
    assert response.status_code == 200, response.text
    body = {
        "addressId": response.json()["data"]["id"],
        "items": [{"skuId": str(skus[0].id), "quantity": 1}],
    }
    root = "/api/v1/mall/checkout/quote"
    assert (
        await client.post(root, headers=headers, json={**body, "payableAmountCent": 1})
    ).status_code == 422
    quote = await client.post(root, headers=headers, json=body)
    assert quote.status_code == 200, quote.text
    assert quote.json()["data"]["payableAmountCent"] == 11000
    assert quote.headers["cache-control"] == "no-store"
    assert ADDRESS["phone"] not in quote.text and ADDRESS["addressLine"] not in quote.text
