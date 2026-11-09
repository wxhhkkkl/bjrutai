"""One-order release of recipient data for internal fulfillment."""

from sqlalchemy import select

from ..api.mall_deps import MallActor
from ..core.config import get_settings
from ..core.exceptions import ForbiddenException, UnauthorizedException
from ..models.consent import ConsentScene
from ..models.mall_base import utc_now
from ..models.mall_trade import MallOrder
from .mall_data_release_service import (
    active_release_consent,
    current_release_actor,
    raw_data_release_runtime_ready,
    record_release_audit,
    release_expires_at,
)
from .mall_fulfillment_service import check_fulfillment


async def release_fulfillment_data(
    db,
    actor: MallActor,
    order_id: int,
    *,
    expected_version: int,
    event_key: str,
):
    """Release one eligible order's recipient fields without storing a replay body."""
    settings = get_settings()
    audit_args = {
        "entity_type": "mall_order",
        "entity_id": str(order_id),
        "purpose": "shipping_label",
        "expected_version": expected_version,
        "event_key": event_key,
        "settings": settings,
    }
    try:
        current_actor = await current_release_actor(db, actor, "mall.fulfillment.release")
    except (ForbiddenException, UnauthorizedException):
        await record_release_audit(
            db,
            actor=actor,
            action="mall_admin_fulfillment_data_release_denied",
            reason_code="permission_revoked",
            **audit_args,
        )
        return None

    if not raw_data_release_runtime_ready(settings):
        await record_release_audit(
            db,
            actor=current_actor,
            action="mall_admin_fulfillment_data_release_denied",
            reason_code="runtime_not_ready",
            **audit_args,
        )
        return None

    order = await db.scalar(
        select(MallOrder)
        .where(MallOrder.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        await record_release_audit(
            db,
            actor=current_actor,
            action="mall_admin_fulfillment_data_release_denied",
            reason_code="target_not_found",
            **audit_args,
        )
        return None

    actual_version = order.version
    fulfillment = await check_fulfillment(db, order, lock=True)
    consent_ok = await active_release_consent(
        db,
        consent_id=order.consent_record_id,
        user_id=order.buyer_user_id,
        scene=ConsentScene.MALL_CHECKOUT,
        required_scopes={"mall_fulfillment", "recipient_contact", "delivery_address"},
        notice_version=settings.mall_data_release_notice_approved_version.strip(),
        now=utc_now(),
    )
    reason_code = None
    if expected_version != actual_version:
        reason_code = "version_mismatch"
    elif not fulfillment["businessReady"]:
        reason_code = fulfillment["blockingReasons"][0]["code"]
    elif not consent_ok:
        reason_code = "consent_inactive_or_scope_mismatch"

    if reason_code:
        await record_release_audit(
            db,
            actor=current_actor,
            action="mall_admin_fulfillment_data_release_denied",
            actual_version=actual_version,
            reason_code=reason_code,
            **audit_args,
        )
        return None

    address = order.address_snapshot if isinstance(order.address_snapshot, dict) else {}
    audit = await record_release_audit(
        db,
        actor=current_actor,
        action="mall_admin_fulfillment_data_released",
        actual_version=actual_version,
        reason_code="allowed",
        **audit_args,
    )
    return {
        "orderId": str(order.id),
        "recipientName": address["recipientName"],
        "phone": address["phone"],
        "addressLine": address["addressLine"],
        "expiresAt": release_expires_at(),
        "auditId": str(audit.id),
    }
