"""Live-authorized administration; dispatch/raw fulfillment are not opened by reads."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...core.exceptions import ForbiddenException
from ...schemas.mall_checkout import OrderCancel
from ...schemas.mall_fulfillment import (
    FulfillmentReleaseRequest,
    OrderNote,
    ShipmentCreate,
    TrackingCorrection,
    VirtualDeliveryCreate,
)
from ...services.mall_admin_order_query_service import get_admin_order, list_admin_orders
from ...services.mall_admin_order_service import mutate_admin_order
from ...services.mall_fulfillment_data_release_service import release_fulfillment_data
from ...services.mall_fulfillment_service import shipment_view
from ...services.mall_order_action_service import cancel_progress
from ...services.mall_order_query_service import serialize_order
from ...services.mall_shipment_service import (
    correct_tracking,
    ship_order,
)
from ...services.mall_virtual_delivery_service import deliver_virtual_order
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall/orders", tags=["admin-mall-orders"])
shipment_router = APIRouter(prefix="/admin/mall/shipments", tags=["admin-mall-shipments"])
read_orders = require_mall_admin("mall.orders.read")
write_orders = require_mall_admin("mall.orders.write")
write_shipments = require_mall_admin("mall.shipments.write")


@router.get("", operation_id="listAdminMallOrders")
async def list_orders(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    status: (
        Literal["pending_payment", "pending_shipment", "pending_receipt", "completed", "closed"]
        | None
    ) = None,
    order_no: str | None = Query(None, alias="orderNo", min_length=1, max_length=32),
    from_time: str | None = Query(None, alias="from", max_length=40),
    to_time: str | None = Query(None, alias="to", max_length=40),
    actor: MallActor = Depends(read_orders),
    db: AsyncSession = Depends(get_db),
):
    result = await list_admin_orders(
        db,
        actor,
        cursor=cursor,
        page_size=page_size,
        status=status,
        order_no=order_no,
        from_time=from_time,
        to_time=to_time,
    )
    await db.commit()
    return response(result)


@router.get("/{orderId}", operation_id="getAdminMallOrder")
async def get_order(
    identity: int = Path(alias="orderId", gt=0),
    actor: MallActor = Depends(read_orders),
    db: AsyncSession = Depends(get_db),
):
    result = await get_admin_order(db, actor, identity)
    await db.commit()
    return response(result)


@router.patch("/{orderId}/note", operation_id="noteMallOrder")
async def note(
    body: OrderNote,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_orders),
    db: AsyncSession = Depends(get_db),
):
    try:
        order, _ = await mutate_admin_order(db, actor, identity, body, key=key)
        result = await serialize_order(db, order)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{orderId}/cancel", operation_id="cancelAdminMallOrder", status_code=202)
async def cancel(
    body: OrderCancel,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_orders),
    db: AsyncSession = Depends(get_db),
):
    try:
        _, command = await mutate_admin_order(db, actor, identity, body, key=key, cancel=True)
        result = await cancel_progress(db, command)
        await db.commit()
        return response(result, status_code=202)
    except Exception:
        await db.rollback()
        raise


@router.post("/{orderId}/ship", operation_id="shipMallOrder")
async def ship(
    body: ShipmentCreate,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_shipments),
    db: AsyncSession = Depends(get_db),
):
    try:
        shipment = await ship_order(db, actor, identity, body, key=key)
        result = shipment_view(shipment)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{orderId}/virtual-delivery", operation_id="deliverVirtualMallOrder")
async def deliver_virtual(
    body: VirtualDeliveryCreate,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_orders),
    db: AsyncSession = Depends(get_db),
):
    try:
        delivery = await deliver_virtual_order(db, actor, identity, body, key=key)
        result = {
            "id": str(delivery.id),
            "deliveredAt": delivery.delivered_at.isoformat() + "Z",
            "version": delivery.version,
        }
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{orderId}/fulfillment-release", operation_id="releaseMallFulfillment")
async def release_closed(
    body: FulfillmentReleaseRequest,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(require_mall_admin("mall.fulfillment.release")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await release_fulfillment_data(
            db,
            actor,
            identity,
            expected_version=body.expected_version,
            event_key=key,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    if result is None:
        raise ForbiddenException(message="原文资料交付当前未获授权")
    return response(result)


@shipment_router.patch("/{shipmentId}", operation_id="correctMallTracking")
async def correct_tracking_route(
    body: TrackingCorrection,
    identity: int = Path(alias="shipmentId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_shipments),
    db: AsyncSession = Depends(get_db),
):
    try:
        shipment = await correct_tracking(db, actor, identity, body, key=key)
        result = shipment_view(shipment)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise
