"""Order-locked local dispatch and tracking correction commands."""

import hashlib
from datetime import timedelta

from sqlalchemy import select

from ..api.mall_deps import require_mall_admin_permission
from ..core.exceptions import ConflictException, ForbiddenException, NotFoundException
from ..models.mall_base import utc_now
from ..models.mall_trade import MallOrder, MallShipment
from .mall_audit_service import record_mall_admin_audit
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_fulfillment_service import (
    _replay_completed_command,
    check_fulfillment,
)
from .mall_job_service import enqueue_mall_job
from .mall_notification_service import notify_mall_buyer


async def _locked_admin_order(db, identity):
    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise NotFoundException(message="商城订单不存在")
    return order


def _tracking_identity(courier_code, tracking_no):
    normalized = f"{courier_code.lower()}\x00{tracking_no.upper()}".encode("ascii")
    return hashlib.sha256(normalized).hexdigest()


def _enqueue_auto_receipt(db, shipment):
    return enqueue_mall_job(
        db,
        kind="mall_order_auto_receive",
        entity_type="mall_shipment",
        entity_id=shipment.id,
        entity_version=shipment.version,
        dedupe_key=f"mall-auto-receive:{shipment.id}:{shipment.version}",
        next_run_at=shipment.auto_receive_at,
    )


async def ship_order(db, actor, identity, data, *, key):
    """Record one local dispatch after a fresh, locked business check."""
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台管理员可登记商城发货")
    actor = await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        "mall.shipments.write",
        current=True,
    )
    order = await _locked_admin_order(db, identity)
    payload = {"orderId": identity, **data.model_dump(mode="json")}
    replay = await _replay_completed_command(db, actor, "shipMallOrder", key, payload, MallShipment)
    if replay is not None:
        return replay
    if order.version != data.expected_version:
        raise ConflictException(message="订单版本已变化，请重新读取订单")

    check = await check_fulfillment(db, order, lock=True)
    if not check["businessReady"]:
        messages = "; ".join(reason["message"] for reason in check["blockingReasons"])
        raise ConflictException(message=f"订单当前不能发货：{messages}")
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="shipMallOrder",
        key=key,
        payload=payload,
    )
    if not intent.created:
        raise ConflictException(message="原发货请求仍在处理中，请查询原请求")
    now = utc_now()
    auto_receive_at = now + timedelta(days=order.policy_snapshot["autoReceiveDays"])
    shipment = MallShipment(
        order_id=order.id,
        courier_code=data.courier_code,
        tracking_no=data.tracking_no,
        shipped_at=now,
        auto_receive_at=auto_receive_at,
        shipped_by=actor.actor_id,
        platform_sync_status="not_required",
        platform_report_status="pending",
        platform_confirmation_status="unknown",
        logistics_provider="kuaidi100",
        logistics_status="pending",
        tracking_identity_hash=_tracking_identity(data.courier_code, data.tracking_no),
        tracking_snapshot={},
    )
    db.add(shipment)
    order.status = "pending_receipt"
    order.shipped_at = now
    order.version += 1
    await db.flush()
    await _enqueue_auto_receipt(db, shipment)
    await notify_mall_buyer(
        db,
        buyer_user_id=order.buyer_user_id,
        event_key=f"mall:shipment:{shipment.id}:created",
        title="商城订单已发货",
        summary=f"订单号 {order.order_no} 已发货，可查看物流进度。",
        target=f"/pages/mall-order-detail/index?id={order.id}",
    )
    await db.flush()
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_order_shipped",
        entity_type="mall_order",
        entity_id=str(order.id),
        detail={
            "shipmentId": str(shipment.id),
            "orderVersion": order.version,
            "courierCode": shipment.courier_code,
            "trackingDigest": _tracking_identity(shipment.courier_code, shipment.tracking_no),
        },
    )
    await complete_mall_command(db, intent, entity_type="mall_shipment", entity_id=shipment.id)
    await db.flush()
    return shipment


async def correct_tracking(db, actor, identity, data, *, key):
    """Correct a local package under the same parent order lock, never dispatch twice."""
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台管理员可更正商城运单")
    actor = await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        "mall.shipments.write",
        current=True,
    )
    order_id = await db.scalar(select(MallShipment.order_id).where(MallShipment.id == identity))
    if order_id is None:
        raise NotFoundException(message="商城包裹不存在")
    order = await _locked_admin_order(db, order_id)
    shipment = await db.scalar(
        select(MallShipment)
        .where(MallShipment.id == identity, MallShipment.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if shipment is None:
        raise NotFoundException(message="商城包裹不存在")
    payload = {"shipmentId": identity, **data.model_dump(mode="json")}
    replay = await _replay_completed_command(
        db, actor, "correctMallTracking", key, payload, MallShipment
    )
    if replay is not None:
        return replay
    if order.version != data.expected_version or shipment.version != data.shipment_version:
        raise ConflictException(message="订单或包裹版本已变化，请重新读取后办理")
    if order.status != "pending_receipt" or not order.shipped_at:
        raise ConflictException(message="仅待收货订单可更正运单")
    if shipment.courier_code == data.courier_code and shipment.tracking_no == data.tracking_no:
        raise ConflictException(message="新运单信息与当前记录相同")
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="correctMallTracking",
        key=key,
        payload=payload,
    )
    if not intent.created:
        raise ConflictException(message="原运单更正请求仍在处理中，请查询原请求")

    previous_courier_code = shipment.courier_code
    previous_tracking_digest = _tracking_identity(shipment.courier_code, shipment.tracking_no)
    shipment.courier_code = data.courier_code
    shipment.tracking_no = data.tracking_no
    shipment.tracking_identity_hash = _tracking_identity(data.courier_code, data.tracking_no)
    shipment.tracking_snapshot = {}
    shipment.logistics_status = "pending"
    shipment.provider_state = None
    shipment.logistics_fetched_at = None
    shipment.logistics_next_query_at = None
    shipment.logistics_last_error_code = None
    shipment.platform_sync_status = "not_required"
    shipment.platform_report_status = "pending"
    shipment.platform_reported_at = None
    shipment.version += 1
    order.version += 1
    await db.flush()
    await _enqueue_auto_receipt(db, shipment)
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_tracking_corrected",
        entity_type="mall_order",
        entity_id=str(order.id),
        detail={
            "shipmentId": str(shipment.id),
            "orderVersion": order.version,
            "shipmentVersion": shipment.version,
            "beforeCourierCode": previous_courier_code,
            "beforeTrackingDigest": previous_tracking_digest,
            "afterCourierCode": shipment.courier_code,
            "afterTrackingDigest": shipment.tracking_identity_hash,
        },
    )
    await complete_mall_command(db, intent, entity_type="mall_shipment", entity_id=shipment.id)
    await db.flush()
    return shipment


async def record_platform_shipment_report(db, actor, identity, data, *, key):
    """Record an administrator's completed manual entry in the WeChat backend."""
    if actor.actor_type != "admin":
        raise ForbiddenException(message="仅后台管理员可登记微信平台发货信息")
    actor = await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        "mall.shipments.write",
        current=True,
    )
    order_id = await db.scalar(select(MallShipment.order_id).where(MallShipment.id == identity))
    if order_id is None:
        raise NotFoundException(message="商城包裹不存在")
    order = await _locked_admin_order(db, order_id)
    shipment = await db.scalar(
        select(MallShipment)
        .where(MallShipment.id == identity, MallShipment.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if shipment is None:
        raise NotFoundException(message="商城包裹不存在")
    payload = {"shipmentId": identity, **data.model_dump(mode="json")}
    replay = await _replay_completed_command(
        db, actor, "recordMallPlatformShipmentReport", key, payload, MallShipment
    )
    if replay is not None:
        return replay
    if shipment.version != data.expected_version:
        raise ConflictException(message="包裹版本已变化，请重新读取订单后办理")
    if not order.shipped_at:
        raise ConflictException(message="仅已登记本地出库的包裹可回填微信平台登记状态")
    if shipment.platform_report_status == "manual_reported":
        raise ConflictException(message="当前包裹版本已记录微信后台登记状态")

    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="recordMallPlatformShipmentReport",
        key=key,
        payload=payload,
    )
    if not intent.created:
        raise ConflictException(message="原登记确认仍在处理中，请查询原请求")

    shipment.platform_report_status = "manual_reported"
    shipment.platform_reported_at = utc_now()
    await db.flush()
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_platform_shipment_reported",
        entity_type="mall_order",
        entity_id=str(order.id),
        detail={
            "shipmentId": str(shipment.id),
            "orderVersion": order.version,
            "shipmentVersion": shipment.version,
            "platformReportStatus": shipment.platform_report_status,
        },
    )
    await complete_mall_command(
        db,
        intent,
        entity_type="mall_shipment",
        entity_id=shipment.id,
    )
    await db.flush()
    return shipment
