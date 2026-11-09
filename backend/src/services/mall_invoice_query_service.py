"""Privacy-safe invoice request and ticket read projections."""

from sqlalchemy import select

from ..core.exceptions import NotFoundException
from ..models.mall_finance import MallInvoice, MallInvoiceRequest
from ..models.mall_trade import MallOrder
from .mall_catalog_query_service import _page
from .mall_order_service import owned_order


def _mask_tax_no(value):
    if not value:
        return None
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


async def serialize_invoice_request(db, row: MallInvoiceRequest):
    order = await db.get(MallOrder, row.order_id, populate_existing=True)
    net_paid_cent = (
        max(0, order.paid_amount_cent - order.refunded_goods_cent - order.refunded_freight_cent)
        if order is not None
        else 0
    )
    invoices = (
        await db.scalars(
            select(MallInvoice)
            .where(MallInvoice.request_id == row.id)
            .order_by(MallInvoice.id)
        )
    ).all()
    return {
        "id": str(row.id),
        "requestNo": row.request_no,
        "orderId": str(row.order_id),
        "buyerType": row.buyer_type,
        "invoiceType": row.invoice_type,
        "title": row.title,
        "taxNoMasked": _mask_tax_no(row.tax_no),
        "status": row.status,
        "requestedGoodsCent": row.requested_goods_cent,
        "requestedFreightCent": row.requested_freight_cent,
        "netPaidCent": net_paid_cent,
        "claimedBy": str(row.claimed_by) if row.claimed_by else None,
        "invoiceIds": [str(invoice.id) for invoice in invoices],
        "invoices": [serialize_invoice(invoice) for invoice in invoices],
        "version": row.version,
    }


def serialize_invoice(row: MallInvoice):
    return {
        "id": str(row.id),
        "orderId": str(row.order_id),
        "requestId": str(row.request_id),
        "sellerIdentity": row.seller_identity,
        "invoiceNo": row.invoice_no,
        "kind": row.kind,
        "totalCent": row.total_cent,
        "issuedAt": row.issued_at.isoformat() + "Z",
        "status": row.status,
        "originalInvoiceId": str(row.original_invoice_id) if row.original_invoice_id else None,
        "replacementForId": str(row.replacement_for_id) if row.replacement_for_id else None,
        "fileId": str(row.file_id),
        "version": row.version,
    }


async def get_owned_invoice_request(db, actor, identity):
    row = await db.scalar(
        select(MallInvoiceRequest)
        .where(
            MallInvoiceRequest.id == identity,
            MallInvoiceRequest.buyer_user_id == actor.actor_id,
        )
        .execution_options(populate_existing=True)
    )
    if actor.actor_type != "user" or row is None:
        raise NotFoundException(message="开票申请不存在")
    return row


async def get_admin_invoice_request(db, identity):
    row = await db.get(MallInvoiceRequest, identity, populate_existing=True)
    if row is None:
        raise NotFoundException(message="开票申请不存在")
    return row


async def list_buyer_invoices(db, actor, order_id, *, cursor=None, page_size=20):
    await owned_order(db, actor, order_id)
    query = select(MallInvoice).where(MallInvoice.order_id == order_id)
    rows, next_cursor, total = await _page(
        db,
        query,
        MallInvoice,
        MallInvoice.id,
        mode=f"buyer-invoices:{order_id}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    return {
        "items": [serialize_invoice(row) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }


async def list_admin_invoice_requests(db, *, status=None, cursor=None, page_size=20):
    query = select(MallInvoiceRequest)
    if status:
        query = query.where(MallInvoiceRequest.status == status)
    rows, next_cursor, total = await _page(
        db,
        query,
        MallInvoiceRequest,
        MallInvoiceRequest.id,
        mode=f"admin-invoice-requests:{status or '*'}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    return {
        "items": [await serialize_invoice_request(db, row) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }
