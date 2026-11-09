"""Permission-scoped payment ledger, channel query and private export routes."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...schemas.mall_catalog import VersionAction
from ...schemas.mall_finance import FinanceExport
from ...services.mall_export_service import create_finance_export
from ...services.mall_finance_query_service import (
    get_admin_payment,
    list_admin_payments,
    queue_admin_payment_query,
)
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall/payments", tags=["admin-mall-payments"])
read_payments = require_mall_admin("mall.payments.read")
query_payments = require_mall_admin("mall.payments.query")
export_finance = require_mall_admin("mall.finance.export")


@router.get("", operation_id="listAdminMallPayments")
async def list_all(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    status: Literal[
        "creating", "pending", "unknown", "succeeded", "closed", "failed"
    ]
    | None = None,
    order_no: str | None = Query(None, alias="orderNo", max_length=32),
    from_time: str | None = Query(None, alias="fromAt", max_length=40),
    to_time: str | None = Query(None, alias="toAt", max_length=40),
    actor: MallActor = Depends(read_payments),
    db: AsyncSession = Depends(get_db),
):
    result = await list_admin_payments(
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


@router.get("/{paymentId}", operation_id="getAdminMallPayment")
async def get_one(
    identity: int = Path(alias="paymentId", gt=0),
    actor: MallActor = Depends(read_payments),
    db: AsyncSession = Depends(get_db),
):
    result = await get_admin_payment(db, actor, identity)
    await db.commit()
    return response(result)


@router.post("/{paymentId}/query", operation_id="queryMallPayment", status_code=202)
async def query_one(
    body: VersionAction,
    identity: int = Path(alias="paymentId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(query_payments),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await queue_admin_payment_query(db, actor, identity, body, key=key)
        await db.commit()
        return response(result, status_code=202)
    except Exception:
        await db.rollback()
        raise


@router.post("/export", operation_id="exportMallPayment", status_code=202)
async def export_payments(
    body: FinanceExport,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(export_finance),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_finance_export(db, actor, "payments", body, key=key)
        await db.commit()
        return response(result, status_code=202)
    except Exception:
        await db.rollback()
        raise
