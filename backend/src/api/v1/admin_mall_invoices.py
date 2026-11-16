"""Permission-scoped finance invoice workbench; raw tax data stays gated."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...core.exceptions import ForbiddenException
from ...schemas.mall_aftersale import ReasonAction
from ...schemas.mall_catalog import VersionAction
from ...schemas.mall_invoice import (
    BillingReleaseRequest,
    InvoiceFileReplace,
    InvoiceIssueRecord,
    RedInvoiceRecord,
    RedPendingUpdate,
)
from ...services.mall_billing_data_release_service import release_billing_data
from ...services.mall_invoice_query_service import (
    get_admin_invoice_request,
    list_admin_invoice_requests,
    serialize_invoice,
    serialize_invoice_request,
)
from ...services.mall_invoice_service import (
    claim_invoice_request,
    need_invoice_info,
    record_invoice_issue,
    record_red_invoice,
    replace_invoice_file,
    set_red_pending,
)
from .mall_checkout import response

router = APIRouter(prefix="/admin/mall", tags=["admin-mall-invoices"])
read_invoices = require_mall_admin("mall.invoices.read")
write_invoices = require_mall_admin("mall.invoices.write")
release_billing = require_mall_admin("mall.billing.release")


@router.get("/invoice-requests", operation_id="listAdminMallInvoiceRequests")
async def list_requests(
    status: Literal[
        "submitted", "needs_info", "issuing", "unknown", "delivered", "withdrawn", "closed"
    ] | None = Query(None),
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(read_invoices),
    db: AsyncSession = Depends(get_db),
):
    result = await list_admin_invoice_requests(
        db, status=status, cursor=cursor, page_size=page_size
    )
    await db.commit()
    return response(result)


@router.get("/invoice-requests/{requestId}", operation_id="getAdminMallInvoiceRequest")
async def get_request(
    identity: int = Path(alias="requestId", gt=0),
    actor: MallActor = Depends(read_invoices),
    db: AsyncSession = Depends(get_db),
):
    row = await get_admin_invoice_request(db, identity)
    result = await serialize_invoice_request(db, row)
    await db.commit()
    return response(result)


@router.post(
    "/invoice-requests/{requestId}/claim", operation_id="claimMallInvoice"
)
async def claim(
    body: VersionAction,
    identity: int = Path(alias="requestId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_invoices),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await claim_invoice_request(db, actor, identity, body, key=key)
        result = await serialize_invoice_request(db, row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post(
    "/invoice-requests/{requestId}/needs-info", operation_id="needMallInvoiceInfo"
)
async def needs_info(
    body: ReasonAction,
    identity: int = Path(alias="requestId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_invoices),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await need_invoice_info(db, actor, identity, body, key=key)
        result = await serialize_invoice_request(db, row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post(
    "/invoice-requests/{requestId}/record", operation_id="recordMallInvoice"
)
async def record_blue(
    body: InvoiceIssueRecord,
    identity: int = Path(alias="requestId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_invoices),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await record_invoice_issue(db, actor, identity, body, key=key)
        result = serialize_invoice(row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.patch("/invoices/{invoiceId}/file", operation_id="replaceMallInvoiceFile")
async def replace_file(
    body: InvoiceFileReplace,
    identity: int = Path(alias="invoiceId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_invoices),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await replace_invoice_file(db, actor, identity, body, key=key)
        result = serialize_invoice(row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/invoices/{invoiceId}/red-record", operation_id="recordMallRedInvoice")
async def record_red(
    body: RedInvoiceRecord,
    identity: int = Path(alias="invoiceId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_invoices),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await record_red_invoice(db, actor, identity, body, key=key)
        result = serialize_invoice(row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post(
    "/invoices/{invoiceId}/red-pending", operation_id="markMallRedPending"
)
async def red_pending(
    body: RedPendingUpdate,
    identity: int = Path(alias="invoiceId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_invoices),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await set_red_pending(db, actor, identity, body, key=key)
        result = serialize_invoice(row)
        await db.commit()
        return response(result)
    except Exception:
        await db.rollback()
        raise


@router.post(
    "/invoice-requests/{requestId}/billing-release", operation_id="releaseMallBilling"
)
async def billing_release_closed(
    body: BillingReleaseRequest,
    identity: int = Path(alias="requestId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(release_billing),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await release_billing_data(
            db,
            actor,
            identity,
            expected_version=body.expected_version,
            event_key=key,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    if result is None:
        raise ForbiddenException(message="原文资料交付当前未获授权")
    return response(result)
