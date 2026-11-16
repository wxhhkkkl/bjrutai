"""Safe mall response serialization has no original recipient address."""

from types import SimpleNamespace


def test_buyer_order_summary_masks_phone_and_omits_address_snapshot():
    from src.schemas.mall_common import serialize_buyer_order_summary

    order = SimpleNamespace(
        id=9,
        order_no="MO202611040001",
        status="pending_shipment",
        payable_amount_cent=10900,
        address_snapshot={
            "recipient_name": "张三",
            "phone": "13800138000",
            "address_line": "北京市朝阳区示例路1号",
        },
    )

    assert serialize_buyer_order_summary(order) == {
        "orderId": "9",
        "orderNo": "MO202611040001",
        "status": "pending_shipment",
        "payableAmountCent": 10900,
        "recipientPhoneMasked": "138****8000",
    }
