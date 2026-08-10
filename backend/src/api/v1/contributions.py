"""消费业绩（业绩贡献=消费金额）视图 API（US6）。

GET /api/v1/contributions/overview – 本月/累计消费金额 + 环比
GET /api/v1/contributions/trend     – 月度消费金额趋势
GET /api/v1/contributions           – 账单分页列表
GET /api/v1/contributions/{id}      – 账单明细
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...services.contribution_query_service import ConsumptionQueryService

router = APIRouter(prefix="/contributions", tags=["contributions"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@router.get("/overview")
async def get_overview(
    month: str = Query(..., description="Month in YYYY-MM format (e.g. 2026-07)"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """本月/累计消费金额 + 环比增长."""
    svc = ConsumptionQueryService()
    result = await svc.get_overview(db, int(payload["sub"]), month)
    return _ok(result)


@router.get("/trend")
async def get_trend(
    period: str = Query("6m", description="Number of months (e.g. 6m, 12m, 3m)"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """月度消费金额趋势（分）。"""
    svc = ConsumptionQueryService()
    result = await svc.get_trend(db, int(payload["sub"]), period)
    return _ok(result)


@router.get("")
async def list_contributions(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    status: Optional[str] = Query(None, description="Filter by bill transaction_status"),
    cursor: Optional[str] = Query(None, description="Pagination cursor (last ID from previous page)"),
    pageSize: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """账单分页列表（消费金额）。"""
    svc = ConsumptionQueryService()
    result = await svc.list_details(
        db, int(payload["sub"]),
        month=month,
        status=status,
        cursor=cursor,
        page_size=pageSize,
    )
    return _ok(result)


@router.get("/{bill_id}")
async def get_detail(
    bill_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """账单明细。"""
    svc = ConsumptionQueryService()
    result = await svc.get_detail(db, bill_id, int(payload["sub"]))
    return _ok(result)
