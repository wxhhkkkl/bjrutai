import pytest
from sqlalchemy import func, select

from src.models.mall_finance import MallPayment
from src.models.mall_operations import MallJob
from tests.conftest import auth_header, make_access_token, seed_user
from tests.unit.test_mall_payment_service import payable


@pytest.mark.asyncio
async def test_owned_prepay_delivery_is_fresh_private_and_expires(client, db_session, monkeypatch):
    from datetime import timedelta

    from src.api.v1 import mall_payments
    from src.models.mall_base import utc_now
    from tests.unit.test_mall_payment_execution import vault
    from tests.unit.test_wechat_pay_client import make_client

    # Invocation generation is local; the client's transport is never touched.
    gateway = make_client(lambda _: None)
    store = vault()
    actor, order, _, payment = await payable(db_session, monkeypatch)
    payment.prepay_ciphertext = store.seal(payment, "synthetic-owned-token")
    payment.status = "pending"
    await db_session.commit()
    monkeypatch.setattr(mall_payments, "payment_runtime", lambda _payment: (gateway, store))
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "payment-delivery-replay-001"
    url = f"/api/v1/mall/orders/{order.id}/payment"
    body = {"expectedVersion": order.version}
    first = await client.post(url, headers=headers, json=body)
    second = await client.post(url, headers=headers, json=body)
    a, b = first.json()["data"], second.json()["data"]
    assert first.status_code == second.status_code == 200
    assert a["canInvoke"] and b["canInvoke"]
    assert a["invokeParams"]["nonceStr"] != b["invokeParams"]["nonceStr"]
    assert a["invokeParams"]["package"] == "prepay_id=synthetic-owned-token"
    assert "prepay_ciphertext" not in first.text and "payment-test-openid" not in first.text
    assert first.headers["cache-control"] == "no-store"
    assert "invokeParams" not in (await client.get(url, headers=headers)).text
    order.expires_at = payment.expires_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    expired = (await client.post(url, headers=headers, json=body)).json()["data"]
    assert expired["canInvoke"] is False and expired["invokeParams"] is None


@pytest.mark.asyncio
async def test_owned_payment_prepare_replay_and_safe_read_do_not_call_gateway(
    client, db_session, monkeypatch
):
    actor, order, _, payment = await payable(db_session, monkeypatch)
    alien_id = await seed_user(db_session, user_type="personal", openid="other-payment-buyer")
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "http-payment-prepare-001"
    url = f"/api/v1/mall/orders/{order.id}/payment"
    response = await client.post(url, headers=headers, json={"expectedVersion": order.version})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()["data"]
    assert (
        body["payment"]["id"] == str(payment.id)
        and not body["canInvoke"]
        and body["invokeParams"] is None
    )
    assert (
        "appid" not in response.text
        and "mchid" not in response.text
        and "prepay" not in response.text
    )
    assert (
        await client.post(url, headers=headers, json={"expectedVersion": order.version})
    ).json()["data"]["payment"]["id"] == str(payment.id)
    assert (
        await client.post(
            url, headers=headers, json={"expectedVersion": order.version, "amountCent": 1}
        )
    ).status_code == 422
    before = await db_session.scalar(select(func.count()).select_from(MallJob))
    assert (await client.get(url, headers=headers)).json()["data"]["status"] == "creating"
    assert before == await db_session.scalar(select(func.count()).select_from(MallJob))
    other = auth_header(make_access_token(user_id=alien_id, user_type="personal"))
    other["Idempotency-Key"] = "http-payment-alien-001"
    assert (await client.get(url, headers=other)).status_code == 404
    assert (
        await client.post(url, headers=other, json={"expectedVersion": order.version})
    ).status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(MallPayment)) == 1
