"""Shared local fulfillment checks and safe package projections."""

import re

from sqlalchemy import select

from ..core.exceptions import ConflictException
from ..models.mall_finance import MallPayment
from ..models.mall_operations import MallCommand, MallJob
from ..models.mall_trade import MallAftersale, MallOrderItem, MallShipment
from .mall_command_service import canonical_payload_hash

TERMINAL_AFTERSALES = {"rejected", "withdrawn", "closed", "succeeded", "completed"}
ACTIVE_AFTERSALE_SQL = MallAftersale.status.not_in(tuple(sorted(TERMINAL_AFTERSALES)))


def shipment_view(shipment):
    return {
        "id": str(shipment.id),
        "courierCode": shipment.courier_code,
        "trackingNo": shipment.tracking_no,
        "shippedAt": shipment.shipped_at.isoformat() + "Z" if shipment.shipped_at else None,
        "autoReceiveAt": (
            shipment.auto_receive_at.isoformat() + "Z" if shipment.auto_receive_at else None
        ),
        "platformSyncStatus": shipment.platform_sync_status,
        "platformReportStatus": shipment.platform_report_status,
        "platformReportedAt": (
            shipment.platform_reported_at.isoformat() + "Z"
            if shipment.platform_reported_at
            else None
        ),
        "platformConfirmedAt": (
            shipment.platform_confirmed_at.isoformat() + "Z"
            if shipment.platform_confirmed_at
            else None
        ),
        "version": shipment.version,
    }


async def check_fulfillment(db, order, *, lock=False):
    async def rows(model):
        query = select(model).where(model.order_id == order.id).order_by(model.id)
        if lock:
            query = query.with_for_update(read=True)
        return (await db.scalars(query.execution_options(populate_existing=True))).all()

    payments, items, aftersales, shipments = (
        await rows(MallPayment),
        await rows(MallOrderItem),
        await rows(MallAftersale),
        await rows(MallShipment),
    )
    reasons = []

    def block(code, message):
        reasons.append({"code": code, "message": message})

    if order.status != "pending_shipment":
        block("order_not_awaiting_shipment", "订单当前不处于待发货状态")
    if not order.paid_amount_cent or not order.paid_at:
        block("payment_unconfirmed", "尚未核实成功收款")
    payment = next((p for p in payments if p.id == order.active_payment_id), None)
    if (
        not payment
        or payment.status != "succeeded"
        or not payment.confirmed_at
        or not payment.channel_transaction_id
        or not payment.appid_snapshot
        or not payment.mchid_snapshot
        or payment.amount_cent != order.payable_amount_cent
        or payment.currency != order.currency
        or order.paid_amount_cent != order.payable_amount_cent
    ):
        block("payment_mismatch", "订单与已核实付款事实不一致，请先核对")
    if any(
        p.id != order.active_payment_id and p.status not in {"closed", "failed"} for p in payments
    ) or (payment and payment.last_error_code):
        block("payment_requires_review", "存在额外付款或收款异常，请先处理")
    if order.close_requested_at:
        block("close_pending", "订单已申请关闭，请先核实处理结果")
    if any(a.status not in TERMINAL_AFTERSALES for a in aftersales):
        block("aftersale_pending", "售后处理中，暂不能发货")
    if order.refund_reserved_cent or order.refunded_goods_cent or order.refunded_freight_cent:
        block("refund_requires_review", "存在退款或金额调整，请先核实可发数量")
    if not items or any(
        i.reservation_status != "sold"
        or i.aftersale_reserved_quantity
        or i.refunded_quantity
        or i.returned_quantity
        for i in items
    ):
        block("item_requires_review", "商品出库数量或已售事实需核实")
    if shipments or order.shipped_at:
        block("already_shipped", "已有发货记录，不能重复发货")
    auto_receive_days = (order.policy_snapshot or {}).get("autoReceiveDays")
    if type(auto_receive_days) is not int or auto_receive_days < 1:
        block("auto_receive_policy_invalid", "订单自动收货规则缺失，请先核实")
    address = order.address_snapshot or {}
    regions = address.get("regionCodes")
    if (
        not address.get("recipientName")
        or not address.get("addressLine")
        or not re.fullmatch(r"1[3-9][0-9]{9}", str(address.get("phone", "")))
        or not isinstance(regions, list)
        or len(regions) != 3
        or any(not re.fullmatch(r"[0-9]{6}", str(code)) for code in regions)
    ):
        block("address_incomplete", "订单收货资料不完整，请先处理")
    job_query = select(MallJob.id).where(
        MallJob.entity_type == "mall_order",
        MallJob.entity_id == order.id,
        MallJob.kind.in_(("mall_paid_order_exception", "mall_order_close")),
        MallJob.status == "manual",
    )
    if lock:
        job_query = job_query.with_for_update(read=True)
    if await db.scalar(job_query.limit(1)):
        block("funds_exception_pending", "订单存在待处理的收款或关闭异常")
    return {"businessReady": not reasons, "blockingReasons": reasons}


async def _replay_completed_command(db, actor, action, key, payload, model):
    command = await db.scalar(
        select(MallCommand)
        .where(
            MallCommand.actor_type == actor.actor_type,
            MallCommand.actor_id == actor.actor_id,
            MallCommand.action == action,
            MallCommand.key == key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if command is None:
        return None
    if command.payload_hash != canonical_payload_hash(payload):
        raise ConflictException(message="幂等键对应的请求内容不一致")
    if command.status != "completed" or command.entity_type not in {
        "mall_order",
        "mall_shipment",
    }:
        raise ConflictException(message="原操作仍在处理中，请查询原请求")
    result = await db.get(model, command.entity_id, populate_existing=True)
    if result is None:
        raise ConflictException(message="原操作结果暂不可用，请联系管理员核实")
    return result
