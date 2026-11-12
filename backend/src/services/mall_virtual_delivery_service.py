"""Authorized, one-time manual delivery for paid virtual-product orders."""

from sqlalchemy import select

from ..api.mall_deps import require_mall_admin_permission
from ..core.exceptions import ConflictException, ForbiddenException, NotFoundException
from ..models.mall_base import utc_now
from ..models.mall_trade import MallOrder, MallVirtualDelivery
from ..schemas.mall_fulfillment import VirtualDeliveryCreate
from .mall_audit_service import record_mall_admin_audit
from .mall_command_service import (
    canonical_payload_hash,
    complete_mall_command,
    reserve_mall_command,
)
from .mall_fulfillment_service import _replay_completed_command, check_fulfillment
from .mall_notification_service import notify_mall_buyer


async def deliver_virtual_order(db, actor, identity, data: VirtualDeliveryCreate, *, key):
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台授权人员可交付虚拟商品")
    actor = await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        "mall.orders.write",
        current=True,
    )
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    payload = {"orderId": identity, **data.model_dump(mode="json")}
    replay = await _replay_completed_command(
        db, actor, "deliverVirtualMallOrder", key, payload, MallVirtualDelivery
    )
    if replay is not None:
        if replay.order_id != order.id:
            raise ConflictException(message="原交付请求关联不一致")
        return replay
    if order.version != data.expected_version:
        raise ConflictException(message="订单版本已变化，请重新读取订单")
    if (order.policy_snapshot or {}).get("deliveryMethod") != "virtual":
        raise ConflictException(message="该订单不是虚拟商品订单")
    content = data.delivery_content.strip()
    if not content:
        raise ConflictException(message="请填写虚拟商品交付内容")
    check = await check_fulfillment(db, order, lock=True)
    if not check["businessReady"]:
        messages = "; ".join(reason["message"] for reason in check["blockingReasons"])
        raise ConflictException(message=f"订单当前不能交付：{messages}")

    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="deliverVirtualMallOrder",
        key=key,
        payload=payload,
    )
    if not intent.created:
        raise ConflictException(message="原交付请求仍在处理中，请查询原请求")
    now = utc_now()
    delivery = MallVirtualDelivery(
        order_id=order.id,
        delivery_content=content,
        delivered_by=actor.actor_id,
        delivered_at=now,
    )
    db.add(delivery)
    order.status = "completed"
    order.received_at = now
    order.version += 1
    await db.flush()
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_virtual_delivered",
        entity_type="mall_order",
        entity_id=str(order.id),
        detail={
            "deliveryId": str(delivery.id),
            "orderVersion": order.version,
            "deliveryContentDigest": canonical_payload_hash({"content": content}),
        },
    )
    await notify_mall_buyer(
        db,
        buyer_user_id=order.buyer_user_id,
        event_key=f"mall:virtual-delivery:{delivery.id}:created",
        title="虚拟商品已交付",
        summary=f"订单号 {order.order_no} 已交付，可在订单详情查看内容。",
        target=f"/pages/mall-order-detail/index?id={order.id}",
    )
    await complete_mall_command(
        db,
        intent,
        entity_type="mall_virtual_delivery",
        entity_id=delivery.id,
    )
    await db.flush()
    return delivery
