"""Buyer-owned shipment snapshot reads; raw provider responses are never returned."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, get_mall_buyer
from ...schemas.mall_logistics import LogisticsSnapshot
from ...services.mall_logistics_service import get_buyer_logistics
from .mall_checkout import response

router = APIRouter(prefix="/mall/orders", tags=["mall-logistics"])


@router.get("/{orderId}/logistics", operation_id="getMyMallLogistics")
async def get_my_logistics(
    identity: int = Path(alias="orderId", gt=0),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    result = await get_buyer_logistics(db, actor, identity)
    data = LogisticsSnapshot.model_validate(result).model_dump(by_alias=True, mode="json")
    await db.commit()
    return response(data)
