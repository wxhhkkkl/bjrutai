"""Owned durable preparation and fresh invocation from an encrypted verified prepay."""

from fastapi import APIRouter, Depends, Header, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, get_mall_buyer
from ...core.exceptions import NotFoundException
from ...integrations.wechat_pay_types import PaymentGatewayError
from ...models.mall_base import utc_now
from ...models.mall_finance import MallPayment
from ...schemas.mall_catalog import VersionAction
from ...services.mall_order_service import audit_order, owned_order
from ...services.mall_payment_runtime import payment_runtime
from ...services.mall_payment_service import prepare_payment
from .mall_checkout import response

router = APIRouter(prefix="/mall/orders", tags=["mall-payments"])


def payment_view(payment, order):
    return {
        "id": str(payment.id),
        "orderId": str(order.id),
        "outTradeNo": payment.out_trade_no,
        "channelTransactionId": payment.channel_transaction_id,
        "amountCent": payment.amount_cent,
        "refundedAmountCent": order.refunded_goods_cent + order.refunded_freight_cent,
        "status": payment.status,
        "confirmedAt": payment.confirmed_at.isoformat() + "Z" if payment.confirmed_at else None,
        "lastErrorCode": payment.last_error_code,
        "version": payment.version,
    }


@router.post("/{orderId}/payment", operation_id="prepareMallPayment")
async def prepare(
    body: VersionAction,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        payment = await prepare_payment(db, actor, identity, body, key=key)
        order = await owned_order(db, actor, identity)
        result = {"payment": payment_view(payment, order), "canInvoke": False, "invokeParams": None}
        if (
            payment.status == "pending"
            and payment.prepay_ciphertext
            and order.status == "pending_payment"
            and not order.close_requested_at
            and not order.paid_amount_cent
            and order.active_payment_id == payment.id
            and min(payment.expires_at, order.expires_at) > utc_now()
        ):
            try:
                gateway, vault = payment_runtime(payment)
                result["invokeParams"] = gateway.invocation(vault.open(payment))
                result["canInvoke"] = True
                audit_order(db, actor, order, "mall_payment_invocation_issued")
            except PaymentGatewayError:
                # The durable command remains usable; never leak decryption/config errors.
                pass
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.get("/{orderId}/payment", operation_id="getMallPayment")
async def get_payment(
    identity: int = Path(alias="orderId", gt=0),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    order = await owned_order(db, actor, identity)
    history = (
        await db.scalars(
            select(MallPayment)
            .where(MallPayment.order_id == order.id)
            .order_by(MallPayment.id.desc())
            .execution_options(populate_existing=True)
        )
    ).all()
    payment = next(
        (row for row in history if row.id == order.active_payment_id),
        history[0] if history else None,
    )
    if payment is None:
        raise NotFoundException(message="订单尚未创建支付请求")
    result = payment_view(payment, order)
    audit_order(db, actor, order, "mall_payment_read")
    await db.commit()
    return response(result)
