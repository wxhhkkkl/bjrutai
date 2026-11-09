"""Admin order writes are reauthorized, versioned and audited in the caller transaction."""

from sqlalchemy import select

from ..api.mall_deps import require_mall_admin_permission
from ..core.exceptions import ConflictException, ForbiddenException, NotFoundException
from ..models.mall_trade import MallOrder
from .mall_audit_service import record_mall_admin_audit
from .mall_command_service import (
    canonical_payload_hash,
    complete_mall_command,
    reserve_mall_command,
)
from .mall_order_action_service import request_close_locked


async def admin_order(db, identity, *, lock=False):
    query = (
        select(MallOrder).where(MallOrder.id == identity).execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    order = await db.scalar(query)
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    return order


async def mutate_admin_order(db, actor, identity, data, *, key, cancel=False):
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台管理员可办理商城订单")
    actor = await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"}, db, "mall.orders.write", current=True
    )
    order = await admin_order(db, identity, lock=True)
    action = "cancelAdminMallOrder" if cancel else "noteMallOrder"
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action=action,
        key=key,
        payload={"orderId": identity, **data.model_dump(mode="json")},
    )
    if not intent.created:
        if intent.command.status != "completed":
            raise ConflictException(message="原操作仍在处理中，请查询原请求")
        return order, intent.command
    if order.version != data.expected_version:
        raise ConflictException(message="订单版本已变化，请加载最新订单")
    if cancel:
        await record_mall_admin_audit(
            db,
            actor=actor,
            action="mall_admin_cancel_requested",
            entity_type="mall_order",
            entity_id=str(order.id),
            detail={"version": order.version},
        )
        await request_close_locked(db, order, reason=data.reason, actor=actor)
    else:
        order.internal_note = data.internal_note
        order.version += 1
        await record_mall_admin_audit(
            db,
            actor=actor,
            action="mall_admin_order_note",
            entity_type="mall_order",
            entity_id=str(order.id),
            detail={
                "version": order.version,
                "noteDigest": canonical_payload_hash({"note": data.internal_note}),
            },
        )
    await complete_mall_command(db, intent, entity_type="mall_order", entity_id=order.id)
    await db.flush()
    return order, intent.command
