"""Payment workers use separate real InnoDB transactions; channel is entirely fake."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from src.models.mall_base import utc_now
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallOrder
from src.schemas.mall_catalog import VersionAction
from src.services.mall_payment_service import prepare_payment
from tests.mysql.test_mall_reliability_payments import enable, local_order
from tests.unit.test_mall_payment_execution import Channel, execute


async def context(sessions, monkeypatch):
    enable(monkeypatch)
    actor, identity, version = await local_order(sessions)
    async with sessions() as db:
        payment = await prepare_payment(
            db,
            actor,
            identity,
            VersionAction(expectedVersion=version),
            key="mysql-worker-payment-" + uuid4().hex,
        )
        order = await db.get(MallOrder, identity)
        from src.models.user import User

        buyer = await db.get(User, actor.actor_id)
        buyer.openid = "worker-test-" + uuid4().hex
        await db.commit()
        channel = Channel(payment, order)
        channel.fact = replace(
            channel.fact, openid=buyer.openid, transaction_id="worker-channel-" + uuid4().hex
        )
        channel.sessions = sessions
        job_id = await db.scalar(
            select(MallJob.id).where(
                MallJob.kind == "mall_payment_create", MallJob.entity_id == payment.id
            )
        )
        return channel, payment.id, order.id, job_id


async def test_many_workers_issue_only_one_prepay_and_hold_no_network_locks(
    mall_mysql_sessions, monkeypatch
):
    channel, payment_id, order_id, job_id = await context(mall_mysql_sessions, monkeypatch)

    async def assert_unlocked():
        async with mall_mysql_sessions() as db:
            for model, identity in (
                (MallOrder, order_id),
                (MallPayment, payment_id),
                (MallJob, job_id),
            ):
                row = await db.scalar(
                    select(model).where(model.id == identity).with_for_update(nowait=True)
                )
                assert row is not None
            await db.rollback()
        await asyncio.sleep(0.02)

    channel.after_io = assert_unlocked
    outcomes = await asyncio.wait_for(
        asyncio.gather(*[execute(channel, factory=mall_mysql_sessions) for _ in range(12)]),
        timeout=30,
    )
    assert outcomes.count(True) == 1 and channel.calls == ["prepay"]
    async with mall_mysql_sessions() as db:
        assert (await db.get(MallPayment, payment_id)).status == "pending"
        assert (await db.get(MallJob, job_id)).attempts == 0


async def test_expired_lease_recovery_queries_instead_of_repeating_prepay(
    mall_mysql_sessions, monkeypatch
):
    channel, payment_id, order_id, job_id = await context(mall_mysql_sessions, monkeypatch)

    async def lose_lease():
        async with mall_mysql_sessions() as db:
            job = await db.get(MallJob, job_id)
            job.lease_owner = "newer-worker"
            job.lease_until = utc_now() - timedelta(seconds=1)
            await db.commit()

    channel.after_io = lose_lease
    assert await execute(channel, factory=mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        payment = await db.get(MallPayment, payment_id)
        assert payment.status == "unknown" and payment.prepay_ciphertext is None
    channel.after_io = None
    channel.fact = replace(channel.fact, state="SUCCESS")
    assert await execute(channel, factory=mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        assert (await db.get(MallOrder, order_id)).status == "pending_shipment"
        assert (await db.get(MallJob, job_id)).status == "done"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallConsumption)
                .where(MallConsumption.order_id == order_id)
            )
            == 1
        )
    assert channel.calls == ["prepay", "query"]


async def test_worker_fact_commit_failure_is_requeried_and_applied_once(
    mall_mysql_sessions, monkeypatch
):
    from src.services import mall_payment_facts_service as facts

    channel, payment_id, order_id, job_id = await context(mall_mysql_sessions, monkeypatch)
    await execute(channel, factory=mall_mysql_sessions)
    original = facts.record_paid_order

    async def fail_after_source(db, order):
        await original(db, order)
        raise RuntimeError("synthetic crash after source")

    channel.fact = replace(channel.fact, state="SUCCESS")
    async with mall_mysql_sessions() as db:
        (await db.get(MallJob, job_id)).next_run_at = utc_now() - timedelta(seconds=1)
        await db.commit()
    monkeypatch.setattr(facts, "record_paid_order", fail_after_source)
    await execute(channel, factory=mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        assert (await db.get(MallPayment, payment_id)).status == "unknown"
        assert (await db.get(MallOrder, order_id)).paid_amount_cent == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallConsumption)
                .where(MallConsumption.order_id == order_id)
            )
            == 0
        )
        (await db.get(MallJob, job_id)).next_run_at = utc_now() - timedelta(seconds=1)
        await db.commit()
    monkeypatch.setattr(facts, "record_paid_order", original)
    await execute(channel, factory=mall_mysql_sessions)
    async with mall_mysql_sessions() as db:
        assert (await db.get(MallPayment, payment_id)).status == "succeeded"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MallConsumption)
                .where(MallConsumption.order_id == order_id)
            )
            == 1
        )
    assert channel.calls == ["prepay", "query", "query"]
