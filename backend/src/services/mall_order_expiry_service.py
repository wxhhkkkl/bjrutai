"""Due order closure works without buyer activation or enabled money transport."""

import math

from sqlalchemy import select

from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_trade import MallOrder
from ..tasks.mall_tasks import MallJobContinuation
from .mall_job_service import locked_mall_lease
from .mall_order_action_service import request_close_locked


def order_handlers(sessions):
    async def expire(item):
        if item.kind != "mall_order_expire" or item.entity_type != "mall_order":
            raise ValueError("invalid order expiry work")
        async with sessions() as db:
            order = await db.scalar(
                select(MallOrder)
                .where(MallOrder.id == item.entity_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not order or not await locked_mall_lease(db, item):
                return
            if order.status != "pending_payment" or order.paid_amount_cent:
                return
            if order.expires_at > utc_now():
                return MallJobContinuation(
                    max(1, math.ceil((order.expires_at - utc_now()).total_seconds()))
                )
            await request_close_locked(db, order, reason="付款期限届满")
            if order.status != "closed":
                db.add(
                    AuditLog(
                        user_id=None,
                        action="mall_order_expiry_close_requested",
                        entity_type="mall_order",
                        entity_id=str(order.id),
                        detail={"actorType": "system", "version": order.version},
                    )
                )
            await db.commit()

    return {"mall_order_expire": expire}
