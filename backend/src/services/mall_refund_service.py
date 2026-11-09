"""Original-payment refunds with durable identities and verified terminal facts."""

import re
from uuid import uuid4

from sqlalchemy import select

from ..api.mall_deps import require_mall_admin_permission
from ..core.exceptions import ConflictException, ForbiddenException, NotFoundException
from ..integrations.wechat_pay_types import RefundFact
from ..models.audit import AuditLog
from ..models.mall_base import utc_now
from ..models.mall_catalog import MallSku, MallStockMovement
from ..models.mall_consumption import MallConsumption
from ..models.mall_finance import MallInvoice, MallPayment, MallRefund
from ..models.mall_operations import MallGatewayEvent, MallJob
from ..models.mall_trade import MallAftersale, MallAftersaleItem, MallOrder, MallOrderItem
from .mall_audit_service import record_mall_admin_audit
from .mall_catalog_query_service import _page
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_consumption_service import performance_base
from .mall_funds_state import clear_funds_unknown, mark_funds_unknown
from .mall_job_service import enqueue_mall_job, locked_mall_lease
from .mall_notification_service import notify_mall_buyer
from .performance_period_service import bump_period


async def _admin(db, actor, permission):
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台授权财务可处理退款")
    return await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        permission,
        current=True,
    )


async def _locked_aftersale(db, identity):
    aftersale = await db.get(MallAftersale, identity, populate_existing=True)
    if aftersale is None:
        raise NotFoundException(message="售后记录不存在")
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == aftersale.order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    aftersale = await db.scalar(
        select(MallAftersale)
        .where(MallAftersale.id == identity, MallAftersale.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if aftersale is None:
        raise NotFoundException(message="售后记录不存在")
    return order, aftersale


async def execute_refund(db, actor, identity, data, *, key):
    """Authorize and persist an original-channel refund job; no gateway I/O here."""
    actor = await _admin(db, actor, "mall.refunds.execute")
    order, aftersale = await _locked_aftersale(db, identity)
    payload = {"aftersaleId": identity, **data.model_dump(mode="json")}
    intent = await reserve_mall_command(
        db, actor=actor, action="executeMallRefund", key=key, payload=payload
    )
    if not intent.created:
        if intent.command.status != "completed" or not intent.command.entity_id:
            raise ConflictException(message="原退款请求仍在处理中，请查询退款记录")
        replay = await db.get(MallRefund, intent.command.entity_id, populate_existing=True)
        if replay is None or replay.aftersale_id != aftersale.id:
            raise ConflictException(message="原退款记录关联不一致")
        return replay

    if aftersale.version != data.expected_version:
        raise ConflictException(message="售后版本已变化，请重新读取")
    if aftersale.status not in {"awaiting_refund", "refunding"}:
        raise ConflictException(message="售后尚未达到可执行退款阶段")
    if aftersale.reserved_refund_cent <= 0:
        raise ConflictException(message="售后没有有效退款额度")
    if (
        order.refund_reserved_cent < aftersale.reserved_refund_cent
        or order.refunded_goods_cent + order.refunded_freight_cent + order.refund_reserved_cent
        > order.paid_amount_cent
    ):
        raise ConflictException(message="订单退款占用与原收款不一致，请核实")
    payment = await db.scalar(
        select(MallPayment)
        .where(MallPayment.id == order.active_payment_id, MallPayment.order_id == order.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if (
        payment is None
        or payment.status != "succeeded"
        or payment.amount_cent != order.paid_amount_cent
        or not payment.channel_transaction_id
        or order.paid_amount_cent <= 0
    ):
        raise ConflictException(message="原路退款所需收款事实不完整")
    active = await db.scalar(
        select(MallRefund)
        .where(MallRefund.aftersale_id == aftersale.id, MallRefund.active_slot == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if active is not None:
        if active.status not in {"prepared", "processing", "unknown", "abnormal"}:
            raise ConflictException(message="退款请求仍需核实，不能重复执行")
        row = active
    else:
        if aftersale.status != "awaiting_refund":
            raise ConflictException(message="售后退款阶段与有效退款请求不一致")
        previous = await db.scalar(
            select(MallRefund)
            .where(MallRefund.aftersale_id == aftersale.id)
            .order_by(MallRefund.id.desc())
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if previous is not None and previous.status not in {"closed", "rejected_unaccepted"}:
            raise ConflictException(message="上一退款请求并非明确关闭，不能另建资金请求")
        total_cent = aftersale.goods_refund_cent + aftersale.freight_refund_cent
        if total_cent != aftersale.reserved_refund_cent:
            raise ConflictException(message="售后金额占用与申请金额不一致")
        row = MallRefund(
            aftersale_id=aftersale.id,
            payment_id=payment.id,
            order_id=order.id,
            out_refund_no="R" + uuid4().hex[:31],
            predecessor_refund_id=previous.id if previous else None,
            active_slot=1,
            status="prepared",
            goods_refund_cent=aftersale.goods_refund_cent,
            freight_refund_cent=aftersale.freight_refund_cent,
            total_cent=total_cent,
            original_amount_cent=payment.amount_cent,
            requested_by=actor.actor_id,
        )
        db.add(row)
        await db.flush()
        await enqueue_mall_job(
            db,
            kind="mall_refund_execute",
            entity_type="mall_refund",
            entity_id=row.id,
            entity_version=row.version,
            dedupe_key=f"mall-refund-execute:{row.id}",
        )
    aftersale.status = "refunding"
    aftersale.version += 1
    order.version += 1
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_refund_execution_requested",
        entity_type="mall_refund",
        entity_id=str(row.id),
        detail={"aftersaleId": str(aftersale.id), "amountCent": row.total_cent},
    )
    await complete_mall_command(db, intent, entity_type="mall_refund", entity_id=row.id)
    await db.flush()
    await notify_mall_buyer(
        db,
        buyer_user_id=order.buyer_user_id,
        event_key=f"mall:refund:{row.id}:submitted",
        title="商城退款已提交",
        summary=f"订单号 {order.order_no} 的退款已提交，结果待确认。",
        target=f"/pages/mall-aftersale-detail/index?id={aftersale.id}",
    )
    return row


async def _lock_refund_context(db, identity):
    candidate = await db.get(MallRefund, identity, populate_existing=True)
    if candidate is None:
        raise NotFoundException(message="退款记录不存在")
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == candidate.order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    refund = await db.scalar(
        select(MallRefund)
        .where(MallRefund.id == identity, MallRefund.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if refund is None:
        raise NotFoundException(message="退款记录不存在")
    aftersale = await db.scalar(
        select(MallAftersale)
        .where(MallAftersale.id == refund.aftersale_id, MallAftersale.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    payment = await db.scalar(
        select(MallPayment)
        .where(MallPayment.id == refund.payment_id, MallPayment.order_id == order.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if aftersale is None or payment is None:
        raise ConflictException(message="退款关联的售后或原收款不存在")
    return order, aftersale, refund, payment


def _verify_refund_fact(order, payment, refund, fact):
    if not isinstance(fact, RefundFact) or (
        fact.out_refund_no != refund.out_refund_no
        or fact.out_trade_no != payment.out_trade_no
        or fact.total_cent != payment.amount_cent
        or fact.total_cent != refund.original_amount_cent
        or fact.refund_cent != refund.total_cent
        or fact.currency != "CNY"
        or order.id != refund.order_id
        or refund.payment_id != payment.id
        or payment.status != "succeeded"
        or payment.amount_cent != order.paid_amount_cent
        or (fact.transaction_id and payment.channel_transaction_id != fact.transaction_id)
        or fact.status not in {"SUCCESS", "CLOSED", "PROCESSING", "ABNORMAL"}
        or (fact.status == "SUCCESS" and (not fact.channel_refund_id or not fact.success_at))
    ):
        raise ConflictException(message="渠道退款事实与原订单、原支付或退款金额不匹配")


async def _manual_refund_job(db, refund, *, error_code):
    job = await enqueue_mall_job(
        db,
        kind="mall_refund_manual_review",
        entity_type="mall_refund",
        entity_id=refund.id,
        entity_version=refund.version,
        dedupe_key=f"mall-refund-manual:{refund.id}",
    )
    job.status = "manual"
    job.last_error_code = error_code
    return job


async def _record_success(db, order, aftersale, refund, payment, fact):
    if refund.status == "succeeded":
        return
    if (
        aftersale.reserved_refund_cent != refund.total_cent
        or order.refund_reserved_cent < refund.total_cent
        or order.refunded_goods_cent + refund.goods_refund_cent > order.goods_amount_cent
        or order.refunded_freight_cent + refund.freight_refund_cent > order.freight_amount_cent
    ):
        raise ConflictException(message="已确认退款超出有效售后占用，需财务人工核对")
    if refund.channel_refund_id and refund.channel_refund_id != fact.channel_refund_id:
        raise ConflictException(message="同一退款号返回了不同的渠道退款身份")
    lines = (
        await db.scalars(
            select(MallAftersaleItem)
            .where(MallAftersaleItem.aftersale_id == aftersale.id)
            .order_by(MallAftersaleItem.order_item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    order_items = (
        await db.scalars(
            select(MallOrderItem)
            .where(MallOrderItem.order_id == order.id)
            .order_by(MallOrderItem.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    by_id = {item.id: item for item in order_items}
    if sum(line.goods_refund_cent for line in lines) != refund.goods_refund_cent:
        raise ConflictException(message="退款商品金额与售后明细不一致")
    unsent = order.status == "pending_shipment" and order.shipped_at is None
    for line in lines:
        item = by_id.get(line.order_item_id)
        if (
            item is None
            or item.aftersale_reserved_quantity < line.quantity
            or item.refunded_quantity + line.quantity > item.quantity
            or item.refunded_goods_cent + line.goods_refund_cent > item.line_amount_cent
        ):
            raise ConflictException(message="退款商品数量与订单明细占用不一致")
        item.aftersale_reserved_quantity -= line.quantity
        item.refunded_quantity += line.quantity
        item.refunded_goods_cent += line.goods_refund_cent
        item.version += 1
        line.active_slot = None
        line.version += 1
        if unsent:
            sku = await db.scalar(
                select(MallSku)
                .where(MallSku.id == item.sku_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if sku is None:
                raise ConflictException(message="退款商品规格不存在")
            before = {"available": sku.available_qty, "reserved": sku.reserved_qty}
            sku.available_qty += line.quantity
            sku.version += 1
            db.add(
                MallStockMovement(
                    sku_id=sku.id,
                    event_key=f"aftersale:{line.id}:pre-shipment-refund",
                    order_item_id=item.id,
                    aftersale_item_id=line.id,
                    kind="refund_return",
                    available_delta=line.quantity,
                    reserved_delta=0,
                    before=before,
                    after={"available": sku.available_qty, "reserved": sku.reserved_qty},
                    actor_type="system",
                    actor_id=0,
                    reason="未出库商品经核实退款成功后恢复可售",
                )
            )
    order.refund_reserved_cent -= refund.total_cent
    order.refunded_goods_cent += refund.goods_refund_cent
    order.refunded_freight_cent += refund.freight_refund_cent
    if order_items and all(
        item.refunded_quantity >= item.quantity and item.aftersale_reserved_quantity == 0
        for item in order_items
    ):
        order.status = "closed"
        order.closed_at = utc_now()
        order.close_reason = "all_goods_refunded"
    order.version += 1
    aftersale.reserved_refund_cent = 0
    aftersale.status = "completed"
    aftersale.version += 1
    refund.status = "succeeded"
    clear_funds_unknown(refund)
    refund.active_slot = None
    refund.channel_refund_id = fact.channel_refund_id
    refund.confirmed_at = fact.success_at
    refund.last_query_at = utc_now()
    refund.last_error_code = None
    refund.version += 1

    source = await db.scalar(
        select(MallConsumption)
        .where(MallConsumption.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source and refund.goods_refund_cent:
        if (
            source.successful_goods_refund_cent + refund.goods_refund_cent
            > source.original_goods_cent
        ):
            raise ConflictException(message="商城绩效来源退款金额超出原商品款")
        source.successful_goods_refund_cent += refund.goods_refund_cent
        source.performance_base_cent = performance_base(
            source.original_goods_cent, source.successful_goods_refund_cent
        )
        source.source_version += 1
        source.version += 1
        period = await bump_period(db, source.business_period)
        if period.status != "open":
            job = await enqueue_mall_job(
                db,
                kind="mall_performance_refund_candidate",
                entity_type="mall_refund",
                entity_id=refund.id,
                entity_version=refund.version,
                dedupe_key=f"mall-performance-refund:{refund.id}",
            )
            job.status = "manual"
            job.last_error_code = "performance_adjustment_requires_review"

    # A successful refund changes the business facts for any invoice that still
    # has live coverage. Keep the tax follow-up status in the same transaction
    # as the refund; finance will decide and record the actual red invoice later.
    blue_invoices = (
        await db.scalars(
            select(MallInvoice)
            .where(
                MallInvoice.order_id == order.id,
                MallInvoice.kind == "blue",
                MallInvoice.status.in_(
                    {"valid", "red_pending", "awaiting_counterparty", "partially_red"}
                ),
            )
            .order_by(MallInvoice.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    for invoice in blue_invoices:
        if invoice.status != "red_pending":
            invoice.status = "red_pending"
            invoice.version += 1

    invoice_job = await enqueue_mall_job(
        db,
        kind="mall_invoice_refund_review",
        entity_type="mall_refund",
        entity_id=refund.id,
        entity_version=refund.version,
        dedupe_key=f"mall-invoice-refund-review:{refund.id}",
    )
    invoice_job.status = "manual"
    invoice_job.last_error_code = "invoice_refund_review_required"
    db.add(
        AuditLog(
            user_id=None,
            action="mall_refund_succeeded",
            entity_type="mall_refund",
            entity_id=str(refund.id),
            detail={"orderId": str(order.id), "amountCent": refund.total_cent},
        )
    )
    await notify_mall_buyer(
        db,
        buyer_user_id=order.buyer_user_id,
        event_key=f"mall:refund:{refund.id}:succeeded",
        title="商城退款结果已确认",
        summary=f"订单号 {order.order_no} 的退款已确认。",
        target=f"/pages/mall-aftersale-detail/index?id={aftersale.id}",
    )


async def apply_verified_refund(db, identity, fact):
    """Apply one signed channel fact; repeat delivery changes no outcome twice."""
    order, aftersale, refund, payment = await _lock_refund_context(db, identity)
    _verify_refund_fact(order, payment, refund, fact)
    if refund.status == "succeeded":
        if refund.channel_refund_id != fact.channel_refund_id:
            raise ConflictException(message="渠道重复退款事实与已成功记录不一致")
        return refund
    if fact.status == "SUCCESS":
        await _record_success(db, order, aftersale, refund, payment, fact)
    elif fact.status == "PROCESSING":
        if refund.status != "abnormal":
            refund.status = "processing"
            clear_funds_unknown(refund)
            aftersale.status = "refunding"
        refund.last_query_at = utc_now()
        refund.last_error_code = None
        refund.version += 1
        aftersale.version += 1
    elif fact.status == "ABNORMAL":
        refund.status = "abnormal"
        clear_funds_unknown(refund)
        refund.last_query_at = utc_now()
        refund.last_error_code = "provider_refund_abnormal"
        refund.version += 1
        aftersale.status = "disputed"
        aftersale.audit_reason = "渠道退款异常，资金占用保留并转人工核实"
        aftersale.version += 1
        order.version += 1
        await _manual_refund_job(db, refund, error_code="provider_refund_abnormal")
    else:  # CLOSED is a channel fact, but the approved business amount stays reserved.
        refund.status = "closed"
        clear_funds_unknown(refund)
        refund.active_slot = None
        refund.last_query_at = utc_now()
        refund.last_error_code = "provider_refund_closed_review"
        refund.version += 1
        aftersale.status = "awaiting_refund"
        aftersale.audit_reason = "渠道已关闭原退款请求，原占用保留，需财务确认后续处理"
        aftersale.version += 1
        order.version += 1
        await _manual_refund_job(db, refund, error_code="provider_refund_closed_review")
    await db.flush()
    return refund


async def record_verified_refund_notification(db, *, event_id, refund_id, fact, verified_digest):
    """Persist an already-authenticated notification fact; no public endpoint is defined here."""
    if not re.fullmatch(r"[a-f0-9]{64}", verified_digest) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,128}", event_id
    ):
        raise ConflictException(message="退款通知事件身份无效")
    refund = await db.get(MallRefund, refund_id, populate_existing=True)
    if refund is None:
        raise NotFoundException(message="退款记录不存在")
    existing = await db.scalar(
        select(MallGatewayEvent)
        .where(MallGatewayEvent.channel == "wechatpay", MallGatewayEvent.event_id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if (
            existing.event_type != "refund"
            or existing.resource_id != refund.out_refund_no
            or existing.verified_digest != verified_digest
        ):
            raise ConflictException(message="退款通知事件ID重复但内容不同")
        await apply_verified_refund(db, refund_id, fact)
        return existing
    event = MallGatewayEvent(
        channel="wechatpay",
        event_id=event_id,
        event_type="refund",
        resource_id=refund.out_refund_no,
        payload_ciphertext=None,
        verified_digest=verified_digest,
        received_at=utc_now(),
        status="received",
    )
    db.add(event)
    await db.flush()
    await apply_verified_refund(db, refund_id, fact)
    event.status = "processed"
    await db.flush()
    return event


async def list_admin_refunds(db, *, cursor=None, page_size=20, status=None):
    query = select(MallRefund)
    if status:
        query = query.where(MallRefund.status == status)
    rows, next_cursor, total = await _page(
        db,
        query,
        MallRefund,
        MallRefund.id,
        mode=f"refunds:admin:{status or 'all'}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    from .mall_aftersale_query_service import serialize_refund

    return {
        "items": [serialize_refund(row) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }


async def get_admin_refund(db, identity):
    refund = await db.get(MallRefund, identity)
    if refund is None:
        raise NotFoundException(message="退款记录不存在")
    return refund


def _refund_job_result(command, refund, job):
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
        "entityId": str(refund.id),
        "status": status,
        "version": refund.version,
    }


async def queue_refund_query(db, actor, identity, data, *, key):
    """Schedule a signed read of the existing provider refund identity only."""
    actor = await _admin(db, actor, "mall.refunds.query")
    order, aftersale, refund, _payment = await _lock_refund_context(db, identity)
    payload = {"refundId": identity, **data.model_dump(mode="json")}
    intent = await reserve_mall_command(
        db, actor=actor, action="queryMallRefund", key=key, payload=payload
    )
    if not intent.created:
        if intent.command.status != "completed" or intent.command.entity_id != refund.id:
            raise ConflictException(message="原退款查单仍在处理中")
        job = await db.scalar(
            select(MallJob).where(
                MallJob.dedupe_key == f"mall-refund-query:{refund.id}:{intent.command.id}"
            )
        )
        if job is None:
            raise ConflictException(message="原退款查单工作项不存在，请重新发起")
        return _refund_job_result(intent.command, refund, job)
    if refund.version != data.expected_version:
        raise ConflictException(message="退款版本已变化，请重新读取")
    job = await enqueue_mall_job(
        db,
        kind="mall_refund_query",
        entity_type="mall_refund",
        entity_id=refund.id,
        entity_version=refund.version,
        dedupe_key=f"mall-refund-query:{refund.id}:{intent.command.id}",
    )
    await complete_mall_command(
        db, intent, entity_type="mall_refund", entity_id=refund.id, result_code="scheduled"
    )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_refund_query_requested",
        entity_type="mall_refund",
        entity_id=str(refund.id),
        detail={"orderId": str(order.id), "aftersaleId": str(aftersale.id)},
    )
    return _refund_job_result(intent.command, refund, job)


async def retry_refund(db, actor, identity, data, *, key):
    """Queue another safe attempt for the same refund row and merchant refund number."""
    actor = await _admin(db, actor, "mall.refunds.execute")
    order, aftersale, refund, _payment = await _lock_refund_context(db, identity)
    payload = {"refundId": identity, **data.model_dump(mode="json")}
    intent = await reserve_mall_command(
        db, actor=actor, action="retryMallRefund", key=key, payload=payload
    )
    if not intent.created:
        if intent.command.status != "completed" or intent.command.entity_id != refund.id:
            raise ConflictException(message="原退款重试请求仍在处理中")
        job = await db.scalar(
            select(MallJob).where(
                MallJob.dedupe_key == f"mall-refund-retry:{refund.id}:{intent.command.id}"
            )
        )
        if job is None:
            job = await db.scalar(
                select(MallJob)
                .where(
                    MallJob.kind == "mall_refund_execute",
                    MallJob.entity_type == "mall_refund",
                    MallJob.entity_id == refund.id,
                )
                .order_by(MallJob.id.desc())
            )
        if job is None:
            raise ConflictException(message="原退款重试工作项不存在，请重新发起")
        return _refund_job_result(intent.command, refund, job)
    if refund.version != data.expected_version:
        raise ConflictException(message="退款版本已变化，请重新读取")
    if refund.status not in {"prepared", "unknown", "processing"} or refund.active_slot != 1:
        raise ConflictException(message="当前退款状态不能自动重试，请先完成人工核实")
    active_job = await db.scalar(
        select(MallJob)
        .where(
            MallJob.kind == "mall_refund_execute",
            MallJob.entity_type == "mall_refund",
            MallJob.entity_id == refund.id,
            MallJob.status.in_(("ready", "retry", "running")),
        )
        .order_by(MallJob.id.desc())
        .with_for_update()
    )
    if active_job is None:
        job = await enqueue_mall_job(
            db,
            kind="mall_refund_execute",
            entity_type="mall_refund",
            entity_id=refund.id,
            entity_version=refund.version,
            dedupe_key=f"mall-refund-retry:{refund.id}:{intent.command.id}",
        )
    else:
        job = active_job
        if job.status in {"ready", "retry"}:
            job.next_run_at = utc_now()
            job.last_error_code = None
    await complete_mall_command(
        db, intent, entity_type="mall_refund", entity_id=refund.id, result_code="scheduled"
    )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_refund_retry_requested",
        entity_type="mall_refund",
        entity_id=str(refund.id),
        detail={"orderId": str(order.id), "aftersaleId": str(aftersale.id)},
    )
    return _refund_job_result(intent.command, refund, job)


class MallRefundExecutor:
    """Query first, then safely create or retry with the same merchant refund number."""

    def __init__(self, sessions, gateway_factory):
        self.sessions, self.gateway_factory = sessions, gateway_factory

    async def __call__(self, item):
        if (item.kind, item.entity_type) != ("mall_refund_execute", "mall_refund"):
            raise ValueError("invalid refund work item")
        async with self.sessions() as db:
            order, aftersale, refund, payment = await _lock_refund_context(db, item.entity_id)
            if not await locked_mall_lease(db, item):
                return
            if refund.status in {"succeeded", "closed"}:
                return
            if refund.status == "abnormal":
                job = await locked_mall_lease(db, item)
                if job:
                    job.status, job.last_error_code = "manual", "provider_refund_abnormal"
                    job.lease_owner = job.lease_until = None
                await db.commit()
                return
            if payment.status != "succeeded" or not payment.channel_transaction_id:
                raise ValueError("original payment requires reconciliation")
            gateway = self.gateway_factory(payment)
            observed_at = utc_now()
            mark_funds_unknown(refund, now=observed_at)
            refund.last_error_code = "refund_confirmation_pending"
            refund.version += 1
            refund.last_query_at = observed_at
            await db.commit()

        from ..integrations.wechat_pay_types import RefundNotFoundError
        from ..tasks.mall_tasks import MallJobContinuation

        try:
            fact = await gateway.query_refund(refund.out_refund_no)
        except RefundNotFoundError:
            async with self.sessions() as db:
                order, aftersale, current, payment = await _lock_refund_context(db, item.entity_id)
                if not await locked_mall_lease(db, item):
                    return
                if current.status in {"succeeded", "closed", "abnormal"}:
                    return
                if (gateway.appid, gateway.mchid) != (
                    payment.appid_snapshot,
                    payment.mchid_snapshot,
                ):
                    raise ValueError("payment merchant identity changed")
                request = {
                    "out_trade_no": payment.out_trade_no,
                    "out_refund_no": current.out_refund_no,
                    "total_cent": current.original_amount_cent,
                    "refund_cent": current.total_cent,
                }
                await db.commit()
            fact = await gateway.create_refund(**request)
        async with self.sessions() as db:
            order, aftersale, current, payment = await _lock_refund_context(db, item.entity_id)
            if not await locked_mall_lease(db, item):
                return
            await apply_verified_refund(db, current.id, fact)
            if current.status in {"abnormal", "closed"}:
                job = await locked_mall_lease(db, item)
                if job:
                    job.status = "manual"
                    job.last_error_code = current.last_error_code
                    job.lease_owner = job.lease_until = None
                await db.commit()
                return
            if current.status != "succeeded":
                await db.commit()
                return MallJobContinuation(delay_seconds=60)
            await db.commit()
        return None


class MallRefundQueryExecutor:
    """Read an existing provider refund identity and never create a refund."""

    def __init__(self, sessions, gateway_factory):
        self.sessions, self.gateway_factory = sessions, gateway_factory

    async def __call__(self, item):
        if (item.kind, item.entity_type) != ("mall_refund_query", "mall_refund"):
            raise ValueError("invalid refund query work item")
        async with self.sessions() as db:
            _, _, refund, payment = await _lock_refund_context(db, item.entity_id)
            if not await locked_mall_lease(db, item):
                return
            gateway = self.gateway_factory(payment)
            refund.last_query_at = utc_now()
            await db.commit()

        from ..integrations.wechat_pay_types import RefundNotFoundError

        try:
            fact = await gateway.query_refund(refund.out_refund_no)
        except RefundNotFoundError:
            async with self.sessions() as db:
                _, _, current, _ = await _lock_refund_context(db, item.entity_id)
                if not await locked_mall_lease(db, item):
                    return
                current.last_query_at = utc_now()
                current.last_error_code = "refund_not_found_at_channel"
                current.version += 1
                await db.commit()
            return None

        async with self.sessions() as db:
            _, _, current, _ = await _lock_refund_context(db, item.entity_id)
            if not await locked_mall_lease(db, item):
                return
            await apply_verified_refund(db, current.id, fact)
            await db.commit()
        return None
