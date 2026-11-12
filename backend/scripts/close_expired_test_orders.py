"""Close payment-expired orders whose channel close work needs a live gateway.

Local/test data only. The worker cannot verify an expired order that already
has a payment attempt while the WeChat gateway is disabled, so those orders
stay pending_payment. This one-off script closes an explicitly listed batch
after rechecking that no payment was ever confirmed, and releases stock through
the same facts used by channel-verified close.

Usage (dry run, shows the plan):

    ./.venv/bin/python -m scripts.close_expired_test_orders \
        --order M391771e264b8465a8bd9e97fa5a9e62 --order ...

Add --apply to commit.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from src.core.config import get_settings
from src.core.database import async_session
from src.models.audit import AuditLog
from src.models.mall_base import utc_now
from src.models.mall_finance import MallPayment
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallOrder
from src.services.mall_payment_facts_service import audit_payment
from src.services.mall_payment_stock_service import locked_stock, stock_event

CLOSE_REASON = "付款超时关闭（测试环境本地核销）"


def _assert_local_environment():
    settings = get_settings()
    if (
        settings.app_environment not in {"development", "test"}
        or settings.mall_gateway_mode != "test"
        or settings.mall_gateway_outbound_enabled
    ):
        raise SystemExit(
            "refused: only development/test with a non-live gateway may run this cleanup"
        )


async def _close_one(db, order_no, *, apply):
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.order_no == order_no)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        print(f"[skip] {order_no}: not found")
        return False
    if order.status != "pending_payment" or order.paid_amount_cent or order.paid_at:
        print(f"[skip] {order_no}: status={order.status} paid={order.paid_amount_cent}")
        return False
    if not order.close_requested_at:
        print(f"[skip] {order_no}: close was never requested")
        return False
    payments = (
        await db.scalars(
            select(MallPayment)
            .where(MallPayment.order_id == order.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(payments) != 1:
        print(f"[skip] {order_no}: expected one payment attempt, found {len(payments)}")
        return False
    payment = payments[0]
    if (
        payment.status == "succeeded"
        or payment.channel_transaction_id
        or payment.confirmed_at
    ):
        print(f"[skip] {order_no}: payment shows a channel fact")
        return False
    if payment.active_slot != 1:
        print(f"[skip] {order_no}: payment has no active slot")
        return False

    jobs = (
        await db.scalars(
            select(MallJob)
            .where(
                MallJob.entity_type == "mall_order",
                MallJob.entity_id == order.id,
                MallJob.kind == "mall_order_close",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()

    if not apply:
        print(
            f"[plan] {order_no}: order#{order.id} payment#{payment.id}"
            f" ({payment.status}) jobs={[(j.id, j.status) for j in jobs]}"
        )
        return False

    items, skus = await locked_stock(db, order)
    stock_event(db, order, payment, items, skus, release=True)
    now = utc_now()
    order.status, order.closed_at, order.close_reason = "closed", now, CLOSE_REASON
    order.active_payment_id = None
    order.version += 1

    payment.status, payment.active_slot, payment.confirmed_at = "closed", None, now
    payment.last_query_at, payment.unknown_since = now, None
    payment.prepay_ciphertext = None
    payment.last_error_code = "local_test_cleanup_unpaid"
    payment.version += 1

    for job in jobs:
        job.status, job.finished_at = "done", now
        job.lease_owner = job.lease_until = job.last_error_code = None
        job.resolution_code = "local_test_cleanup_unpaid"
        job.resolution_summary = CLOSE_REASON
        job.resolved_by_type, job.resolved_by_id, job.resolved_at = "system", 0, now

    db.add(
        AuditLog(
            user_id=None,
            action="mall_order_expired",
            entity_type="mall_order",
            entity_id=str(order.id),
            detail={
                "actorType": "system",
                "version": order.version,
                "source": "local_test_cleanup",
                "channelVerification": "not_attempted",
            },
        )
    )
    audit_payment(db, order, payment, "mall_payment_closed")
    await db.flush()
    print(f"[closed] {order_no}: order#{order.id} payment#{payment.id}")
    return True


async def _main(order_numbers, *, apply):
    _assert_local_environment()
    closed = 0
    async with async_session() as db:
        for order_no in order_numbers:
            if await _close_one(db, order_no, apply=apply):
                closed += 1
        if apply:
            await db.commit()
        else:
            await db.rollback()
    print(f"[{'applied' if apply else 'dry-run'}] closed={closed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--order", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(_main(args.order, apply=args.apply))
