"""Private buyer and permission-scoped administrator aftersale projections."""

from sqlalchemy import select

from ..core.exceptions import NotFoundException
from ..models.mall_finance import MallRefund
from ..models.mall_trade import MallAftersale, MallAftersaleItem, MallOrder, MallOrderItem
from .mall_catalog_query_service import _page
from .mall_order_text import safe_order_text


def serialize_refund(refund):
    """Safe financial projection; never expose provider raw payloads or account data."""
    return {
        "id": str(refund.id),
        "orderId": str(refund.order_id),
        "aftersaleId": str(refund.aftersale_id),
        "paymentId": str(refund.payment_id),
        "outRefundNo": refund.out_refund_no,
        "channelRefundId": refund.channel_refund_id,
        "goodsRefundCent": refund.goods_refund_cent,
        "freightRefundCent": refund.freight_refund_cent,
        "totalCent": refund.total_cent,
        "status": refund.status,
        "confirmedAt": refund.confirmed_at.isoformat() + "Z" if refund.confirmed_at else None,
        "lastErrorCode": refund.last_error_code,
        "version": refund.version,
    }


async def serialize_aftersale(db, row, *, buyer=False):
    order = await db.get(MallOrder, row.order_id)
    lines = (
        await db.execute(
            select(MallAftersaleItem, MallOrderItem.product_snapshot)
            .join(MallOrderItem, MallOrderItem.id == MallAftersaleItem.order_item_id)
            .where(MallAftersaleItem.aftersale_id == row.id)
            .order_by(MallAftersaleItem.id)
        )
    ).all()
    refund = await db.scalar(
        select(MallRefund)
        .where(MallRefund.aftersale_id == row.id)
        .order_by(MallRefund.id.desc())
        .limit(1)
    )
    result = {
        "id": str(row.id),
        "orderId": str(row.order_id),
        "orderNo": order.order_no if order else None,
        "aftersaleNo": row.aftersale_no,
        "createdAt": row.created_at.isoformat() + "Z" if row.created_at else None,
        "method": row.method,
        "status": row.status,
        "reason": safe_order_text(row.reason),
        "proofFileIds": [str(identity) for identity in row.proof_file_ids],
        "goodsRefundCent": row.goods_refund_cent,
        "freightRefundCent": row.freight_refund_cent,
        "refundId": str(refund.id) if refund else None,
        "auditReason": safe_order_text(row.audit_reason),
        "receiptResult": row.receipt_result,
        "returnCompany": row.return_company,
        "returnTrackingNo": row.return_tracking_no,
        "items": [
            {
                "id": str(line.id),
                "orderItemId": str(line.order_item_id),
                "productName": (
                    product_snapshot.get("name")
                    if isinstance(product_snapshot, dict)
                    else None
                ),
                "quantity": line.quantity,
                "goodsRefundCent": line.goods_refund_cent,
                "sellableReceivedQuantity": line.stock_return_quantity,
            }
            for line, product_snapshot in lines
        ],
        "version": row.version,
    }
    if buyer:
        snapshot = row.return_address_snapshot or {}
        address_parts = [
            snapshot.get("recipientName") or snapshot.get("name"),
            snapshot.get("phone"),
            snapshot.get("addressLine"),
            snapshot.get("instructions"),
        ]
        result["returnInstructions"] = (
            "\n".join(str(part) for part in address_parts if part)
            if row.status in {"awaiting_return", "awaiting_receipt"} and snapshot
            else None
        )
    return result


async def get_owned_aftersale(db, actor, identity):
    row = await db.scalar(
        select(MallAftersale).where(
            MallAftersale.id == identity,
            MallAftersale.buyer_user_id == actor.actor_id,
        )
    )
    if actor.actor_type != "user" or row is None:
        raise NotFoundException(message="售后记录不存在")
    return row


async def get_admin_aftersale(db, identity):
    row = await db.get(MallAftersale, identity)
    if row is None:
        raise NotFoundException(message="售后记录不存在")
    return row


async def list_buyer_aftersales(db, actor, *, cursor=None, page_size=20):
    query = select(MallAftersale).where(MallAftersale.buyer_user_id == actor.actor_id)
    rows, next_cursor, total = await _page(
        db,
        query,
        MallAftersale,
        MallAftersale.id,
        mode=f"aftersales:buyer:{actor.actor_id}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    return {
        "items": [await serialize_aftersale(db, row, buyer=True) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }


async def list_admin_aftersales(db, *, cursor=None, page_size=20, status=None):
    query = select(MallAftersale)
    if status:
        query = query.where(MallAftersale.status == status)
    rows, next_cursor, total = await _page(
        db,
        query,
        MallAftersale,
        MallAftersale.id,
        mode=f"aftersales:admin:{status or 'all'}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    return {
        "items": [await serialize_aftersale(db, row) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }
