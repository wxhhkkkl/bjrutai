"""Permission-scoped refund ledger reads and queued channel checks."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...schemas.mall_aftersale import ReasonAction
from ...schemas.mall_catalog import VersionAction
from ...schemas.mall_finance import FinanceExport
from ...services.mall_aftersale_query_service import serialize_refund
from ...services.mall_export_service import create_finance_export
from ...services.mall_finance_query_service import list_admin_finance_refunds
from ...services.mall_refund_service import (
    get_admin_refund,
    queue_refund_query,
    retry_refund,
)
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall/refunds", tags=["admin-mall-refunds"])
read_refunds = require_mall_admin("mall.refunds.read")
query_refunds = require_mall_admin("mall.refunds.query")
execute_refunds = require_mall_admin("mall.refunds.execute")
export_finance = require_mall_admin("mall.finance.export")


@router.get("", operation_id="listAdminMallRefunds")
async def list_all(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    status: Literal[
        "prepared",
        "processing",
        "unknown",
        "succeeded",
        "closed",
        "abnormal",
        "rejected_unaccepted",
    ]
    | None = None,
    order_no: str | None = Query(None, alias="orderNo", max_length=32),
    from_time: str | None = Query(None, alias="fromAt", max_length=40),
    to_time: str | None = Query(None, alias="toAt", max_length=40),
    actor: MallActor = Depends(read_refunds),
    db: AsyncSession = Depends(get_db),
):
    result = await list_admin_finance_refunds(
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


@router.post("/export", operation_id="exportMallRefund", status_code=202)
async def export_refunds(
    body: FinanceExport,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(export_finance),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_finance_export(db, actor, "refunds", body, key=key)
        await db.commit()
        return response(result, status_code=202)
    except Exception:
        await db.rollback()
        raise


@router.get("/{refundId}", operation_id="getAdminMallRefund")
async def get_one(
    identity: int = Path(alias="refundId", gt=0),
    actor: MallActor = Depends(read_refunds),
    db: AsyncSession = Depends(get_db),
):
    refund = await get_admin_refund(db, identity)
    result = serialize_refund(refund)
    await db.commit()
    return response(result)


@router.post("/{refundId}/query", operation_id="queryMallRefund", status_code=202)
async def query_one(
    body: VersionAction,
    identity: int = Path(alias="refundId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(query_refunds),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await queue_refund_query(db, actor, identity, body, key=key)
        await db.commit()
        return response(result, status_code=202)
    except Exception:
        await db.rollback()
        raise


@router.post("/{refundId}/retry", operation_id="retryMallRefund", status_code=202)
async def retry_one(
    body: ReasonAction,
    identity: int = Path(alias="refundId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(execute_refunds),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await retry_refund(db, actor, identity, body, key=key)
        await db.commit()
        return response(result, status_code=202)
    except Exception:
        await db.rollback()
        raise
