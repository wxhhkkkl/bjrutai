"""Permission-scoped summary counts for the independent mall workbench."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.mall_deps import MallActor
from ..models.mall_base import utc_now
from ..models.mall_catalog import MallProduct, MallSku
from ..models.mall_consumption import MallConsumption
from ..models.mall_finance import MallInvoice, MallInvoiceRequest, MallPayment, MallRefund
from ..models.mall_trade import MallAftersale, MallOrder, MallShipment

_UNKNOWN_FUNDS_DELAY = timedelta(minutes=10)
_BEIJING = ZoneInfo("Asia/Shanghai")

_PAYMENT_READ = frozenset({"mall.payments.read", "mall.payments.query"})
_REFUND_READ = frozenset({"mall.refunds.read", "mall.refunds.query", "mall.refunds.execute"})
_RECONCILIATION_READ = "mall.reconciliations.read"


def _has(actor: MallActor, *permissions: str) -> bool:
    return not actor.permissions.isdisjoint(permissions)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _beijing_day_range(now: datetime) -> tuple[datetime, datetime]:
    """Return today's Beijing calendar day as a half-open naive-UTC interval."""
    instant = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    day = instant.astimezone(_BEIJING).date()
    start_local = datetime.combine(day, time.min, tzinfo=_BEIJING)
    next_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=_BEIJING)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        next_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


async def _count(db: AsyncSession, statement) -> int:
    return int(await db.scalar(statement) or 0)


async def _sum(db: AsyncSession, statement) -> int:
    return int(await db.scalar(statement) or 0)


async def get_mall_workbench(
    db: AsyncSession, actor: MallActor, *, now: datetime | None = None
) -> dict[str, int]:
    """Count open work only in the caller's live permission scope.

    Every key is returned to keep the response shape stable. Unauthorized
    categories remain zero, and database failures intentionally propagate so
    callers cannot mistake a failed read for an empty queue.
    """
    instant = now or utc_now()
    now_utc = _utc_naive(instant)
    unknown_before = now_utc - _UNKNOWN_FUNDS_DELAY
    day_start, day_end = _beijing_day_range(instant)
    summary = {
        "pendingShipment": 0,
        "pendingPlatformReport": 0,
        "pendingAftersale": 0,
        "pendingReturnReceipt": 0,
        "paymentUnknown": 0,
        "refundAbnormal": 0,
        "unassigned": 0,
        "pendingAdjustment": 0,
        "pendingInvoice": 0,
        "pendingRedInvoice": 0,
        "lowStock": 0,
        "paidTodayCent": 0,
        "refundedTodayCent": 0,
    }

    if _has(actor, "mall.orders.read", "mall.shipments.write"):
        summary["pendingShipment"] = await _count(
            db,
            select(func.count())
            .select_from(MallOrder)
            .where(MallOrder.status == "pending_shipment"),
        )

    if "mall.shipments.write" in actor.permissions:
        summary["pendingPlatformReport"] = await _count(
            db,
            select(func.count())
            .select_from(MallShipment)
            .where(MallShipment.platform_report_status.in_({"pending", "unknown"})),
        )

    if _has(actor, "mall.aftersales.read", "mall.aftersales.review"):
        summary["pendingAftersale"] = await _count(
            db,
            select(func.count())
            .select_from(MallAftersale)
            .where(MallAftersale.status.in_({"submitted", "disputed"})),
        )

    if _has(actor, "mall.aftersales.read", "mall.returns.receive"):
        summary["pendingReturnReceipt"] = await _count(
            db,
            select(func.count())
            .select_from(MallAftersale)
            .where(
                MallAftersale.status == "awaiting_receipt",
                MallAftersale.return_sent_at.is_not(None),
            ),
        )

    if _has(actor, *_PAYMENT_READ, _RECONCILIATION_READ):
        summary["paymentUnknown"] = await _count(
            db,
            select(func.count())
            .select_from(MallPayment)
            .where(
                MallPayment.status == "unknown",
                MallPayment.unknown_since.is_not(None),
                MallPayment.unknown_since < unknown_before,
            ),
        )
        summary["paidTodayCent"] = await _sum(
            db,
            select(func.coalesce(func.sum(MallPayment.amount_cent), 0))
            .select_from(MallPayment)
            .join(MallOrder, MallOrder.id == MallPayment.order_id)
            .where(
                MallPayment.status == "succeeded",
                MallOrder.active_payment_id == MallPayment.id,
                MallOrder.paid_amount_cent > 0,
                MallOrder.paid_at >= day_start,
                MallOrder.paid_at < day_end,
            ),
        )

    if _has(actor, *_REFUND_READ, _RECONCILIATION_READ):
        summary["refundAbnormal"] = await _count(
            db,
            select(func.count())
            .select_from(MallRefund)
            .where(
                (MallRefund.status.in_({"abnormal", "rejected_unaccepted"}))
                | (
                    (MallRefund.status == "unknown")
                    & MallRefund.unknown_since.is_not(None)
                    & (MallRefund.unknown_since < unknown_before)
                )
            ),
        )
        summary["refundedTodayCent"] = await _sum(
            db,
            select(func.coalesce(func.sum(MallRefund.total_cent), 0)).where(
                MallRefund.status == "succeeded",
                MallRefund.confirmed_at >= day_start,
                MallRefund.confirmed_at < day_end,
            ),
        )

    if "mall.attribution.write" in actor.permissions:
        summary["unassigned"] = await _count(
            db,
            select(func.count())
            .select_from(MallConsumption)
            .where(MallConsumption.status == "unassigned"),
        )

    if "performance.settle" in actor.permissions:
        from ..models.performance_adjustment import PerformanceAdjustment

        summary["pendingAdjustment"] = await _count(
            db,
            select(func.count())
            .select_from(PerformanceAdjustment)
            .where(PerformanceAdjustment.status.in_({"proposed", "manual_required"})),
        )

    if _has(actor, "mall.invoices.read", "mall.invoices.write"):
        summary["pendingInvoice"] = await _count(
            db,
            select(func.count())
            .select_from(MallInvoiceRequest)
            .where(
                MallInvoiceRequest.active_slot == 1,
                MallInvoiceRequest.status.in_({"submitted", "needs_info", "issuing", "unknown"}),
            ),
        )
        summary["pendingRedInvoice"] = await _count(
            db,
            select(func.count())
            .select_from(MallInvoice)
            .where(
                MallInvoice.kind == "blue",
                MallInvoice.status.in_(
                    {"red_pending", "awaiting_counterparty", "partially_red"}
                ),
            ),
        )

    if _has(actor, "mall.stock.read", "mall.stock.write"):
        summary["lowStock"] = await _count(
            db,
            select(func.count())
            .select_from(MallSku)
            .join(MallProduct, MallProduct.id == MallSku.product_id)
            .where(
                MallSku.status == "active",
                MallProduct.status == "on_sale",
                MallSku.available_qty <= MallSku.warning_qty,
            ),
        )

    return summary
