"""Signed fake query -> transaction rollback -> same identity queried again.

This is not an OS crash/restart or a live merchant acceptance test.
"""

import json

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select

from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment
from src.models.mall_trade import MallOrder
from src.models.performance_evidence import PerformancePeriodVersion
from src.services.mall_payment_service import apply_verified_payment
from tests.conftest import auth_header, make_access_token
from tests.unit.test_mall_payment_service import payable
from tests.unit.test_wechat_pay_client import make_client, signed_response


@pytest.mark.asyncio
async def test_verified_query_rollback_then_requery_original_identity(
    client, db_session, monkeypatch
):
    actor, order, _, payment = await payable(db_session, monkeypatch)
    payment_id, order_id, amount, out_trade_no, buyer_id = (
        payment.id,
        order.id,
        payment.amount_cent,
        payment.out_trade_no,
        actor.actor_id,
    )
    keys = tuple(rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(3))
    requests = []

    def respond(request):
        requests.append(str(request.url))
        return signed_response(
            keys[1],
            json.dumps(
                {
                    "appid": "wx-test",
                    "mchid": "test-merchant",
                    "out_trade_no": out_trade_no,
                    "trade_state": "SUCCESS",
                    "transaction_id": "recovery-synthetic-transaction",
                    "success_time": "2026-11-05T00:30:00+08:00",
                    "payer": {"openid": "payment-test-openid"},
                    "amount": {
                        "total": amount,
                        "payer_total": amount,
                        "currency": "CNY",
                        "payer_currency": "CNY",
                    },
                }
            ).encode(),
        )

    gateway = make_client(keys, respond)
    verified = await gateway.query(out_trade_no)
    await apply_verified_payment(db_session, payment_id, verified)
    await db_session.rollback()  # Lost local transaction: channel success remains true.
    assert (await db_session.get(MallPayment, payment_id)).status == "creating"
    assert (await db_session.get(MallOrder, order_id)).paid_amount_cent == 0
    assert await db_session.scalar(select(func.count()).select_from(MallConsumption)) == 0
    # A fresh adapter re-queries the original merchant request, never a new payment.
    gateway = make_client(keys, respond)
    for _ in range(20):
        await apply_verified_payment(db_session, payment_id, await gateway.query(out_trade_no))
    await db_session.commit()
    assert len(set(requests)) == 1 and out_trade_no in requests[0]
    assert await db_session.scalar(select(func.count()).select_from(MallPayment)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MallConsumption)) == 1
    assert (await db_session.get(PerformancePeriodVersion, "2026-11")).revision == 1
    headers = auth_header(make_access_token(user_id=buyer_id, user_type="personal"))
    read = await client.get(f"/api/v1/mall/orders/{order_id}/payment", headers=headers)
    assert read.json()["data"]["status"] == "succeeded"
    assert "test-merchant" not in read.text and "payment-test-openid" not in read.text
    detail = (await client.get(f"/api/v1/mall/orders/{order_id}", headers=headers)).json()["data"]
    assert detail["status"] == "pending_shipment" and detail["paidAmountCent"] == amount
    paid = [event for event in detail["timeline"] if event["action"] == "paid"]
    assert len(paid) == 1 and paid[0]["actorLabel"] == "系统核实"
