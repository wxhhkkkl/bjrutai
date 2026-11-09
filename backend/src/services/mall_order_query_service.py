"""Buyer-safe order projections always read immutable trade snapshots."""

from sqlalchemy import func, or_, select

from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_consumption import MallConsumption
from ..models.mall_finance import MallInvoiceRequest, MallPayment
from ..models.mall_trade import MallAftersale, MallOrder, MallOrderItem, MallShipment
from .mall_catalog_query_service import _page
from .mall_order_service import audit_order
from .mall_order_text import safe_order_text


def timestamp(value):
    return value.isoformat() + "Z" if value else None


def address_view(snapshot):
    return {
        "id": snapshot["id"],
        "recipientName": snapshot["recipientName"],
        "phoneMasked": snapshot["phoneMasked"],
        "regionCodes": snapshot["regionCodes"],
        "addressMasked": "详细地址已保存",
        "isDefault": False,
        "version": snapshot["version"],
    }


async def _relations(db, orders):
    """Load a page in batches; do not run seven queries for every row."""
    identities = [order.id for order in orders]
    result = {
        identity: {
            "items": [],
            "aftersales": [],
            "payment": None,
            "invoice": None,
            "consumption": None,
            "shipment": None,
        }
        for identity in identities
    }
    if not identities:
        return result
    for model, name, column, values in [
        (MallOrderItem, "items", MallOrderItem.order_id, identities),
        (MallAftersale, "aftersales", MallAftersale.order_id, identities),
        (
            MallInvoiceRequest,
            "invoice",
            MallInvoiceRequest.id,
            [o.current_invoice_request_id for o in orders if o.current_invoice_request_id],
        ),
        (MallConsumption, "consumption", MallConsumption.order_id, identities),
        (MallShipment, "shipment", MallShipment.order_id, identities),
    ]:
        if not values:
            continue
        rows = await db.scalars(select(model).where(column.in_(values)).order_by(model.id))
        for row in rows:
            if row.order_id not in result:
                continue
            if name in {"items", "aftersales"}:
                result[row.order_id][name].append(row)
            else:
                result[row.order_id][name] = row
    active = {order.id: order.active_payment_id for order in orders}
    latest = (
        select(func.max(MallPayment.id))
        .where(MallPayment.order_id.in_(identities))
        .group_by(MallPayment.order_id)
    )
    payments = await db.scalars(
        select(MallPayment)
        .where(
            MallPayment.order_id.in_(identities),
            or_(
                MallPayment.id.in_([identity for identity in active.values() if identity]),
                MallPayment.id.in_(latest),
            ),
        )
        .order_by(MallPayment.id)
    )
    for payment in payments:
        existing = result[payment.order_id]["payment"]
        if existing is None or existing.id != active[payment.order_id]:
            result[payment.order_id]["payment"] = payment
    return result


async def serialize_order(db, order, *, detail=False, relations=None):
    related = (relations if relations is not None else await _relations(db, [order]))[order.id]
    items, payment, invoice = related["items"], related["payment"], related["invoice"]
    aftersales, consumption, shipment = (
        related["aftersales"],
        related["consumption"],
        related["shipment"],
    )
    result = {
        "id": str(order.id),
        "orderNo": order.order_no,
        "status": order.status,
        "paymentStatus": (
            payment.status
            if payment
            else ("succeeded" if order.paid_amount_cent else "not_started")
        ),
        "aftersaleStatus": aftersales[-1].status if aftersales else "none",
        "goodsAmountCent": order.goods_amount_cent,
        "freightAmountCent": order.freight_amount_cent,
        "payableAmountCent": order.payable_amount_cent,
        "paidAmountCent": order.paid_amount_cent,
        "refundedGoodsCent": order.refunded_goods_cent,
        "refundedFreightCent": order.refunded_freight_cent,
        "refundReservedCent": order.refund_reserved_cent,
        "netReceivedCent": order.paid_amount_cent
        - order.refunded_goods_cent
        - order.refunded_freight_cent,
        "items": [
            {
                "id": str(item.id),
                "skuId": str(item.sku_id),
                "productName": item.product_snapshot["name"],
                "optionsText": item.product_snapshot.get("optionsText", ""),
                "unitPriceCent": item.unit_price_cent,
                "quantity": item.quantity,
                "lineAmountCent": item.line_amount_cent,
                "refundedGoodsCent": item.refunded_goods_cent,
                "availableAftersaleQuantity": (
                    max(
                        0, item.quantity - item.refunded_quantity - item.aftersale_reserved_quantity
                    )
                    if order.paid_amount_cent
                    else 0
                ),
            }
            for item in items
        ],
        "address": address_view(order.address_snapshot),
        "version": order.version,
        "shipment": (
            {
                "id": str(shipment.id),
                "courierCode": shipment.courier_code,
                "trackingNo": shipment.tracking_no,
                "shippedAt": timestamp(shipment.shipped_at),
                "autoReceiveAt": timestamp(shipment.auto_receive_at),
                "platformSyncStatus": shipment.platform_sync_status,
                "platformConfirmedAt": timestamp(shipment.platform_confirmed_at),
                "version": shipment.version,
            }
            if shipment
            else None
        ),
        "createdAt": timestamp(order.created_at),
        "paidAt": timestamp(order.paid_at),
        "expiresAt": timestamp(order.expires_at),
        "businessPeriod": order.business_period,
        "invoiceStatus": invoice.status if invoice else "not_requested",
        "attributionStatus": (
            "assigned" if consumption and consumption.attributed_distributor_id else "unassigned"
        ),
        "invoiceRequestId": str(invoice.id) if invoice else None,
        "aftersaleIds": [str(row.id) for row in aftersales],
        "paymentId": str(payment.id) if payment else None,
    }
    if detail:
        labels = {
            "mall_order_created": ("created", "提交订单", "买家"),
            "mall_order_closed": ("closed", "订单关闭", "买家"),
            "mall_payment_succeeded": ("paid", "确认收款", "系统核实"),
            "mall_payment_closed": ("closed", "核实关闭付款", "系统核实"),
            "mall_order_expired": ("closed", "付款超时关闭", "系统核实"),
            "mall_order_expiry_close_requested": (
                "cancel_requested",
                "付款超时，核实关闭中",
                "系统核实",
            ),
            "mall_order_cancel_requested": ("cancel_requested", "申请取消，核实关闭中", "买家"),
            "mall_order_address_changed": ("address_changed", "修改收货地址", "买家"),
            "mall_admin_cancel_requested": ("cancel_requested", "商家申请取消，核实关闭中", "商家"),
            "mall_admin_order_closed": ("closed", "商家关闭未付款订单", "商家"),
            "mall_admin_order_shipped": ("shipped", "商家登记发货", "商家"),
            "mall_admin_tracking_corrected": ("tracking_corrected", "商家更正运单", "商家"),
            "mall_order_received": ("received", "确认收货", "买家"),
            "mall_order_auto_received": ("received", "系统自动确认收货", "系统"),
        }
        events = (
            await db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == "mall_order",
                    AuditLog.entity_id == str(order.id),
                    AuditLog.action.in_(labels),
                )
                .order_by(AuditLog.created_at, AuditLog.id)
            )
        ).all()
        result.update(
            buyerNote=safe_order_text(order.buyer_note),
            receivedAt=timestamp(order.received_at),
            closedAt=timestamp(order.closed_at),
            closeReason=safe_order_text(order.close_reason),
            consumptionId=str(consumption.id) if consumption else None,
            timeline=[
                {
                    "id": str(row.id),
                    "action": labels[row.action][0],
                    "label": labels[row.action][1],
                    "occurredAt": timestamp(row.created_at),
                    "actorLabel": labels[row.action][2],
                    "reason": None,
                }
                for row in events
            ],
            # Expose actions only when their owning routes are implemented.
            availableActions=(
                (
                    (
                        ["cancelMallOrder"]
                        if order.status == "pending_payment" and not order.paid_amount_cent
                        else []
                    )
                    + (
                        ["changeMallOrderAddress"]
                        if order.status in {"pending_payment", "pending_shipment"}
                        and not shipment
                        and not order.shipped_at
                        and (order.status != "pending_payment" or order.expires_at > utc_now())
                        and not any(
                            a.status not in {"rejected", "withdrawn", "closed", "succeeded"}
                            for a in aftersales
                        )
                        else []
                    )
                    + (
                        ["confirmMallReceipt"]
                        if order.status == "pending_receipt" and shipment
                        else []
                    )
                )
                if not order.close_requested_at
                else []
            ),
        )
    return result


async def list_orders(db, actor, *, cursor=None, page_size=20, status=None):
    query = select(MallOrder).where(MallOrder.buyer_user_id == actor.actor_id)
    if status:
        query = query.where(MallOrder.status == status)
    rows, next_cursor, total = await _page(
        db,
        query,
        MallOrder,
        MallOrder.id,
        mode=f"orders:{actor.actor_id}:{status}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    related = await _relations(db, rows)
    for row in rows:
        audit_order(db, actor, row, "mall_order_read")
    return {
        "items": [await serialize_order(db, row, relations=related) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }
