"""Workbench aggregation boundaries and notification failure isolation."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.api.mall_deps import MallActor
from src.models.mall_base import utc_now
from src.models.mall_finance import MallRefund
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallAftersale
from tests.conftest import TestAsyncSession, seed_admin
from tests.unit.test_mall_payment_service import payable


@pytest.mark.asyncio
async def test_payment_unknown_workbench_threshold_is_strictly_over_ten_minutes(
    db_session, monkeypatch
):
    from src.services.mall_workbench_service import get_mall_workbench

    _, _, _, exactly_ten_minutes = await payable(
        db_session, monkeypatch, openid="workbench-threshold-exact"
    )
    _, _, _, over_ten_minutes = await payable(
        db_session, monkeypatch, openid="workbench-threshold-over"
    )
    now = utc_now()
    exactly_ten_minutes.status = over_ten_minutes.status = "unknown"
    exactly_ten_minutes.last_error_code = over_ten_minutes.last_error_code = "gateway_timeout"
    exactly_ten_minutes.unknown_since = now - timedelta(minutes=10)
    over_ten_minutes.unknown_since = now - timedelta(minutes=10, seconds=1)
    exactly_ten_minutes.last_query_at = over_ten_minutes.last_query_at = now
    from src.services.mall_funds_state import mark_funds_unknown

    mark_funds_unknown(exactly_ten_minutes, now=now)
    mark_funds_unknown(over_ten_minutes, now=now)
    assert exactly_ten_minutes.unknown_since == now - timedelta(minutes=10)
    assert over_ten_minutes.unknown_since == now - timedelta(minutes=10, seconds=1)
    actor = MallActor("admin", 1, frozenset({"mall.payments.read"}))

    summary = await get_mall_workbench(db_session, actor, now=now)

    assert summary["paymentUnknown"] == 1


@pytest.mark.asyncio
async def test_workbench_database_error_propagates_instead_of_becoming_zeroes(
    db_session, monkeypatch
):
    from src.services.mall_workbench_service import get_mall_workbench

    async def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic database read failure")

    for method in ("execute", "scalar", "scalars"):
        monkeypatch.setattr(db_session, method, fail)
    actor = MallActor("admin", 1, frozenset({"mall.invoices.read"}))

    with pytest.raises(RuntimeError, match="synthetic database read failure"):
        await get_mall_workbench(db_session, actor, now=utc_now())


@pytest.mark.asyncio
async def test_all_permission_scopes_return_the_complete_zero_summary(db_session):
    from src.services.mall_workbench_service import get_mall_workbench

    permissions = frozenset(
        {
            "mall.orders.read",
            "mall.shipments.write",
            "mall.aftersales.read",
            "mall.aftersales.review",
            "mall.returns.receive",
            "mall.payments.read",
            "mall.payments.query",
            "mall.refunds.read",
            "mall.refunds.query",
            "mall.refunds.execute",
            "mall.reconciliations.read",
            "mall.attribution.write",
            "performance.settle",
            "mall.invoices.read",
            "mall.invoices.write",
            "mall.stock.read",
            "mall.stock.write",
        }
    )
    actor = MallActor("admin", 1, permissions)

    summary = await get_mall_workbench(db_session, actor, now=utc_now())

    assert len(summary) == 12
    assert all(value == 0 for value in summary.values())


def test_workbench_day_window_uses_beijing_midnight_and_half_open_range():
    from src.services.mall_workbench_service import _beijing_day_range

    before_beijing_midnight = _beijing_day_range(datetime(2026, 11, 8, 15, 59, 59))
    at_beijing_midnight = _beijing_day_range(datetime(2026, 11, 8, 16, 0, 0))

    assert before_beijing_midnight == (
        datetime(2026, 11, 7, 16, 0, 0),
        datetime(2026, 11, 8, 16, 0, 0),
    )
    assert at_beijing_midnight == (
        datetime(2026, 11, 8, 16, 0, 0),
        datetime(2026, 11, 9, 16, 0, 0),
    )


@pytest.mark.asyncio
async def test_workbench_daily_money_uses_paid_and_refund_success_time(
    db_session, monkeypatch
):
    from src.services.mall_workbench_service import get_mall_workbench

    _, order, _, payment = await payable(db_session, monkeypatch)
    admin_id = await seed_admin(db_session, username="workbench-money-" + uuid4().hex)
    aftersale = MallAftersale(
        aftersale_no="W" + uuid4().hex[:31],
        order_id=order.id,
        buyer_user_id=order.buyer_user_id,
        method="refund_only",
        status="completed",
        reason="合成工作台日金额样例",
    )
    db_session.add(aftersale)
    await db_session.flush()

    payment.status = "succeeded"
    order.status = "pending_shipment"
    order.paid_amount_cent = order.payable_amount_cent
    order.paid_at = datetime(2026, 11, 7, 16, 0, 0)  # Beijing Nov 8 at 00:00.
    order.refunded_goods_cent = 100
    refund = MallRefund(
        aftersale_id=aftersale.id,
        payment_id=payment.id,
        order_id=order.id,
        out_refund_no="WR" + uuid4().hex[:30],
        status="succeeded",
        goods_refund_cent=100,
        freight_refund_cent=0,
        total_cent=100,
        original_amount_cent=payment.amount_cent,
        requested_by=admin_id,
        active_slot=None,
        confirmed_at=datetime(2026, 11, 8, 15, 59, 59),  # Beijing Nov 8 at 23:59:59.
    )
    db_session.add(refund)
    await db_session.flush()
    actor = MallActor(
        "admin", admin_id, frozenset({"mall.payments.read", "mall.refunds.read"})
    )

    today = await get_mall_workbench(
        db_session, actor, now=datetime(2026, 11, 8, 15, 59, 59)
    )
    tomorrow = await get_mall_workbench(
        db_session, actor, now=datetime(2026, 11, 8, 16, 0, 0)
    )

    assert today["paidTodayCent"] == payment.amount_cent
    assert today["refundedTodayCent"] == 100
    assert tomorrow["paidTodayCent"] == tomorrow["refundedTodayCent"] == 0


@pytest.mark.asyncio
async def test_failed_notification_job_does_not_rollback_committed_trade(
    db_session, monkeypatch
):
    from src.tasks.mall_tasks import run_mall_worker_once

    _, order, _, payment = await payable(db_session, monkeypatch)
    now = utc_now()
    order.status = "pending_shipment"
    order.paid_amount_cent = order.payable_amount_cent
    order.paid_at = now
    payment.status = "succeeded"
    job = MallJob(
        kind="mall_notification_delivery",
        entity_type="mall_order",
        entity_id=order.id,
        entity_version=order.version,
        dedupe_key=f"workbench-notification-failure:{order.id}",
        status="ready",
        attempts=0,
        next_run_at=now,
    )
    db_session.add(job)
    await db_session.commit()

    async def fail_delivery(_item):
        raise RuntimeError("synthetic notification provider failure")

    assert await run_mall_worker_once(
        TestAsyncSession,
        handlers={"mall_notification_delivery": fail_delivery},
        enabled=True,
    )

    await db_session.refresh(order)
    await db_session.refresh(payment)
    await db_session.refresh(job)
    assert order.status == "pending_shipment" and order.paid_amount_cent > 0
    assert payment.status == "succeeded"
    assert job.status == "retry" and job.attempts == 1
    assert await db_session.scalar(
        select(MallJob.id).where(MallJob.dedupe_key == job.dedupe_key)
    ) == job.id
