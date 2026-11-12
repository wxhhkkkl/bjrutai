"""Internal fact application. Only the verified adapter or verified inbox may call it."""

from datetime import datetime, timedelta

from sqlalchemy import select

from ..core.exceptions import ConflictException, NotFoundException
from ..integrations.wechat_pay_types import PaymentFact, VerifiedClose
from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_finance import MallPayment
from ..models.mall_trade import MallOrder
from ..models.user import User
from .mall_consumption_service import record_paid_order
from .mall_funds_state import clear_funds_unknown, mark_funds_unknown
from .mall_job_service import enqueue_mall_job
from .mall_notification_service import notify_mall_buyer
from .mall_payment_stock_service import is_reserved, locked_stock, stock_event


async def locked_payment(db, identity):
    order_id = await db.scalar(select(MallPayment.order_id).where(MallPayment.id == identity))
    if order_id is None:
        raise NotFoundException(message="支付记录不存在")
    order = (
        await db.scalars(
            select(MallOrder)
            .where(MallOrder.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()
    payment = (
        await db.scalars(
            select(MallPayment)
            .where(MallPayment.id == identity)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()
    return order, payment


def audit_payment(db, order, payment, action):
    db.add(
        AuditLog(
            user_id=None,
            action=action,
            entity_type="mall_order",
            entity_id=str(order.id),
            detail={"actorType": "system", "paymentId": str(payment.id), "status": payment.status},
        )
    )


async def manual_exception(db, order, payment, code):
    payment.last_error_code = code
    job = await enqueue_mall_job(
        db,
        kind="mall_paid_order_exception",
        entity_type="mall_order",
        entity_id=order.id,
        entity_version=order.version,
        dedupe_key=f"mall-paid-exception:{payment.id}",
    )
    job.status, job.last_error_code = "manual", code


async def apply_verified_payment(db, identity, fact, *, payer_identity_verified=False):
    order, payment = await locked_payment(db, identity)
    if (
        not isinstance(fact, PaymentFact)
        or (fact.appid, fact.mchid, fact.out_trade_no, fact.currency, fact.total_cent)
        != (
            payment.appid_snapshot,
            payment.mchid_snapshot,
            payment.out_trade_no,
            "CNY",
            payment.amount_cent,
        )
        or type(fact.total_cent) is not int
        or payment.amount_cent != order.payable_amount_cent
    ):
        raise ConflictException(message="支付主体、币种、身份或金额不匹配")
    if fact.state == "SUCCESS":
        buyer = await db.get(User, order.buyer_user_id, populate_existing=True)
        if (
            not isinstance(fact.paid_at, datetime)
            or fact.paid_at.tzinfo is not None
            or fact.paid_at < order.created_at - timedelta(minutes=5)
            or fact.paid_at > utc_now() + timedelta(minutes=5)
            or not isinstance(fact.transaction_id, str)
            or not 0 < len(fact.transaction_id) <= 64
            or type(fact.payer_total_cent) is not int
            or fact.payer_total_cent != payment.amount_cent
            or not buyer
            or not buyer.openid
            or (not payer_identity_verified and fact.openid != buyer.openid)
        ):
            raise ConflictException(message="支付付款人、实付金额、时间或渠道身份需核实")
        if payment.status == "succeeded":
            if payment.channel_transaction_id != fact.transaction_id or (
                order.active_payment_id == payment.id and order.paid_at != fact.paid_at
            ):
                raise ConflictException(message="同一支付请求出现不同成功身份")
            return payment
        duplicate = order.paid_amount_cent > 0
        clear_funds_unknown(payment)
        payment.status, payment.channel_transaction_id = "succeeded", fact.transaction_id
        payment.active_slot, payment.confirmed_at, payment.last_query_at = (
            None,
            utc_now(),
            utc_now(),
        )
        payment.version += 1
        if duplicate:
            await manual_exception(db, order, payment, "duplicate_payment_requires_manual_refund")
        else:
            items, skus = await locked_stock(db, order)
            fulfillable = order.status == "pending_payment" and is_reserved(items, skus)
            order.paid_amount_cent, order.paid_at, order.active_payment_id = (
                payment.amount_cent,
                fact.paid_at,
                payment.id,
            )
            order.version += 1
            if fulfillable:
                stock_event(db, order, payment, items, skus, release=False)
                order.status, payment.last_error_code = "pending_shipment", None
            else:
                order.status, order.closed_at = "closed", order.closed_at or utc_now()
                order.close_reason = "已收款无法正常履约，待人工原路退款核实"
                await manual_exception(db, order, payment, "paid_order_requires_manual_refund")
            await record_paid_order(db, order)
        audit_payment(db, order, payment, "mall_payment_succeeded")
        if not duplicate:
            status_text = (
                (
                    "订单正在等待商家交付。"
                    if (order.policy_snapshot or {}).get("deliveryMethod") == "virtual"
                    else "订单正在等待发货。"
                )
                if order.status == "pending_shipment"
                else "订单情况需要商家核实。"
            )
            await notify_mall_buyer(
                db,
                buyer_user_id=order.buyer_user_id,
                event_key=f"mall:payment:{payment.id}:succeeded",
                title="商城支付结果已确认",
                summary=f"订单号 {order.order_no} 的支付已核实，{status_text}",
                target=f"/pages/mall-order-detail/index?id={order.id}",
            )
    elif payment.status not in {"succeeded", "closed"}:
        if fact.state == "CLOSED":
            return await apply_verified_close(
                db, identity, VerifiedClose(fact.out_trade_no, fact.mchid)
            )
        observed_at = utc_now()
        payment.status = "pending" if fact.state in {"NOTPAY", "USERPAYING"} else "unknown"
        if payment.status == "unknown":
            mark_funds_unknown(payment, now=observed_at)
        else:
            clear_funds_unknown(payment)
        payment.last_query_at, payment.version = observed_at, payment.version + 1
        payment.last_error_code = (
            None if payment.status == "pending" else "payment_requires_reconciliation"
        )
    await db.flush()
    return payment


async def apply_verified_close(db, identity, fact):
    order, payment = await locked_payment(db, identity)
    if not isinstance(fact, VerifiedClose) or (fact.out_trade_no, fact.mchid) != (
        payment.out_trade_no,
        payment.mchid_snapshot,
    ):
        raise ConflictException(message="渠道关单身份不匹配")
    if payment.status == "succeeded" or order.paid_amount_cent:
        return payment
    if payment.status == "closed" and order.status == "closed":
        return payment
    other = await db.scalar(
        select(MallPayment.id)
        .where(
            MallPayment.order_id == order.id,
            MallPayment.id != payment.id,
            MallPayment.active_slot == 1,
        )
        .with_for_update()
    )
    if other is not None:
        raise ConflictException(message="订单还有其他活动支付请求，不能释放库存")
    items, skus = await locked_stock(db, order)
    if order.status != "closed":
        if order.status != "pending_payment":
            raise ConflictException(message="业务订单状态不允许未付关单")
        stock_event(db, order, payment, items, skus, release=True)
        order.status, order.closed_at, order.close_reason = (
            "closed",
            utc_now(),
            "渠道核实未付并关闭",
        )
        order.active_payment_id = None
        order.version += 1
    clear_funds_unknown(payment)
    payment.status, payment.active_slot, payment.confirmed_at = "closed", None, utc_now()
    payment.last_query_at, payment.version = utc_now(), payment.version + 1
    audit_payment(db, order, payment, "mall_payment_closed")
    await db.flush()
    return payment
