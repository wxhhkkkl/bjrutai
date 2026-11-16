"""Common, privacy-safe response helpers for buyer-facing mall APIs."""

from typing import Any


def mask_phone(phone: object) -> str:
    """Return a stable Chinese mobile mask without retaining a raw value."""
    value = "".join(character for character in str(phone or "") if character.isdigit())
    if len(value) == 11:
        return f"{value[:3]}****{value[-4:]}"
    return ""


def serialize_buyer_order_summary(order: Any) -> dict[str, object]:
    """Expose order state and a masked contact only, never the address snapshot."""
    snapshot = getattr(order, "address_snapshot", None) or {}
    return {
        "orderId": str(order.id),
        "orderNo": order.order_no,
        "status": order.status,
        "payableAmountCent": order.payable_amount_cent,
        "recipientPhoneMasked": snapshot.get("phone_masked") or mask_phone(snapshot.get("phone")),
    }
