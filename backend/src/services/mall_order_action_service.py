"""Owned order changes; cancellation intent is durable, channel closure is separate."""

from sqlalchemy import select

from ..core.exceptions import ConflictException
from ..models.audit import AuditLog
from ..models.consent import ConsentRecord, ConsentScene
from ..models.mall_base import utc_now
from ..models.mall_operations import MallJob
from ..models.mall_trade import MallAftersale, MallOrder, MallShipment
from .mall_address_service import audit_address, lock_buyer, owned_address
from .mall_command_service import (
    canonical_payload_hash,
    complete_mall_command,
    reserve_mall_command,
)
from .mall_job_service import enqueue_mall_job
from .mall_order_close_service import close_unattempted_locked, payment_history
from .mall_order_service import audit_order, owned_order


async def request_close_locked(db, order, *, reason, actor=None):
    """Requires the order lock; stock stays reserved whenever payment history exists."""
    if order.status != "pending_payment" or order.paid_amount_cent:
        raise ConflictException(message="已收款订单须申请售后，不能直接取消")
    history = await payment_history(db, order)
    if not order.close_requested_at:
        order.close_requested_at, order.close_request_reason = utc_now(), reason
        order.version += 1
    if not history and order.active_payment_id is None:
        return await close_unattempted_locked(db, order, actor=actor)
    if not history:
        raise ConflictException(message="付款关联异常，须先人工核实")
    await enqueue_mall_job(
        db,
        kind="mall_order_close",
        entity_type="mall_order",
        entity_id=order.id,
        entity_version=order.version,
        dedupe_key=f"mall-order-close:{order.id}",
    )
    return order


async def cancel_order(db, actor, identity, data, *, key):
    await lock_buyer(db, actor)
    order = await owned_order(db, actor, identity, lock=True)
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="cancelMallOrder",
        key=key,
        payload={"orderId": identity, **data.model_dump(mode="json")},
    )
    if not intent.created:
        return intent.command
    if order.version != data.expected_version:
        raise ConflictException(message="订单版本已变化，请刷新")
    audit_order(db, actor, order, "mall_order_cancel_requested")
    await request_close_locked(db, order, reason=data.reason, actor=actor)
    await complete_mall_command(db, intent, entity_type="mall_order", entity_id=order.id)
    return intent.command


async def cancel_progress(db, command):
    order = await db.get(MallOrder, command.entity_id, populate_existing=True)
    job = await db.scalar(
        select(MallJob)
        .where(MallJob.dedupe_key == f"mall-order-close:{command.entity_id}")
        .execution_options(populate_existing=True)
    )
    status = "manual"
    if order and order.status == "closed" and not order.paid_amount_cent:
        status = "completed"
    elif order and not order.paid_amount_cent and job:
        status = {
            "ready": "pending",
            "retry": "pending",
            "running": "running",
            "manual": "manual",
        }.get(job.status, "manual")
    return {
        "commandId": str(command.id),
        "entityId": str(command.entity_id),
        "status": status,
        "version": order.version if order else command.version,
    }


async def change_order_address(db, actor, identity, data, *, key):
    await lock_buyer(db, actor)
    order = await owned_order(db, actor, identity, lock=True)
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="changeMallOrderAddress",
        key=key,
        payload={"orderId": identity, **data.model_dump(mode="json")},
    )
    if not intent.created:
        return order
    if (
        order.version != data.expected_version
        or order.status not in {"pending_payment", "pending_shipment"}
        or order.shipped_at
        or order.close_requested_at
        or (order.status == "pending_payment" and order.expires_at <= utc_now())
    ):
        raise ConflictException(message="订单状态或版本不允许修改地址")
    shipment = await db.scalar(
        select(MallShipment.id).where(MallShipment.order_id == order.id).with_for_update()
    )
    aftersale = await db.scalar(
        select(MallAftersale.id)
        .where(
            MallAftersale.order_id == order.id,
            MallAftersale.status.not_in(("rejected", "withdrawn", "closed", "succeeded")),
        )
        .with_for_update()
        .limit(1)
    )
    if shipment or aftersale:
        raise ConflictException(message="已有发货或售后处理，不能修改地址")
    address = await owned_address(db, actor, int(data.address_id), lock=True)
    consent = await db.scalar(
        select(ConsentRecord)
        .where(ConsentRecord.id == address.consent_record_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if (
        not consent
        or consent.user_id != actor.actor_id
        or consent.scene != ConsentScene.MALL_ADDRESS
        or not consent.confirmed
        or consent.status != "active"
        or consent.scopes.get("mall_address") is not True
        or (consent.expires_at and consent.expires_at <= utc_now())
    ):
        raise ConflictException(message="收货资料告知已失效，请重新保存地址")
    policy = order.policy_snapshot
    regions = [address.province_code, address.city_code, address.district_code]
    freight = 0 if policy.get("freightMode") == "free" else policy.get("freightCent")
    if (
        policy.get("freightMode") not in {"free", "fixed"}
        or type(freight) is not int
        or freight != order.freight_amount_cent
        or not isinstance(policy.get("blockedRegionCodes"), list)
        or set(regions) & set(policy["blockedRegionCodes"])
    ):
        raise ConflictException(message="原配送规则不支持此地址或需要调整运费")
    before = canonical_payload_hash(order.address_snapshot)
    order.address_snapshot = {
        "id": str(address.id),
        "version": address.version,
        "recipientName": address.recipient_name,
        "phone": address.phone,
        "phoneMasked": address.phone_masked,
        "regionCodes": regions,
        "addressLine": address.address_line,
        "changeReason": data.reason,
    }
    order.version += 1
    audit_address(db, actor, "mall_address_order_change", address.id, address.version)
    db.add(
        AuditLog(
            user_id=actor.actor_id,
            action="mall_order_address_changed",
            entity_type="mall_order",
            entity_id=str(order.id),
            detail={
                "version": order.version,
                "addressId": str(address.id),
                "addressVersion": address.version,
                "beforeDigest": before,
                "afterDigest": canonical_payload_hash(order.address_snapshot),
                "reasonDigest": canonical_payload_hash({"reason": data.reason}),
            },
        )
    )
    await complete_mall_command(db, intent, entity_type="mall_order", entity_id=order.id)
    await db.flush()
    return order
