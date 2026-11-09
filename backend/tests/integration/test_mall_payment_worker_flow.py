"""Signed mock-channel timeout -> durable query -> buyer-local confirmation."""

import json
from datetime import timezone

import httpx
import pytest

from src.models.mall_finance import MallPayment
from src.models.mall_trade import MallOrder
from src.services.mall_payment_execution_service import MallPaymentExecutor
from src.tasks.mall_tasks import run_mall_worker_once
from tests.conftest import TestAsyncSession, auth_header, make_access_token
from tests.unit.test_mall_payment_execution import due, vault
from tests.unit.test_mall_payment_service import payable, success
from tests.unit.test_wechat_pay_client import make_client, pay_keys, signed_response


@pytest.mark.asyncio
async def test_signed_worker_recovery_retains_original_id_and_safe_buyer_view(
    db_session, client, monkeypatch
):
    actor, order, _, payment = await payable(db_session, monkeypatch)
    keys = pay_keys.__wrapped__()
    calls = []
    fact = success(payment, order)

    def respond(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            assert json.loads(request.content)["out_trade_no"] == payment.out_trade_no
            raise httpx.ReadTimeout("synthetic lost prepay reply")
        body = json.dumps(
            {
                "appid": fact.appid,
                "mchid": fact.mchid,
                "out_trade_no": fact.out_trade_no,
                "trade_state": "SUCCESS",
                "transaction_id": fact.transaction_id,
                "success_time": fact.paid_at.replace(tzinfo=timezone.utc).isoformat(),
                "amount": {
                    "total": fact.total_cent,
                    "payer_total": fact.payer_total_cent,
                    "currency": "CNY",
                },
                "payer": {"openid": fact.openid},
            }
        ).encode()
        return signed_response(keys[1], body)

    def handlers():
        # Reconstruct adapter and executor; only committed database state survives.
        return {
            "mall_payment_create": MallPaymentExecutor(
                TestAsyncSession,
                lambda _: make_client(keys, respond),
                vault(),
                "https://example.test/notify",
            )
        }

    assert await run_mall_worker_once(TestAsyncSession, handlers=handlers(), enabled=True)
    await db_session.refresh(payment)
    assert payment.status == "unknown"
    await due(db_session)
    assert await run_mall_worker_once(TestAsyncSession, handlers=handlers(), enabled=True)
    async with TestAsyncSession() as fresh:
        assert (await fresh.get(MallPayment, payment.id)).status == "succeeded"
        assert (await fresh.get(MallOrder, order.id)).status == "pending_shipment"
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    status = await client.get(f"/api/v1/mall/orders/{order.id}/payment", headers=headers)
    assert status.json()["data"]["status"] == "succeeded"
    assert "payment-test-openid" not in status.text and "prepay" not in status.text
    assert calls == [
        ("POST", "/v3/pay/transactions/jsapi"),
        ("GET", "/v3/pay/transactions/out-trade-no/" + payment.out_trade_no),
    ]
