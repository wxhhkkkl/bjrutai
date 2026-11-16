"""Complete simulated refund paths; no live payment or storage calls."""

import pytest
from sqlalchemy import func, select

from src.models.mall_catalog import MallStockMovement
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment, MallRefund
from src.models.mall_operations import MallJob, MallSettings
from src.models.mall_trade import MallAftersaleItem, MallShipment
from src.schemas.mall_aftersale import (
    AftersaleCreate,
    AftersaleDecision,
    ReturnReceipt,
    ReturnShipment,
    SellableReturnLine,
)
from src.schemas.mall_catalog import VersionAction
from src.schemas.mall_fulfillment import ShipmentCreate
from src.services.mall_aftersale_service import (
    apply_aftersale,
    decide_aftersale,
    receive_return,
    submit_return_shipment,
)
from src.services.mall_refund_service import apply_verified_refund, execute_refund
from src.services.mall_shipment_service import ship_order
from tests.unit.test_mall_aftersale_service import admin_actor, paid_order, request
from tests.unit.test_mall_refund_service import refund_fact


@pytest.mark.asyncio
async def test_pre_shipment_full_refund_restores_goods_and_freight_once(db_session, monkeypatch):
    buyer, order, skus, items = await paid_order(db_session, monkeypatch)
    application = AftersaleCreate(
        orderId=str(order.id),
        expectedOrderVersion=order.version,
        method="refund_only",
        items=[{"orderItemId": str(line.id), "quantity": line.quantity} for line in items],
        reason="整单退货前取消，包含全部商品",
    )
    aftersale = await apply_aftersale(
        db_session, buyer, application, key="refund-full-application-flow-001"
    )
    operator = await admin_actor(db_session, ["mall.aftersales.review", "mall.refunds.execute"])
    payment = await db_session.get(MallPayment, order.active_payment_id)
    refund = await execute_refund(
        db_session,
        operator,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-full-application-execute-001",
    )
    fact = refund_fact(refund, payment)
    for _ in range(20):
        await apply_verified_refund(db_session, refund.id, fact)
    await db_session.commit()

    assert order.status == "closed"
    assert order.refunded_goods_cent == order.goods_amount_cent == 20000
    assert order.refunded_freight_cent == order.freight_amount_cent == 1000
    assert order.refund_reserved_cent == 0 and aftersale.status == "completed"
    assert refund.status == "succeeded" and refund.active_slot is None
    assert all(sku.available_qty == 10 and sku.reserved_qty == 0 for sku in skus)
    assert all(line.refunded_quantity == line.quantity for line in items)
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(MallStockMovement.kind == "refund_return")
        )
        == 2
    )
    source = await db_session.scalar(
        select(MallConsumption).where(MallConsumption.order_id == order.id)
    )
    assert source.successful_goods_refund_cent == source.original_goods_cent == 20000
    assert source.performance_base_cent == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(MallJob.kind == "mall_invoice_refund_review")
        )
        == 1
    )
    assert await db_session.scalar(select(func.count()).select_from(MallRefund)) == 1


@pytest.mark.asyncio
async def test_partially_accepted_return_refunds_all_requested_units_without_double_restock(
    db_session, monkeypatch
):
    buyer, order, skus, items = await paid_order(db_session, monkeypatch)
    operator = await admin_actor(
        db_session,
        [
            "mall.aftersales.review",
            "mall.returns.receive",
            "mall.refunds.execute",
            "mall.shipments.write",
        ],
    )
    await ship_order(
        db_session,
        operator,
        order.id,
        ShipmentCreate(expectedVersion=order.version, courierCode="sf", trackingNo="SF12345678"),
        key="refund-return-original-shipment-001",
    )
    await db_session.commit()
    await db_session.refresh(order)
    assert await db_session.scalar(select(MallShipment.id).where(MallShipment.order_id == order.id))

    aftersale = await apply_aftersale(
        db_session,
        buyer,
        request(order, items[1], quantity=2, method="return_refund"),
        key="refund-return-application-flow-001",
    )
    settings = await db_session.get(MallSettings, 1)
    settings.return_address_snapshot = {
        "recipientName": "测试退货收件人",
        "addressLine": "虚构仓库地址",
    }
    aftersale = await decide_aftersale(
        db_session,
        operator,
        aftersale.id,
        AftersaleDecision(expectedVersion=aftersale.version, decision="approve", reason="同意退回"),
        key="refund-return-application-review-001",
    )
    aftersale = await submit_return_shipment(
        db_session,
        buyer,
        aftersale.id,
        ReturnShipment(
            expectedVersion=aftersale.version, courierCode="sf", trackingNo="SF87654321"
        ),
        key="refund-return-shipment-001",
    )
    aftersale_item = await db_session.scalar(
        select(MallAftersaleItem).where(MallAftersaleItem.aftersale_id == aftersale.id)
    )
    available_before_receipt = skus[1].available_qty
    aftersale = await receive_return(
        db_session,
        operator,
        aftersale.id,
        ReturnReceipt(
            expectedVersion=aftersale.version,
            result="partially_accepted",
            sellableItems=[SellableReturnLine(aftersaleItemId=str(aftersale_item.id), quantity=1)],
            reason="两件中一件可二次销售",
        ),
        key="refund-return-receipt-001",
    )
    assert skus[1].available_qty == available_before_receipt + 1

    payment = await db_session.get(MallPayment, order.active_payment_id)
    refund = await execute_refund(
        db_session,
        operator,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-return-execute-001",
    )
    await apply_verified_refund(db_session, refund.id, refund_fact(refund, payment))
    await db_session.commit()

    assert refund.status == "succeeded" and aftersale.status == "completed"
    assert order.refunded_goods_cent == 10000 and order.refunded_freight_cent == 0
    assert order.refund_reserved_cent == 0
    assert aftersale_item.quantity == 2 and aftersale_item.stock_return_quantity == 1
    assert items[1].returned_quantity == 2 and items[1].refunded_quantity == 2
    assert skus[1].available_qty == available_before_receipt + 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(
                MallStockMovement.aftersale_item_id == aftersale_item.id,
                MallStockMovement.kind == "return",
            )
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(
                MallStockMovement.aftersale_item_id == aftersale_item.id,
                MallStockMovement.kind == "refund_return",
            )
        )
        == 0
    )
