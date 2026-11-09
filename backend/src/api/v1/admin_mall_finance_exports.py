"""Requester-scoped status for asynchronous finance exports."""

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...services.mall_export_service import get_finance_export
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall/finance/exports", tags=["admin-mall-finance"])
read_export = require_mall_admin("mall.finance.export")


@router.get("/{requestId}", operation_id="getAdminMallFinanceExport")
async def get_one(
    identity: int = Path(alias="requestId", gt=0),
    actor: MallActor = Depends(read_export),
    db: AsyncSession = Depends(get_db),
):
    result = await get_finance_export(db, actor, identity)
    await db.commit()
    return response(result)
