from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from src.models.mall_base import utc_now
from src.models.mall_operations import MallJob
from src.schemas.mall_checkout import OrderCancel
from src.services.mall_order_action_service import cancel_order, cancel_progress
from src.tasks.mall_tasks import run_mall_worker_once
from tests.conftest import TestAsyncSession
from tests.unit.test_mall_order_actions import unattempted
from tests.unit.test_mall_payment_execution import Channel, execute
from tests.unit.test_mall_payment_service import payable


@pytest.mark.asyncio
async def test_expiry_defers_until_deadline_then_closes_once_despite_changed_order_version(
    db_session, monkeypatch
):
    from src.services.mall_order_expiry_service import order_handlers

    actor, _, skus, _, order = await unattempted(db_session, monkeypatch)
    job = await db_session.scalar(select(MallJob).where(MallJob.kind == "mall_order_expire"))
    job.next_run_at = utc_now() - timedelta(seconds=1)
    order.version += 1
    await db_session.commit()
    handlers = order_handlers(TestAsyncSession)
    assert await run_mall_worker_once(TestAsyncSession, handlers=handlers, enabled=True)
    await db_session.refresh(order)
    await db_session.refresh(job)
    assert order.status == "pending_payment" and job.status == "retry"
    order.expires_at = job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    assert await run_mall_worker_once(TestAsyncSession, handlers=handlers, enabled=True)
    await db_session.refresh(order)
    await db_session.refresh(skus[0])
    assert order.status == "closed" and skus[0].available_qty == 10
    assert order.close_requested_at and skus[0].reserved_qty == 0
    assert not await run_mall_worker_once(TestAsyncSession, handlers=handlers, enabled=True)


@pytest.mark.asyncio
async def test_expiry_with_channel_history_only_queues_reconciliation(db_session, monkeypatch):
    from src.services.mall_order_expiry_service import order_handlers

    _, order, skus, payment = await payable(db_session, monkeypatch)
    expiry = await db_session.scalar(select(MallJob).where(MallJob.kind == "mall_order_expire"))
    order.expires_at = payment.expires_at = expiry.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    await run_mall_worker_once(
        TestAsyncSession, handlers=order_handlers(TestAsyncSession), enabled=True
    )
    await db_session.refresh(order)
    await db_session.refresh(skus[0])
    assert order.status == "pending_payment" and order.close_requested_at
    assert skus[0].reserved_qty == 1
    assert await db_session.scalar(select(MallJob.id).where(MallJob.kind == "mall_order_close"))


@pytest.mark.asyncio
async def test_invalid_money_configuration_cannot_block_unattempted_local_expiry(
    db_session, monkeypatch
):
    from src.core import database
    from src.core.config import get_settings
    from src.tasks.mall_tasks import mall_worker_job

    _, _, skus, _, order = await unattempted(db_session, monkeypatch)
    job = await db_session.scalar(select(MallJob).where(MallJob.kind == "mall_order_expire"))
    order.expires_at = job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()
    settings = get_settings()
    monkeypatch.setattr(settings, "mall_worker_enabled", True)
    monkeypatch.setattr(settings, "mall_gateway_mode", "live")
    monkeypatch.setattr(settings, "mall_gateway_outbound_enabled", True)
    monkeypatch.setattr(settings, "mall_prepay_keys", {})
    monkeypatch.setattr(database, "async_session", TestAsyncSession)
    await mall_worker_job()
    await db_session.refresh(order)
    await db_session.refresh(skus[0])
    assert order.status == "closed" and skus[0].available_qty == 10


@pytest.mark.asyncio
async def test_cancelled_order_query_closes_before_expiry_and_never_creates_new_prepay(
    db_session, monkeypatch
):
    actor, order, skus, payment = await payable(db_session, monkeypatch)
    command = await cancel_order(
        db_session,
        actor,
        order.id,
        OrderCancel(expectedVersion=order.version, reason="取消"),
        key="worker-cancel-intent-001",
    )
    await db_session.commit()
    channel = Channel(payment, order)
    await execute(channel)
    await db_session.refresh(order)
    await db_session.refresh(skus[0])
    assert channel.calls == ["query", "close"]
    assert order.status == "closed" and skus[0].reserved_qty == 0
    assert (await cancel_progress(db_session, command))["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_query_success_keeps_money_and_returns_manual_instead_of_closed(
    db_session, monkeypatch
):
    from src.services.mall_payment_execution_service import MallPaymentExecutor
    from tests.unit.test_mall_payment_execution import vault

    actor, order, skus, payment = await payable(db_session, monkeypatch)
    command = await cancel_order(
        db_session,
        actor,
        order.id,
        OrderCancel(expectedVersion=order.version, reason="取消"),
        key="paid-worker-cancel-intent-001",
    )
    await db_session.commit()
    channel = Channel(payment, order)
    channel.fact = replace(channel.fact, state="SUCCESS")
    handler = MallPaymentExecutor(
        TestAsyncSession, lambda _: channel, vault(), "https://example.test/notify"
    )
    assert await run_mall_worker_once(
        TestAsyncSession, handlers={"mall_order_close": handler}, enabled=True
    )
    await db_session.refresh(order)
    await db_session.refresh(skus[0])
    assert (
        order.status == "pending_shipment" and order.paid_amount_cent == order.payable_amount_cent
    )
    assert skus[0].available_qty == 9 and skus[0].reserved_qty == 0
    assert channel.calls == ["query"]
    assert (await cancel_progress(db_session, command))["status"] == "manual"
    job = await db_session.scalar(select(MallJob).where(MallJob.kind == "mall_order_close"))
    assert job.status == "manual" and job.last_error_code == "close_found_paid_order"
