"""Safe admin order projections; no generic user or raw audit serialization."""

from datetime import datetime, timezone

from sqlalchemy import select

from ..core.exceptions import ValidationException
from ..models.audit import AuditLog
from ..models.mall_trade import MallOrder, MallShipment
from ..models.user import User
from .mall_admin_order_service import admin_order
from .mall_audit_service import record_mall_admin_audit
from .mall_catalog_query_service import _page
from .mall_command_service import canonical_payload_hash
from .mall_fulfillment_service import check_fulfillment
from .mall_order_query_service import _relations, serialize_order, timestamp
from .mall_order_text import safe_order_text


def parse_filter_time(value):
    if not value:
        return None
    try:
        if "T" not in value:
            raise ValueError()
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        raise ValidationException(message="查询时间须包含日期、时间及时区") from None


async def list_admin_orders(
    db,
    actor,
    *,
    cursor=None,
    page_size=20,
    status=None,
    order_no=None,
    pending_platform_report=None,
    from_time=None,
    to_time=None,
):
    start, end = parse_filter_time(from_time), parse_filter_time(to_time)
    if start and end and start >= end:
        raise ValidationException(message="开始时间必须早于结束时间")
    query = select(MallOrder)
    if status:
        query = query.where(MallOrder.status == status)
    if order_no:
        query = query.where(MallOrder.order_no == order_no)
    if pending_platform_report is True:
        query = query.where(
            MallOrder.id.in_(
                select(MallShipment.order_id).where(
                    MallShipment.platform_report_status.in_({"pending", "unknown"})
                )
            )
        )
    elif pending_platform_report is False:
        query = query.where(
            MallOrder.id.in_(
                select(MallShipment.order_id).where(
                    MallShipment.platform_report_status == "manual_reported"
                )
            )
        )
    if start:
        query = query.where(MallOrder.created_at >= start)
    if end:
        query = query.where(MallOrder.created_at < end)
    digest = canonical_payload_hash(
        {
            "status": status,
            "orderNo": order_no,
            "pendingPlatformReport": pending_platform_report,
            "from": start.isoformat() if start else None,
            "to": end.isoformat() if end else None,
        }
    )
    rows, next_cursor, total = await _page(
        db,
        query,
        MallOrder,
        MallOrder.id,
        mode=f"admin-orders:{actor.actor_id}:{digest}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    related = await _relations(db, rows)
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_orders_read",
        entity_type="mall_order",
        entity_id=None,
        detail={
            "count": len(rows),
            "filterDigest": digest,
            "orderIds": [str(row.id) for row in rows],
        },
    )
    return {
        "items": [await serialize_order(db, row, relations=related) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }


async def get_admin_order(db, actor, identity):
    order = await admin_order(db, identity)
    result = await serialize_order(db, order, detail=True)
    buyer = await db.get(User, order.buyer_user_id)
    result["buyer"] = {
        "id": str(order.buyer_user_id),
        "displayName": safe_order_text(
            (buyer.name if buyer else None) or f"用户{order.buyer_user_id}"
        )[:64],
    }
    result["internalNote"] = safe_order_text(order.internal_note)
    fulfillment_check = await check_fulfillment(db, order)
    result["fulfillmentCheck"] = fulfillment_check
    result["availableActions"] = []
    if "mall.orders.write" in actor.permissions:
        result["availableActions"].append("noteMallOrder")
        if (
            order.status == "pending_payment"
            and not order.paid_amount_cent
            and not order.close_requested_at
        ):
            result["availableActions"].append("cancelAdminMallOrder")
    if "mall.shipments.write" in actor.permissions:
        if fulfillment_check["businessReady"]:
            result["availableActions"].append("shipMallOrder")
        if order.status == "pending_receipt" and result["shipment"]:
            result["availableActions"].append("correctMallTracking")
        if (
            result["shipment"]
            and result["shipment"]["platformReportStatus"] != "manual_reported"
        ):
            result["availableActions"].append("recordMallPlatformShipmentReport")
    notes = (
        await db.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "mall_order",
                AuditLog.entity_id == str(order.id),
                AuditLog.action == "mall_admin_order_note",
            )
            .order_by(AuditLog.created_at, AuditLog.id)
        )
    ).all()
    result["timeline"].extend(
        {
            "id": str(event.id),
            "action": "internal_note_updated",
            "label": "更新内部备注",
            "occurredAt": timestamp(event.created_at),
            "actorLabel": "后台人员",
            "reason": None,
        }
        for event in notes
    )
    result["timeline"].sort(key=lambda e: (e["occurredAt"], int(e["id"])))
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_order_read",
        entity_type="mall_order",
        entity_id=str(order.id),
        detail={"version": order.version},
    )
    return result
