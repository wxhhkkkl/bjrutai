"""Conservative local close: any channel attempt must use channel reconciliation."""

from sqlalchemy import select

from ..core.exceptions import ConflictException
from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_catalog import MallSku, MallStockMovement
from ..models.mall_finance import MallPayment
from ..models.mall_trade import MallOrderItem
from .mall_address_service import lock_buyer
from .mall_order_service import _current, audit_order, owned_order


async def close_never_paid_order(db, actor, identity, *, expected_version):
    await lock_buyer(db, actor)
    order = await owned_order(db, actor, identity, lock=True)
    if order.status == "closed" and order.paid_amount_cent == 0:
        return order
    if (
        order.status != "pending_payment"
        or order.version != expected_version
        or order.paid_amount_cent
    ):
        raise ConflictException(message="订单状态或版本已变化")
    return await close_unattempted_locked(db, order, actor=actor)


async def payment_history(db, order):
    """Caller holds the parent order lock; current read sees all attempt history."""
    return (
        await db.scalars(
            select(MallPayment)
            .where(MallPayment.order_id == order.id)
            .order_by(MallPayment.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()


async def close_unattempted_locked(db, order, *, actor=None):
    if order.status == "closed" and not order.paid_amount_cent:
        return order
    if order.status != "pending_payment" or order.paid_amount_cent:
        raise ConflictException(message="订单状态不允许未付关闭")
    attempt = await db.scalar(
        select(MallPayment.id).where(MallPayment.order_id == order.id).limit(1).with_for_update()
    )
    if order.active_payment_id is not None or attempt is not None:
        raise ConflictException(message="存在渠道付款请求，须先核实渠道状态，不能本地释放库存")
    items = (
        await db.scalars(
            select(MallOrderItem)
            .where(MallOrderItem.order_id == order.id)
            .order_by(MallOrderItem.sku_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    for item in items:
        sku = await _current(db, MallSku, item.sku_id, write=True)
        if item.reservation_status != "reserved" or sku.reserved_qty < item.quantity:
            raise ConflictException(message="库存占用事实不一致，请人工核对")
        before = {"available": sku.available_qty, "reserved": sku.reserved_qty}
        sku.reserved_qty -= item.quantity
        sku.available_qty += item.quantity
        sku.version += 1
        item.reservation_status = "released"
        item.version += 1
        db.add(
            MallStockMovement(
                sku_id=sku.id,
                order_item_id=item.id,
                kind="release",
                event_key=f"order:{order.id}:release:{sku.id}",
                available_delta=item.quantity,
                reserved_delta=-item.quantity,
                before=before,
                after={"available": sku.available_qty, "reserved": sku.reserved_qty},
                actor_type=actor.actor_type if actor else "system",
                actor_id=actor.actor_id if actor else 0,
                reason="未发起付款订单关闭释放",
            )
        )
    order.status, order.closed_at, order.close_reason = "closed", utc_now(), "未发起付款订单关闭"
    order.version += 1
    if actor and actor.actor_type == "user":
        audit_order(db, actor, order, "mall_order_closed")
    elif actor and actor.actor_type == "admin":
        from .mall_audit_service import record_mall_admin_audit

        await record_mall_admin_audit(
            db,
            actor=actor,
            action="mall_admin_order_closed",
            entity_type="mall_order",
            entity_id=str(order.id),
            detail={"version": order.version},
        )
    else:
        db.add(
            AuditLog(
                user_id=None,
                action="mall_order_expired",
                entity_type="mall_order",
                entity_id=str(order.id),
                detail={"actorType": "system", "version": order.version},
            )
        )
    await db.flush()
    return order
