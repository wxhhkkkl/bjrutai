"""Live-authorized admin reads and rate-limited Kuaidi100 refresh requests."""

from fastapi import APIRouter, Depends, Header, Path
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...schemas.mall_catalog import VersionAction
from ...schemas.mall_logistics import LogisticsRefreshResult, LogisticsSnapshot
from ...services.mall_logistics_service import get_admin_logistics, refresh_logistics
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall/orders", tags=["admin-mall-logistics"])
shipment_router = APIRouter(prefix="/admin/mall/shipments", tags=["admin-mall-logistics"])
read_orders = require_mall_admin("mall.orders.read")
write_shipments = require_mall_admin("mall.shipments.write")


@router.get("/{orderId}/logistics", operation_id="getAdminMallLogistics")
async def get_order_logistics(
    identity: int = Path(alias="orderId", gt=0),
    actor: MallActor = Depends(read_orders),
    db: AsyncSession = Depends(get_db),
):
    result = await get_admin_logistics(db, actor, identity)
    data = LogisticsSnapshot.model_validate(result).model_dump(by_alias=True, mode="json")
    await db.commit()
    return response(data)


@shipment_router.post(
    "/{shipmentId}/logistics-refresh",
    operation_id="refreshMallLogistics",
    status_code=202,
)
async def refresh_shipment_logistics(
    body: VersionAction,
    identity: int = Path(alias="shipmentId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_shipments),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await refresh_logistics(db, actor, identity, body, key=key)
        data = LogisticsRefreshResult.model_validate(result).model_dump(by_alias=True, mode="json")
        await db.commit()
        return response(data, status_code=202)
    except Exception:
        await db.rollback()
        raise
