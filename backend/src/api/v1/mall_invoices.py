"""Buyer invoice applications, correction requests and order ticket history."""

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, get_mall_buyer
from ...schemas.mall_aftersale import ReasonAction
from ...schemas.mall_invoice import InvoiceCreate, InvoicePatch
from ...services.mall_invoice_query_service import (
    get_owned_invoice_request,
    list_buyer_invoices,
    serialize_invoice_request,
)
from ...services.mall_invoice_service import (
    create_invoice_request,
    request_invoice_correction,
    update_invoice_request,
    withdraw_invoice_request,
)
from .mall_checkout import response

router = APIRouter(prefix="/mall", tags=["mall-invoices"])


@router.post("/invoice-requests", operation_id="createMallInvoiceRequest")
async def create(
    body: InvoiceCreate,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await create_invoice_request(db, actor, body, key=key)
        result = await serialize_invoice_request(db, row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.get("/invoice-requests/{requestId}", operation_id="getMyMallInvoiceRequest")
async def get_request(
    identity: int = Path(alias="requestId", gt=0),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    row = await get_owned_invoice_request(db, actor, identity)
    result = await serialize_invoice_request(db, row)
    await db.commit()
    return response(result)


@router.patch("/invoice-requests/{requestId}", operation_id="updateMyMallInvoiceRequest")
async def update_request(
    body: InvoicePatch,
    identity: int = Path(alias="requestId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await update_invoice_request(db, actor, identity, body, key=key)
        result = await serialize_invoice_request(db, row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post(
    "/invoice-requests/{requestId}/withdraw", operation_id="withdrawMallInvoiceRequest"
)
async def withdraw_request(
    body: ReasonAction,
    identity: int = Path(alias="requestId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await withdraw_invoice_request(db, actor, identity, body, key=key)
        result = await serialize_invoice_request(db, row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.get("/orders/{orderId}/invoices", operation_id="listMyMallInvoices")
async def list_order_invoices(
    identity: int = Path(alias="orderId", gt=0),
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    result = await list_buyer_invoices(
        db, actor, identity, cursor=cursor, page_size=page_size
    )
    await db.commit()
    return response(result)


@router.post("/invoices/{invoiceId}/correction", operation_id="requestMallInvoiceCorrection")
async def request_correction(
    body: ReasonAction,
    identity: int = Path(alias="invoiceId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(get_mall_buyer),
    db: AsyncSession = Depends(get_db),
):
    try:
        command = await request_invoice_correction(db, actor, identity, body, key=key)
        await db.commit()
        return response(
            {
                "commandId": str(command.id),
                "entityId": str(command.entity_id) if command.entity_id else None,
                "status": "manual",
                "version": command.version,
            },
            status_code=202,
        )
    except Exception:
        await db.rollback()
        raise
