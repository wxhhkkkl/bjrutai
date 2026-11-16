"""Buyer and automatic receipt facts, separate from platform confirmation."""

import math

from sqlalchemy import select

from ..api.mall_deps import require_mall_object_owner
from ..core.exceptions import ConflictException, NotFoundException
from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_trade import MallAftersale, MallOrder, MallShipment
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_fulfillment_service import ACTIVE_AFTERSALE_SQL, _replay_completed_command
from .mall_job_service import locked_mall_lease


async def confirm_receipt(db, actor, identity, data, *, key):
    """Buyer confirms receipt once; channel confirmation remains a separate fact."""
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == identity, MallOrder.buyer_user_id == actor.actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    require_mall_object_owner(actor, order.buyer_user_id)
    payload = {"orderId": identity, **data.model_dump(mode="json")}
    replay = await _replay_completed_command(
        db, actor, "confirmMallReceipt", key, payload, MallOrder
    )
    if replay is not None:
        return replay
    if order.version != data.expected_version:
        raise ConflictException(message="订单版本已变化，请重新读取")
    if order.status != "pending_receipt" or not order.shipped_at:
        raise ConflictException(message="订单当前不处于待收货状态")
    shipment = await db.scalar(
        select(MallShipment)
        .where(MallShipment.order_id == order.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if shipment is None:
        raise ConflictException(message="未找到有效发货记录，请联系商家核实")
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="confirmMallReceipt",
        key=key,
        payload=payload,
    )
    if not intent.created:
        raise ConflictException(message="原确认收货请求仍在处理中")
    now = utc_now()
    order.status, order.received_at = "completed", now
    order.version += 1
    db.add(
        AuditLog(
            user_id=actor.actor_id,
            action="mall_order_received",
            entity_type="mall_order",
            entity_id=str(order.id),
            detail={"shipmentId": str(shipment.id), "version": order.version},
        )
    )
    await complete_mall_command(db, intent, entity_type="mall_order", entity_id=order.id)
    await db.flush()
    return order


def fulfillment_handlers(sessions):
    """Version-fenced automatic receipt; unresolved aftersales defer it by one day."""

    async def auto_receive(item):
        from ..tasks.mall_tasks import MallJobContinuation

        if item.kind != "mall_order_auto_receive" or item.entity_type != "mall_shipment":
            raise ValueError("invalid automatic receipt work")
        async with sessions() as db:
            order_id = await db.scalar(
                select(MallShipment.order_id).where(MallShipment.id == item.entity_id)
            )
            if order_id is None:
                return
            order = await db.scalar(
                select(MallOrder)
                .where(MallOrder.id == order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not order or not await locked_mall_lease(db, item):
                return
            shipment = await db.scalar(
                select(MallShipment)
                .where(MallShipment.id == item.entity_id, MallShipment.order_id == order.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                shipment is None
                or shipment.version != item.entity_version
                or order.status != "pending_receipt"
                or not order.shipped_at
            ):
                return
            now = utc_now()
            if shipment.auto_receive_at is None:
                return
            if shipment.auto_receive_at > now:
                return MallJobContinuation(
                    max(1, math.ceil((shipment.auto_receive_at - now).total_seconds()))
                )
            active_aftersale = await db.scalar(
                select(MallAftersale.id)
                .where(MallAftersale.order_id == order.id, ACTIVE_AFTERSALE_SQL)
                .with_for_update(read=True)
                .limit(1)
                .execution_options(populate_existing=True)
            )
            if active_aftersale:
                return MallJobContinuation(24 * 60 * 60)
            order.status, order.received_at = "completed", now
            order.version += 1
            db.add(
                AuditLog(
                    user_id=None,
                    action="mall_order_auto_received",
                    entity_type="mall_order",
                    entity_id=str(order.id),
                    detail={
                        "actorType": "system",
                        "shipmentId": str(shipment.id),
                        "version": order.version,
                    },
                )
            )
            await db.commit()

    return {"mall_order_auto_receive": auto_receive}
