"""Refund timeout recovery queries and retries one stable merchant identity."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from src.integrations.wechat_pay_types import RefundFact, RefundNotFoundError
from src.models.mall_base import utc_now
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallRefund
from src.models.mall_operations import MallGatewayEvent, MallJob
from src.models.mall_trade import MallOrder
from src.schemas.mall_catalog import VersionAction
from src.services.mall_refund_service import (
    MallRefundExecutor,
    MallRefundQueryExecutor,
    execute_refund,
    queue_refund_query,
    record_verified_refund_notification,
)
from src.tasks.mall_tasks import run_mall_worker_once
from tests.conftest import TestAsyncSession
from tests.unit.test_mall_refund_service import refund_ready


class RefundChannel:
    appid, mchid = "wx-test", "test-merchant"

    def __init__(self, payment, refund, sessions):
        self.payment, self.refund, self.sessions = payment, refund, sessions
        self.calls = []
        self.query_count = 0

    async def query_refund(self, out_refund_no):
        assert out_refund_no == self.refund.out_refund_no
        self.calls.append(("query", out_refund_no))
        self.query_count += 1
        if self.query_count == 1:
            async with self.sessions() as db:
                current = await db.get(MallRefund, self.refund.id)
                assert current.status == "unknown"  # uncertainty committed before I/O
            raise RefundNotFoundError()
        return self.fact("SUCCESS")

    async def create_refund(self, *, out_trade_no, out_refund_no, total_cent, refund_cent):
        assert out_trade_no == self.payment.out_trade_no
        assert out_refund_no == self.refund.out_refund_no
        assert total_cent == self.refund.original_amount_cent
        assert refund_cent == self.refund.total_cent
        async with self.sessions() as db:
            current = await db.get(MallRefund, self.refund.id)
            assert current.status == "unknown"
        self.calls.append(("create", out_refund_no))
        return self.fact("PROCESSING")

    def fact(self, status):
        return RefundFact(
            out_refund_no=self.refund.out_refund_no,
            out_trade_no=self.payment.out_trade_no,
            status=status,
            total_cent=self.refund.original_amount_cent,
            refund_cent=self.refund.total_cent,
            currency="CNY",
            transaction_id="synthetic-channel-id",
            channel_refund_id=("synthetic-channel-refund" if status == "SUCCESS" else None),
            success_at=utc_now() if status == "SUCCESS" else None,
        )


@pytest.mark.asyncio
async def test_worker_queries_first_and_retries_same_refund_identity(db_session, monkeypatch):
    finance, order, aftersale, skus, items, payment = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-recovery-execute-001",
    )
    await db_session.commit()
    refund_id, order_id, sku_id, order_item_id = refund.id, order.id, skus[1].id, items[1].id
    channel = RefundChannel(payment, refund, TestAsyncSession)
    handler = MallRefundExecutor(TestAsyncSession, lambda _: channel)

    assert await run_mall_worker_once(
        TestAsyncSession, handlers={"mall_refund_execute": handler}, enabled=True
    )
    job = await db_session.scalar(
        select(MallJob).where(MallJob.kind == "mall_refund_execute", MallJob.entity_id == refund_id)
    )
    assert job.status == "retry"
    job.next_run_at = utc_now() - timedelta(seconds=1)
    await db_session.commit()

    assert await run_mall_worker_once(
        TestAsyncSession, handlers={"mall_refund_execute": handler}, enabled=True
    )
    async with TestAsyncSession() as fresh:
        settled = await fresh.get(MallRefund, refund_id)
        refreshed_order = await fresh.get(MallOrder, order_id)
        refreshed_sku = await fresh.get(type(skus[1]), sku_id)
        refreshed_line = await fresh.get(type(items[1]), order_item_id)
        source = await fresh.scalar(
            select(MallConsumption).where(MallConsumption.order_id == order_id)
        )
        assert settled.status == "succeeded" and settled.active_slot is None
        assert refreshed_order.refunded_goods_cent == 5000
        assert refreshed_order.refund_reserved_cent == 0
        assert refreshed_sku.available_qty == 9 and refreshed_line.refunded_quantity == 1
        assert source.successful_goods_refund_cent == 5000
        assert (
            await fresh.scalar(
                select(func.count()).select_from(MallRefund).where(MallRefund.id == refund_id)
            )
            == 1
        )
        completed_job = await fresh.get(MallJob, job.id)
        assert completed_job.status == "done"
    assert channel.calls == [
        ("query", refund.out_refund_no),
        ("create", refund.out_refund_no),
        ("query", refund.out_refund_no),
    ]


@pytest.mark.asyncio
async def test_verified_notification_event_persists_before_duplicate_application(
    db_session, monkeypatch
):
    finance, order, aftersale, _, _, payment = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-notification-execute-001",
    )
    fact = RefundFact(
        out_refund_no=refund.out_refund_no,
        out_trade_no=payment.out_trade_no,
        status="SUCCESS",
        total_cent=payment.amount_cent,
        refund_cent=refund.total_cent,
        currency="CNY",
        transaction_id=payment.channel_transaction_id,
        channel_refund_id="notification-synthetic-refund",
        success_at=utc_now(),
    )
    for _ in range(2):
        event = await record_verified_refund_notification(
            db_session,
            event_id="refund-event-001",
            refund_id=refund.id,
            fact=fact,
            verified_digest="a" * 64,
        )
    await db_session.commit()

    assert event.status == "processed"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallGatewayEvent)
            .where(MallGatewayEvent.event_id == "refund-event-001")
        )
        == 1
    )
    assert order.refunded_goods_cent == 5000 and order.refund_reserved_cent == 0


@pytest.mark.asyncio
async def test_manual_query_updates_verified_state_but_never_creates_a_refund(
    db_session, monkeypatch
):
    finance, order, aftersale, _, _, payment = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-manual-query-execute-001",
    )
    await db_session.commit()
    refund_id = refund.id
    result = await queue_refund_query(
        db_session,
        finance,
        refund.id,
        VersionAction(expectedVersion=refund.version),
        key="refund-manual-query-request-001",
    )
    await db_session.commit()

    class QueryOnlyChannel(RefundChannel):
        async def query_refund(self, out_refund_no):
            self.calls.append(("query", out_refund_no))
            return self.fact("PROCESSING")

        async def create_refund(self, **kwargs):
            raise AssertionError("manual query must never submit a refund")

    channel = QueryOnlyChannel(payment, refund, TestAsyncSession)
    handler = MallRefundQueryExecutor(TestAsyncSession, lambda _: channel)
    assert await run_mall_worker_once(
        TestAsyncSession, handlers={"mall_refund_query": handler}, enabled=True
    )

    async with TestAsyncSession() as fresh:
        current = await fresh.get(MallRefund, refund_id)
        query_job = await fresh.get(MallJob, int(result["jobId"]))
        current_order = await fresh.get(MallOrder, order.id)
        assert current.status == "processing"
        assert current.last_query_at is not None and current.last_error_code is None
        assert current_order.refund_reserved_cent == 5000
        assert query_job.status == "done"
    assert channel.calls == [("query", refund.out_refund_no)]
