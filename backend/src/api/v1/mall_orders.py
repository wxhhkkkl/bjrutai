"""Local order creation and owned snapshot reads; no live payment routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, get_mall_buyer
from ...schemas.mall_catalog import VersionAction
from ...schemas.mall_checkout import OrderAddressChange, OrderCancel, OrderCreate
from ...services.mall_order_action_service import (
    cancel_order,
    cancel_progress,
    change_order_address,
)
from ...services.mall_order_query_service import list_orders, serialize_order
from ...services.mall_order_service import audit_order, create_order, owned_order
from ...services.mall_receipt_service import confirm_receipt
from .mall_checkout import response

router = APIRouter(prefix="/mall/orders", tags=["mall-orders"])


@router.post("/{orderId}/cancel", operation_id="cancelMallOrder", status_code=202)
async def cancel(
    body: OrderCancel,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        command = await cancel_order(db, actor, identity, body, key=key)
        result = await cancel_progress(db, command)
        await db.commit()
        return response(result, status_code=202)
    except Exception:
        await db.rollback()
        raise


@router.patch("/{orderId}/address", operation_id="changeMallOrderAddress")
async def change_address(
    body: OrderAddressChange,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        order = await change_order_address(db, actor, identity, body, key=key)
        result = await serialize_order(db, order)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("", operation_id="createMallOrder")
async def create(
    body: OrderCreate,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        order = await create_order(db, actor, body, key=key)
        result = await serialize_order(db, order)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.get("", operation_id="listMyMallOrders")
async def list_my_orders(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    status: (
        Literal["pending_payment", "pending_shipment", "pending_receipt", "completed", "closed"]
        | None
    ) = None,
    aftersale: Literal["active"] | None = Query(None),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    result = await list_orders(
        db, actor, cursor=cursor, page_size=page_size, status=status, aftersale=aftersale
    )
    await db.commit()
    return response(result)


@router.get("/{orderId}", operation_id="getMyMallOrder")
async def get_my_order(
    identity: int = Path(alias="orderId", gt=0),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    order = await owned_order(db, actor, identity)
    result = await serialize_order(
        db, order, detail=True, include_delivery_details=True
    )
    audit_order(db, actor, order, "mall_order_read")
    await db.commit()
    return response(result)


@router.post("/{orderId}/confirm-receipt", operation_id="confirmMallReceipt")
async def confirm_order_receipt(
    body: VersionAction,
    identity: int = Path(alias="orderId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        order = await confirm_receipt(db, actor, identity, body, key=key)
        result = await serialize_order(db, order, detail=True)
        audit_order(db, actor, order, "mall_order_read")
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise
