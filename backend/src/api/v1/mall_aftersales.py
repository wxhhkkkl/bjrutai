"""Buyer aftersale submission, progress, withdrawal and return shipment."""

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, get_mall_buyer
from ...schemas.mall_aftersale import AftersaleCreate, ReasonAction, ReturnShipment
from ...services.mall_aftersale_query_service import (
    get_owned_aftersale,
    list_buyer_aftersales,
    serialize_aftersale,
)
from ...services.mall_aftersale_service import (
    apply_aftersale,
    submit_return_shipment,
    withdraw_aftersale,
)
from .mall_checkout import response

router = APIRouter(prefix="/mall/aftersales", tags=["mall-aftersales"])


@router.post("", operation_id="createMallAftersale")
async def create(
    body: AftersaleCreate,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await apply_aftersale(db, actor, body, key=key)
        result = await serialize_aftersale(db, row, buyer=True)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.get("", operation_id="listMyMallAftersales")
async def list_my(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    result = await list_buyer_aftersales(db, actor, cursor=cursor, page_size=page_size)
    await db.commit()
    return response(result)


@router.get("/{aftersaleId}", operation_id="getMyMallAftersale")
async def get_one(
    identity: int = Path(alias="aftersaleId", gt=0),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    row = await get_owned_aftersale(db, actor, identity)
    result = await serialize_aftersale(db, row, buyer=True)
    await db.commit()
    return response(result)


@router.post("/{aftersaleId}/withdraw", operation_id="withdrawMallAftersale")
async def withdraw(
    body: ReasonAction,
    identity: int = Path(alias="aftersaleId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await withdraw_aftersale(db, actor, identity, body, key=key)
        result = await serialize_aftersale(db, row, buyer=True)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{aftersaleId}/return-shipment", operation_id="sendMallReturn")
async def send_return(
    body: ReturnShipment,
    identity: int = Path(alias="aftersaleId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await submit_return_shipment(db, actor, identity, body, key=key)
        result = await serialize_aftersale(db, row, buyer=True)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise
