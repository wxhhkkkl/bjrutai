"""Safe, permission-scoped payment and refund ledger projections."""

from sqlalchemy import case, func, select

from ..api.mall_deps import MallActor, require_mall_admin_permission
from ..core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ..models.mall_finance import MallPayment, MallRefund
from ..models.mall_operations import MallJob
from ..models.mall_trade import MallOrder
from ..models.user import User
from ..schemas.mall_catalog import VersionAction
from .mall_admin_order_query_service import parse_filter_time
from .mall_audit_service import record_mall_admin_audit
from .mall_catalog_query_service import _page
from .mall_command_service import (
    canonical_payload_hash,
    complete_mall_command,
    reserve_mall_command,
)
from .mall_job_service import enqueue_mall_job
from .mall_order_query_service import timestamp
from .mall_order_text import safe_order_text
from .mall_payment_facts_service import locked_payment


def _require_read(actor: MallActor):
    if actor.actor_type != "admin" or "mall.payments.read" not in actor.permissions:
        raise ForbiddenException(message="缺少商城权限: mall.payments.read")


def _require_refund_read(actor: MallActor):
    if actor.actor_type != "admin" or "mall.refunds.read" not in actor.permissions:
        raise ForbiddenException(message="缺少商城权限: mall.refunds.read")


def _payment_query_result(command, payment, job):
    status = {
        "ready": "pending",
        "retry": "pending",
        "running": "running",
        "manual": "manual",
        "done": "completed",
    }.get(job.status, "manual")
    return {
        "commandId": str(command.id),
        "jobId": str(job.id),
        "entityId": str(payment.id),
        "status": status,
        "version": payment.version,
    }


async def queue_admin_payment_query(
    db, actor: MallActor, identity: int, data: VersionAction, *, key: str
):
    """Queue one signed read of the original payment number; never create a new payment."""
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台资金核对人员可查证支付")
    actor = await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        "mall.payments.query",
        current=True,
    )
    _order, payment = await locked_payment(db, identity)
    payload = {"paymentId": identity, **data.model_dump(mode="json")}
    reservation = await reserve_mall_command(
        db, actor=actor, action="queryMallPayment", key=key, payload=payload
    )
    command = reservation.command
    if not reservation.created:
        if command.status != "completed" or command.entity_type != "mall_payment":
            raise ConflictException(message="原支付查证请求仍在处理中")
        if command.entity_id != payment.id:
            raise ConflictException(message="原支付查证请求关联不一致")
        job = await db.scalar(
            select(MallJob).where(
                MallJob.dedupe_key == f"mall-payment-query:{payment.id}:{command.id}"
            )
        )
        if job is None:
            raise ConflictException(message="原支付查证工作项不存在")
        return _payment_query_result(command, payment, job)

    if payment.version != data.expected_version:
        raise ConflictException(message="支付版本已变化，请重新读取")
    if payment.status not in {"creating", "pending", "unknown"}:
        raise ConflictException(message="当前支付状态不需要自动查证")

    job = await enqueue_mall_job(
        db,
        kind="mall_payment_query",
        entity_type="mall_payment",
        entity_id=payment.id,
        entity_version=payment.version,
        dedupe_key=f"mall-payment-query:{payment.id}:{command.id}",
    )
    await complete_mall_command(
        db,
        reservation,
        entity_type="mall_payment",
        entity_id=payment.id,
        result_code="scheduled",
    )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_payment_query_requested",
        entity_type="mall_payment",
        entity_id=str(payment.id),
        detail={"orderId": str(payment.order_id), "version": payment.version},
    )
    return _payment_query_result(command, payment, job)


def _refund_sum(payment_id):
    return (
        select(func.coalesce(func.sum(MallRefund.total_cent), 0))
        .where(MallRefund.payment_id == payment_id, MallRefund.status == "succeeded")
        .scalar_subquery()
    )


def _payment_view(
    payment,
    *,
    order_no,
    buyer_id,
    buyer_name,
    goods_cent,
    freight_cent,
    refund_cent,
    detail=False,
):
    net = payment.amount_cent - refund_cent if payment.status == "succeeded" else None
    result = {
        "id": str(payment.id),
        "orderId": str(payment.order_id),
        "orderNo": order_no,
        "buyer": {
            "id": str(buyer_id),
            "displayName": safe_order_text(buyer_name or f"用户{buyer_id}")[:64],
        },
        "outTradeNo": payment.out_trade_no,
        "amountCent": payment.amount_cent,
        "goodsAmountCent": goods_cent,
        "freightAmountCent": freight_cent,
        "currency": payment.currency,
        "refundSucceededCent": refund_cent,
        "netReceivedCent": net,
        "status": payment.status,
        "createdAt": timestamp(payment.created_at),
        "confirmedAt": timestamp(payment.confirmed_at),
        "lastQueryAt": timestamp(payment.last_query_at),
        "lastErrorCode": payment.last_error_code,
        "version": payment.version,
    }
    if detail:
        result["channelTransactionId"] = payment.channel_transaction_id
    return result


async def _payment_projection_rows(db, identities):
    if not identities:
        return {}
    statement = (
        select(
            MallPayment,
            MallOrder.order_no,
            MallOrder.buyer_user_id,
            User.name,
            MallOrder.goods_amount_cent,
            MallOrder.freight_amount_cent,
            _refund_sum(MallPayment.id).label("refund_succeeded_cent"),
        )
        .join(MallOrder, MallOrder.id == MallPayment.order_id)
        .join(User, User.id == MallOrder.buyer_user_id)
        .where(MallPayment.id.in_(identities))
    )
    rows = (await db.execute(statement)).all()
    return {
        payment.id: (
            payment,
            order_no,
            buyer_id,
            name,
            goods_cent,
            freight_cent,
            int(refund_cent or 0),
        )
        for payment, order_no, buyer_id, name, goods_cent, freight_cent, refund_cent in rows
    }


async def list_admin_payments(
    db,
    actor: MallActor,
    *,
    cursor=None,
    page_size=20,
    status=None,
    order_no=None,
    from_time=None,
    to_time=None,
):
    """Page payment attempts by creation time; only successful facts count as money."""
    _require_read(actor)
    start, end = parse_filter_time(from_time), parse_filter_time(to_time)
    if start and end and start >= end:
        raise ValidationException(message="开始时间必须早于结束时间")
    event_time = case(
        (MallPayment.status == "succeeded", MallPayment.confirmed_at),
        else_=MallPayment.created_at,
    )
    query = select(MallPayment).join(MallOrder, MallOrder.id == MallPayment.order_id)
    if status:
        query = query.where(MallPayment.status == status)
    if order_no:
        query = query.where(MallOrder.order_no == order_no)
    if start:
        query = query.where(event_time >= start)
    if end:
        query = query.where(event_time < end)
    filter_key = f"payments:{status or 'all'}:{order_no or ''}:{start or ''}:{end or ''}"
    rows, next_cursor, total = await _page(
        db,
        query,
        MallPayment,
        MallPayment.id,
        mode=f"admin-mall-payments:{actor.actor_id}:{filter_key}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    projection = await _payment_projection_rows(db, [row.id for row in rows])
    items = []
    for row in rows:
        projected = projection.get(row.id)
        if projected is None:
            continue
        payment, related_order_no, buyer_id, buyer_name, goods_cent, freight_cent, refund_cent = (
            projected
        )
        items.append(
            _payment_view(
                payment,
                order_no=related_order_no,
                buyer_id=buyer_id,
                buyer_name=buyer_name,
                goods_cent=goods_cent,
                freight_cent=freight_cent,
                refund_cent=refund_cent,
            )
        )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_payments_read",
        entity_type="mall_payment",
        entity_id=None,
        detail={
            "count": len(items),
            "paymentIds": [item["id"] for item in items],
            "filterDigest": canonical_payload_hash(
                {
                    "status": status,
                    "orderNo": order_no,
                    "from": start.isoformat() if start else None,
                    "to": end.isoformat() if end else None,
                }
            ),
        },
    )
    return {"items": items, "nextCursor": next_cursor, "total": total}


async def get_admin_payment(db, actor: MallActor, identity: int):
    _require_read(actor)
    projection = await _payment_projection_rows(db, [identity])
    row = projection.get(identity)
    if row is None:
        raise NotFoundException(message="支付记录不存在")
    payment, order_no, buyer_id, buyer_name, goods_cent, freight_cent, refund_cent = row
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_payment_read",
        entity_type="mall_payment",
        entity_id=str(payment.id),
        detail={"version": payment.version, "status": payment.status},
    )
    return _payment_view(
        payment,
        order_no=order_no,
        buyer_id=buyer_id,
        buyer_name=buyer_name,
        goods_cent=goods_cent,
        freight_cent=freight_cent,
        refund_cent=refund_cent,
        detail=True,
    )


async def list_admin_finance_refunds(
    db,
    actor: MallActor,
    *,
    cursor=None,
    page_size=20,
    status=None,
    order_no=None,
    from_time=None,
    to_time=None,
):
    """Page refunds separately; successful rows use confirmation time."""
    _require_refund_read(actor)
    start, end = parse_filter_time(from_time), parse_filter_time(to_time)
    if start and end and start >= end:
        raise ValidationException(message="开始时间必须早于结束时间")
    query = select(MallRefund)
    if order_no:
        query = query.join(MallOrder, MallOrder.id == MallRefund.order_id).where(
            MallOrder.order_no == order_no
        )
    if status:
        query = query.where(MallRefund.status == status)
    event_time = case(
        (MallRefund.status == "succeeded", MallRefund.confirmed_at),
        else_=MallRefund.created_at,
    )
    if start:
        query = query.where(event_time >= start)
    if end:
        query = query.where(event_time < end)
    filter_key = f"refunds:{status or 'all'}:{order_no or ''}:{start or ''}:{end or ''}"
    rows, next_cursor, total = await _page(
        db,
        query,
        MallRefund,
        MallRefund.id,
        mode=f"admin-mall-refunds:{actor.actor_id}:{filter_key}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    from .mall_aftersale_query_service import serialize_refund

    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_refunds_read",
        entity_type="mall_refund",
        entity_id=None,
        detail={
            "count": len(rows),
            "refundIds": [str(row.id) for row in rows],
            "filterDigest": canonical_payload_hash(
                {
                    "status": status,
                    "orderNo": order_no,
                    "from": start.isoformat() if start else None,
                    "to": end.isoformat() if end else None,
                }
            ),
        },
    )
    return {
        "items": [serialize_refund(row) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }
