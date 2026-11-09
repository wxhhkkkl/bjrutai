"""Permission-scoped aftersale review and physical return inspection."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...schemas.mall_aftersale import AftersaleDecision, ReturnReceipt
from ...schemas.mall_catalog import VersionAction
from ...services.mall_aftersale_query_service import (
    get_admin_aftersale,
    list_admin_aftersales,
    serialize_aftersale,
    serialize_refund,
)
from ...services.mall_aftersale_service import decide_aftersale, receive_return
from ...services.mall_refund_service import execute_refund
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall/aftersales", tags=["admin-mall-aftersales"])
read_aftersales = require_mall_admin("mall.aftersales.read")
review_aftersales = require_mall_admin("mall.aftersales.review")
receive_returns = require_mall_admin("mall.returns.receive")
execute_refunds = require_mall_admin("mall.refunds.execute")


@router.get("", operation_id="listAdminMallAftersales")
async def list_all(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    status: Literal[
        "submitted",
        "awaiting_return",
        "awaiting_receipt",
        "awaiting_refund",
        "refunding",
        "disputed",
        "completed",
        "rejected",
        "withdrawn",
    ]
    | None = None,
    actor: MallActor = Depends(read_aftersales),
    db: AsyncSession = Depends(get_db),
):
    result = await list_admin_aftersales(db, cursor=cursor, page_size=page_size, status=status)
    await db.commit()
    return response(result)


@router.get("/{aftersaleId}", operation_id="getAdminMallAftersale")
async def get_one(
    identity: int = Path(alias="aftersaleId", gt=0),
    actor: MallActor = Depends(read_aftersales),
    db: AsyncSession = Depends(get_db),
):
    row = await get_admin_aftersale(db, identity)
    result = await serialize_aftersale(db, row)
    await db.commit()
    return response(result)


@router.post("/{aftersaleId}/decision", operation_id="decideMallAftersale")
async def decide(
    body: AftersaleDecision,
    identity: int = Path(alias="aftersaleId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(review_aftersales),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await decide_aftersale(db, actor, identity, body, key=key)
        result = await serialize_aftersale(db, row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{aftersaleId}/receipt", operation_id="receiveMallReturn")
async def receive(
    body: ReturnReceipt,
    identity: int = Path(alias="aftersaleId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(receive_returns),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await receive_return(db, actor, identity, body, key=key)
        result = await serialize_aftersale(db, row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{aftersaleId}/execute-refund", operation_id="executeMallRefund")
async def execute(
    body: VersionAction,
    identity: int = Path(alias="aftersaleId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(execute_refunds),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await execute_refund(db, actor, identity, body, key=key)
        result = serialize_refund(row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise
