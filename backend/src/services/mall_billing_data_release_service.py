"""Minimum invoice data release for the current finance claimant."""

import re

from sqlalchemy import select

from ..api.mall_deps import MallActor
from ..core.config import get_settings
from ..core.exceptions import ForbiddenException, UnauthorizedException
from ..models.consent import ConsentScene
from ..models.mall_base import utc_now
from ..models.mall_finance import MallInvoiceRequest, MallPayment
from ..models.mall_trade import MallOrder
from .mall_data_release_service import (
    active_release_consent,
    current_release_actor,
    raw_data_release_runtime_ready,
    record_release_audit,
    release_expires_at,
)


async def release_billing_data(
    db,
    actor: MallActor,
    request_id: int,
    *,
    expected_version: int,
    event_key: str,
):
    """Release one claimed invoice request's minimum issue fields."""
    settings = get_settings()
    audit_args = {
        "entity_type": "mall_invoice_request",
        "entity_id": str(request_id),
        "purpose": "invoice_issue",
        "expected_version": expected_version,
        "event_key": event_key,
        "settings": settings,
    }
    try:
        current_actor = await current_release_actor(db, actor, "mall.billing.release")
    except (ForbiddenException, UnauthorizedException):
        await record_release_audit(
            db,
            actor=actor,
            action="mall_admin_billing_data_release_denied",
            reason_code="permission_revoked",
            **audit_args,
        )
        return None

    if not raw_data_release_runtime_ready(settings):
        await record_release_audit(
            db,
            actor=current_actor,
            action="mall_admin_billing_data_release_denied",
            reason_code="runtime_not_ready",
            **audit_args,
        )
        return None

    order_id = await db.scalar(
        select(MallInvoiceRequest.order_id).where(MallInvoiceRequest.id == request_id)
    )
    if order_id is None:
        await record_release_audit(
            db,
            actor=current_actor,
            action="mall_admin_billing_data_release_denied",
            reason_code="target_not_found",
            **audit_args,
        )
        return None

    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    request = await db.scalar(
        select(MallInvoiceRequest)
        .where(MallInvoiceRequest.id == request_id, MallInvoiceRequest.order_id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None or request is None:
        await record_release_audit(
            db,
            actor=current_actor,
            action="mall_admin_billing_data_release_denied",
            reason_code="relationship_mismatch",
            **audit_args,
        )
        return None

    actual_version = request.version
    payment = await db.scalar(
        select(MallPayment)
        .where(MallPayment.id == order.active_payment_id, MallPayment.order_id == order.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    net_paid_cent = (
        order.paid_amount_cent - order.refunded_goods_cent - order.refunded_freight_cent
    )
    request_total_cent = request.requested_goods_cent + request.requested_freight_cent
    paid_and_open = bool(
        order.status in {"pending_shipment", "pending_receipt", "completed"}
        and order.paid_amount_cent > 0
        and order.close_requested_at is None
        and order.refund_reserved_cent == 0
        and net_paid_cent > 0
        and payment is not None
        and payment.status == "succeeded"
        and payment.confirmed_at is not None
        and payment.channel_transaction_id
        and payment.amount_cent == order.paid_amount_cent
        and payment.currency == "CNY"
    )
    request_is_current = bool(
        request.version == expected_version
        and request.status == "issuing"
        and request.active_slot == 1
        and request.claimed_by == current_actor.actor_id
        and request.claimed_at is not None
        and order.current_invoice_request_id == request.id
        and request.buyer_user_id == order.buyer_user_id
        and 0 < request.source_order_version <= order.version
        and 0 < request_total_cent <= net_paid_cent
    )
    tax_no = request.tax_no if request.buyer_type == "company" else None
    invoice_fields_valid = bool(
        request.buyer_type in {"personal", "company"}
        and isinstance(request.title, str)
        and request.title.strip()
        and (
            request.buyer_type == "personal"
            or (isinstance(tax_no, str) and re.fullmatch(r"[A-Za-z0-9]{8,32}", tax_no))
        )
    )
    consent_ok = await active_release_consent(
        db,
        consent_id=request.consent_record_id,
        user_id=request.buyer_user_id,
        scene=ConsentScene.MALL_INVOICE,
        required_scopes=(
            {"mall_invoice", "invoice_title", "tax_identifier"}
            if request.buyer_type == "company"
            else {"mall_invoice", "invoice_title"}
        ),
        notice_version=settings.mall_data_release_notice_approved_version.strip(),
        now=utc_now(),
    )

    reason_code = None
    if request.version != expected_version:
        reason_code = "version_mismatch"
    elif not request_is_current:
        reason_code = "request_not_currently_claimed"
    elif not paid_and_open:
        reason_code = "order_not_paid_or_refund_pending"
    elif not invoice_fields_valid:
        reason_code = "invoice_fields_invalid"
    elif not consent_ok:
        reason_code = "consent_inactive_or_scope_mismatch"

    if reason_code:
        await record_release_audit(
            db,
            actor=current_actor,
            action="mall_admin_billing_data_release_denied",
            actual_version=actual_version,
            reason_code=reason_code,
            **audit_args,
        )
        return None

    audit = await record_release_audit(
        db,
        actor=current_actor,
        action="mall_admin_billing_data_released",
        actual_version=actual_version,
        reason_code="allowed",
        **audit_args,
    )
    return {
        "requestId": str(request.id),
        "buyerType": request.buyer_type,
        "title": request.title,
        "taxNo": tax_no,
        "expiresAt": release_expires_at(),
        "auditId": str(audit.id),
    }
