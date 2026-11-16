"""Shipment readiness is a projection of trusted money and reserved/sold facts."""

import pytest
from sqlalchemy import select

from src.models.mall_trade import MallAftersale, MallOrderItem
from src.services.mall_payment_service import apply_verified_payment
from tests.unit.test_mall_payment_service import payable, success


@pytest.mark.asyncio
async def test_verified_paid_snapshot_can_pass_business_check_without_catalog_stock_rechecking(
    db_session, monkeypatch
):
    from src.services.mall_fulfillment_service import check_fulfillment

    _, order, skus, payment = await payable(db_session, monkeypatch)
    await apply_verified_payment(db_session, payment.id, success(payment, order))
    await db_session.commit()
    skus[0].available_qty = 0
    skus[0].status = "archived"
    result = await check_fulfillment(db_session, order)
    assert result == {"businessReady": True, "blockingReasons": []}


@pytest.mark.parametrize(
    "invalid,code",
    [
        ("unpaid", "payment_unconfirmed"),
        ("closing", "close_pending"),
        ("aftersale", "aftersale_pending"),
        ("money", "payment_mismatch"),
        ("stock", "item_requires_review"),
        ("refund", "refund_requires_review"),
        ("extra_payment", "payment_requires_review"),
        ("address", "address_incomplete"),
        ("shipped", "already_fulfilled"),
    ],
)
@pytest.mark.asyncio
async def test_shipment_blockers_are_safe_and_never_mutate_inventory(
    db_session, monkeypatch, invalid, code
):
    from src.models.mall_base import utc_now
    from src.models.mall_finance import MallPayment
    from src.services.mall_fulfillment_service import check_fulfillment

    actor, order, skus, payment = await payable(db_session, monkeypatch)
    if invalid != "unpaid":
        await apply_verified_payment(db_session, payment.id, success(payment, order))
    if invalid == "closing":
        order.close_requested_at = utc_now()
    if invalid == "aftersale":
        db_session.add(
            MallAftersale(
                aftersale_no="check-aftersale",
                order_id=order.id,
                buyer_user_id=actor.actor_id,
                method="refund_only",
                reason="审核中",
            )
        )
    if invalid == "money":
        payment.amount_cent += 1
    if invalid == "stock":
        (
            await db_session.scalar(
                select(MallOrderItem).where(MallOrderItem.order_id == order.id).limit(1)
            )
        ).reservation_status = "reserved"
    if invalid == "refund":
        order.refund_reserved_cent = 1
    if invalid == "address":
        order.address_snapshot = {**order.address_snapshot, "phone": ""}
    if invalid == "shipped":
        order.shipped_at = utc_now()
    if invalid == "extra_payment":
        db_session.add(
            MallPayment(
                order_id=order.id,
                out_trade_no="extra-check-payment",
                amount_cent=payment.amount_cent,
                appid_snapshot=payment.appid_snapshot,
                mchid_snapshot=payment.mchid_snapshot,
                expires_at=payment.expires_at,
                status="unknown",
            )
        )
    await db_session.flush()
    before = [(s.available_qty, s.reserved_qty) for s in skus]
    result = await check_fulfillment(db_session, order)
    assert not result["businessReady"] and code in {x["code"] for x in result["blockingReasons"]}
    assert "13800001234" not in str(result) and "虚构路" not in str(result)
    assert before == [(s.available_qty, s.reserved_qty) for s in skus]
