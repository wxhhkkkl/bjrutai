"""Live-permission workbench summary for the independent mall."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin_any
from ...services import mall_workbench_service
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall", tags=["admin-mall-workbench"])

read_workbench = require_mall_admin_any(
    "mall.orders.read",
    "mall.shipments.write",
    "mall.aftersales.read",
    "mall.aftersales.review",
    "mall.returns.receive",
    "mall.payments.read",
    "mall.payments.query",
    "mall.refunds.read",
    "mall.refunds.query",
    "mall.refunds.execute",
    "mall.attribution.write",
    "performance.settle",
    "mall.invoices.read",
    "mall.invoices.write",
    "mall.stock.read",
    "mall.stock.write",
)


@router.get("/workbench", operation_id="getAdminMallWorkbench")
async def workbench(
    actor: MallActor = Depends(read_workbench),
    db: AsyncSession = Depends(get_db),
):
    return response(await mall_workbench_service.get_mall_workbench(db, actor))
