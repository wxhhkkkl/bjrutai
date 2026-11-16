"""Recoverable execution with isolated sessions and an entirely fake channel."""

import base64
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from src.integrations.wechat_pay_types import PaymentGatewayError, PrepayResult, VerifiedClose
from src.models.mall_base import utc_now
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment
from src.models.mall_operations import MallJob
from tests.conftest import TestAsyncSession
from tests.unit.test_mall_payment_service import payable, success


def vault():
    from src.services.mall_prepay_service import PrepayVault

    return PrepayVault({"k1": base64.urlsafe_b64encode(b"a" * 32).decode()}, "k1")


class Channel:
    appid, mchid = "wx-test", "test-merchant"

    def __init__(self, payment, order):
        self.payment, self.order = payment, order
        self.calls = []
        self.fact = replace(success(payment, order, paid_at=utc_now()), state="NOTPAY")
        self.error = None
        self.after_io = None
        self.sessions = TestAsyncSession

    async def outbound(self, operation):
        # Every network operation must observe a committed uncertainty marker.
        async with self.sessions() as db:
            row = await db.get(MallPayment, self.payment.id)
            assert row.status == "unknown"
        self.calls.append(operation)
        if self.after_io:
            await self.after_io()
        if self.error:
            raise self.error

    async def prepay(self, **data):
        assert data["out_trade_no"] == self.payment.out_trade_no
        assert data["amount_cent"] == self.payment.amount_cent
        await self.outbound("prepay")
        return PrepayResult("synthetic-private-prepay")

    async def query(self, identity):
        assert identity == self.payment.out_trade_no
        await self.outbound("query")
        return self.fact

    async def close(self, identity):
        assert identity == self.payment.out_trade_no
        await self.outbound("close")
        return VerifiedClose(identity, self.mchid)


async def execute(channel, *, store=None, factory=TestAsyncSession):
    from src.services.mall_payment_execution_service import MallPaymentExecutor
    from src.tasks.mall_tasks import run_mall_worker_once

    handler = MallPaymentExecutor(
        factory, lambda _payment: channel, store or vault(), "https://example.test/notify"
    )
    return await run_mall_worker_once(
        factory, handlers={"mall_payment_create": handler}, enabled=True
    )


async def due(db):
    job = await db.scalar(select(MallJob).where(MallJob.kind == "mall_payment_create"))
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db.commit()
    return job


@pytest.mark.asyncio
async def test_prepay_is_encrypted_polling_is_deferred_and_success_is_atomic(
    db_session, monkeypatch
):
    _, order, _, payment = await payable(db_session, monkeypatch)
    channel = Channel(payment, order)
    assert await execute(channel)
    await db_session.refresh(payment)
    job = await due(db_session)
    assert channel.calls == ["prepay"] and payment.status == "pending"
    assert "synthetic-private-prepay" not in payment.prepay_ciphertext
    assert vault().open(payment) == "synthetic-private-prepay"
    assert job.status == "retry" and job.attempts == 0
    channel.fact = replace(channel.fact, state="SUCCESS")
    assert await execute(channel)
    await db_session.refresh(payment)
    await db_session.refresh(order)
    await db_session.refresh(job)
    assert channel.calls == ["prepay", "query"]
    assert payment.status == "succeeded" and order.status == "pending_shipment"
    assert job.status == "done"
    assert await db_session.scalar(select(func.count()).select_from(MallConsumption)) == 1


@pytest.mark.asyncio
async def test_timeout_rebuilds_executor_and_queries_original_identity_first(
    db_session, monkeypatch
):
    _, order, skus, payment = await payable(db_session, monkeypatch)
    channel = Channel(payment, order)
    channel.error = PaymentGatewayError("transport_result_unknown")
    assert await execute(channel)
    await db_session.refresh(payment)
    assert payment.status == "unknown"
    job = await due(db_session)
    assert job.status == "retry" and job.attempts == 1
    channel.error = None
    channel.fact = replace(channel.fact, state="SUCCESS")
    assert await execute(channel)
    await db_session.refresh(payment)
    await db_session.refresh(skus[0])
    assert channel.calls == ["prepay", "query"] and payment.status == "succeeded"
    assert skus[0].available_qty == 9 and skus[0].reserved_qty == 0


@pytest.mark.asyncio
async def test_expired_payment_query_then_verified_close_releases_once(db_session, monkeypatch):
    _, order, skus, payment = await payable(db_session, monkeypatch)
    order.expires_at = payment.expires_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    channel = Channel(payment, order)
    assert await execute(channel)
    await db_session.refresh(payment)
    await db_session.refresh(order)
    await db_session.refresh(skus[0])
    assert channel.calls == ["query", "close"]
    assert payment.status == order.status == "closed"
    assert skus[0].available_qty == 10 and skus[0].reserved_qty == 0
    assert not await execute(channel)


@pytest.mark.asyncio
async def test_lease_lost_during_io_cannot_publish_prepay(db_session, monkeypatch):
    _, order, _, payment = await payable(db_session, monkeypatch)
    channel = Channel(payment, order)

    async def steal():
        async with TestAsyncSession() as db:
            job = await db.scalar(select(MallJob).where(MallJob.kind == "mall_payment_create"))
            job.lease_owner = "replacement-worker"
            await db.commit()

    channel.after_io = steal
    assert await execute(channel)
    await db_session.refresh(payment)
    assert payment.status == "unknown" and payment.prepay_ciphertext is None


@pytest.mark.asyncio
async def test_changed_merchant_is_rejected_before_outbound(db_session, monkeypatch):
    _, order, _, payment = await payable(db_session, monkeypatch)
    channel = Channel(payment, order)
    channel.mchid = "different-merchant"
    assert await execute(channel)
    await db_session.refresh(payment)
    assert not channel.calls and payment.status == "creating"


@pytest.mark.asyncio
async def test_close_timeout_does_not_release_and_retry_queries_before_close(
    db_session, monkeypatch
):
    _, order, skus, payment = await payable(db_session, monkeypatch)
    order.expires_at = payment.expires_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    channel = Channel(payment, order)
    original_close = channel.close

    async def timeout_close(identity):
        await channel.outbound("close")
        raise PaymentGatewayError("transport_result_unknown")

    channel.close = timeout_close
    await execute(channel)
    await db_session.refresh(payment)
    await db_session.refresh(skus[0])
    assert payment.status == "unknown" and skus[0].reserved_qty == 1
    await due(db_session)
    channel.close = original_close
    await execute(channel)
    await db_session.refresh(skus[0])
    assert channel.calls == ["query", "close", "query", "close"]
    assert skus[0].available_qty == 10 and skus[0].reserved_qty == 0


@pytest.mark.asyncio
async def test_closed_business_order_never_gets_a_new_prepay(db_session, monkeypatch):
    _, order, _, payment = await payable(db_session, monkeypatch)
    order.status, order.closed_at = "closed", utc_now()
    await db_session.commit()
    channel = Channel(payment, order)
    await execute(channel)
    assert channel.calls == ["query", "close"]


@pytest.mark.asyncio
async def test_many_normal_polls_preserve_failure_budget_but_unknown_is_bounded(
    db_session, monkeypatch
):
    _, order, skus, payment = await payable(db_session, monkeypatch)
    channel = Channel(payment, order)
    await execute(channel)
    for _ in range(7):
        job = await due(db_session)
        await execute(channel)
        await db_session.refresh(job)
        assert job.attempts == 0 and job.status == "retry"
    channel.error = PaymentGatewayError("invalid_gateway_signature")
    for _ in range(5):
        job = await due(db_session)
        await execute(channel)
    await db_session.refresh(job)
    await db_session.refresh(skus[0])
    assert job.status == "manual" and job.last_error_code == "handler_failed"
    assert skus[0].reserved_qty == 1


@pytest.mark.asyncio
async def test_long_expired_userpaying_escalates_without_closing(db_session, monkeypatch):
    _, order, skus, payment = await payable(db_session, monkeypatch)
    order.expires_at = payment.expires_at = utc_now() - timedelta(minutes=20)
    await db_session.commit()
    channel = Channel(payment, order)
    channel.fact = replace(channel.fact, state="USERPAYING")
    for _ in range(5):
        await due(db_session)
        await execute(channel)
    job = await db_session.scalar(select(MallJob).where(MallJob.kind == "mall_payment_create"))
    await db_session.refresh(job)
    await db_session.refresh(skus[0])
    assert job.status == "manual" and channel.calls == ["query"] * 5
    assert skus[0].reserved_qty == 1


@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.asyncio
async def test_verified_absence_retries_original_prepay_only_while_valid(
    db_session, monkeypatch, expired
):
    from src.integrations.wechat_pay_types import PaymentNotFoundError

    _, order, skus, payment = await payable(db_session, monkeypatch)
    payment.status = "unknown"
    if expired:
        order.expires_at = payment.expires_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    channel = Channel(payment, order)

    async def absent(identity):
        assert identity == payment.out_trade_no
        await channel.outbound("query")
        raise PaymentNotFoundError()

    channel.query = absent
    await execute(channel)
    await db_session.refresh(payment)
    await db_session.refresh(skus[0])
    assert channel.calls == (["query"] if expired else ["query", "prepay"])
    assert payment.status == ("unknown" if expired else "pending")
    assert skus[0].reserved_qty == 1


@pytest.mark.asyncio
async def test_vault_binds_every_payment_identity_and_supports_key_overlap(db_session, monkeypatch):
    _, _, _, payment = await payable(db_session, monkeypatch)
    store = vault()
    payment.prepay_ciphertext = store.seal(payment, "prepay-secret")
    assert store.open(payment) == "prepay-secret"
    original = payment.amount_cent
    payment.amount_cent += 1
    with pytest.raises(PaymentGatewayError, match="prepay_unavailable"):
        store.open(payment)
    payment.amount_cent = original
    from src.services.mall_prepay_service import PrepayVault

    rotated = PrepayVault(
        {
            "k1": base64.urlsafe_b64encode(b"a" * 32).decode(),
            "k2": base64.urlsafe_b64encode(b"b" * 32).decode(),
        },
        "k2",
    )
    assert rotated.open(payment) == "prepay-secret"
    assert "prepay-secret" not in rotated.seal(payment, "prepay-secret")


@pytest.mark.parametrize(
    "change",
    [
        "id",
        "out_trade_no",
        "appid_snapshot",
        "mchid_snapshot",
        "currency",
        "expires_at",
        "tamper",
        "unknown_key",
    ],
)
@pytest.mark.asyncio
async def test_vault_refuses_copied_corrupt_or_untrusted_tokens(db_session, monkeypatch, change):
    _, _, _, payment = await payable(db_session, monkeypatch)
    store = vault()
    payment.prepay_ciphertext = store.seal(payment, "private-prepay")
    if change == "tamper":
        payment.prepay_ciphertext = payment.prepay_ciphertext[:-8] + "AAAAAAAA"
    elif change == "unknown_key":
        payment.prepay_ciphertext = payment.prepay_ciphertext.replace("v1.k1.", "v1.k2.")
    elif change == "expires_at":
        payment.expires_at += timedelta(seconds=1)
    elif change == "id":
        payment.id += 1
    else:
        setattr(payment, change, getattr(payment, change) + "changed")
    with pytest.raises(PaymentGatewayError, match="prepay_unavailable"):
        store.open(payment)
    await db_session.rollback()
