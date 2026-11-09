"""Persistent payment intent and verified fact application; no HTTP inside locks."""

from uuid import uuid4

from sqlalchemy import select

from ..core.config import get_settings
from ..core.exceptions import ConflictException, ValidationException
from ..models.mall_base import utc_now
from ..models.mall_finance import MallPayment
from .mall_address_service import lock_buyer
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_job_service import enqueue_mall_job
from .mall_order_service import audit_order, owned_order


async def prepare_payment(db, actor, identity, data, *, key):
    await lock_buyer(db, actor)
    order = await owned_order(db, actor, identity, lock=True)
    if order.close_requested_at:
        raise ConflictException(message="订单正在核实关闭，请查询原订单")
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="prepareMallPayment",
        key=key,
        payload={"orderId": identity, **data.model_dump(mode="json")},
    )
    if not intent.created:
        if intent.command.status != "completed":
            raise ConflictException(message="原支付请求仍在处理中")
        payment = await db.get(MallPayment, intent.command.entity_id, populate_existing=True)
        if not payment or payment.order_id != order.id:
            raise ConflictException(message="原支付请求不一致")
        return payment
    if (
        order.version != data.expected_version
        or order.status != "pending_payment"
        or order.paid_amount_cent
    ):
        raise ConflictException(message="订单版本或付款状态已变化")
    # The parent order is locked. Do not gap-lock an absent child range: distinct
    # first-time payments could otherwise deadlock while inserting each other.
    if order.active_payment_id:
        history = (
            await db.scalars(
                select(MallPayment)
                .where(MallPayment.id == order.active_payment_id, MallPayment.order_id == order.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        if not history:
            raise ConflictException(message="活动支付关联不一致，请核实原请求")
    else:
        known_ids = (
            await db.scalars(select(MallPayment.id).where(MallPayment.order_id == order.id))
        ).all()
        history = (
            (
                await db.scalars(
                    select(MallPayment)
                    .where(MallPayment.id.in_(known_ids))
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
            if known_ids
            else []
        )
    if history:
        active = [payment for payment in history if payment.active_slot == 1]
        if len(active) != 1 or active[0].status in {"succeeded", "closed", "failed"}:
            raise ConflictException(message="原支付请求需先核实，不能另建付款请求")
        payment = active[0]
        if order.active_payment_id != payment.id:
            order.active_payment_id = payment.id
            order.version += 1
    else:
        if order.expires_at <= utc_now():
            raise ConflictException(message="付款期限已过，请先核实关闭原订单")
        settings = get_settings()
        if not settings.wechat_app_id or not settings.mall_wechat_mchid:
            raise ValidationException(message="商城支付主体尚未配置")
        payment = MallPayment(
            order_id=order.id,
            out_trade_no="P" + uuid4().hex[:31],
            amount_cent=order.payable_amount_cent,
            appid_snapshot=settings.wechat_app_id,
            mchid_snapshot=settings.mall_wechat_mchid,
            expires_at=order.expires_at,
            status="creating",
        )
        db.add(payment)
        await db.flush()
        order.active_payment_id = payment.id
        order.version += 1
        await enqueue_mall_job(
            db,
            kind="mall_payment_create",
            entity_type="mall_payment",
            entity_id=payment.id,
            entity_version=payment.version,
            dedupe_key=f"mall-payment-create:{payment.id}",
        )
        audit_order(db, actor, order, "mall_payment_prepared")
    await complete_mall_command(db, intent, entity_type="mall_payment", entity_id=payment.id)
    await db.flush()
    return payment


async def apply_verified_payment(db, identity, fact):
    from .mall_payment_facts_service import apply_verified_payment as apply

    return await apply(db, identity, fact)


async def apply_verified_close(db, identity, fact):
    from .mall_payment_facts_service import apply_verified_close as apply

    return await apply(db, identity, fact)
