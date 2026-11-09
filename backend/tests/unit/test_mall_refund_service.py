"""Refund authority, original payment identity and terminal facts are durable."""

from datetime import datetime

import pytest
from sqlalchemy import func, select

from src.core.exceptions import ConflictException
from src.integrations.wechat_pay_types import RefundFact
from src.models.mall_catalog import MallStockMovement
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallPayment, MallRefund
from src.models.mall_operations import MallJob
from src.models.mall_trade import MallAftersaleItem
from src.schemas.mall_catalog import VersionAction
from src.services.mall_refund_service import apply_verified_refund, execute_refund
from tests.unit.test_mall_aftersale_service import admin_actor, paid_order, request


async def refund_ready(db, monkeypatch):
    from src.schemas.mall_aftersale import AftersaleDecision
    from src.services.mall_aftersale_service import apply_aftersale, decide_aftersale

    buyer, order, skus, items = await paid_order(db, monkeypatch)
    aftersale = await apply_aftersale(
        db,
        buyer,
        request(order, items[1]),
        key="refund-ready-aftersale-001",
    )
    finance = await admin_actor(
        db,
        ["mall.aftersales.review", "mall.refunds.execute", "mall.refunds.query"],
    )
    aftersale = await decide_aftersale(
        db,
        finance,
        aftersale.id,
        AftersaleDecision(
            expectedVersion=aftersale.version, decision="approve", reason="核实后同意退款"
        ),
        key="refund-ready-decision-001",
    )
    payment = await db.get(MallPayment, order.active_payment_id)
    await db.commit()
    return finance, order, aftersale, skus, items, payment


def refund_fact(refund, payment, *, status="SUCCESS"):
    return RefundFact(
        out_refund_no=refund.out_refund_no,
        out_trade_no=payment.out_trade_no,
        status=status,
        total_cent=refund.original_amount_cent,
        refund_cent=refund.total_cent,
        currency="CNY",
        transaction_id="synthetic-channel-id",
        channel_refund_id="synthetic-channel-refund",
        success_at=datetime(2026, 11, 6, 10, 30) if status == "SUCCESS" else None,
    )


@pytest.mark.asyncio
async def test_finance_execution_reserves_one_channel_refund_identity_and_is_idempotent(
    db_session, monkeypatch
):
    finance, order, aftersale, _, _, _ = await refund_ready(db_session, monkeypatch)
    action = VersionAction(expectedVersion=aftersale.version)
    first = await execute_refund(
        db_session, finance, aftersale.id, action, key="refund-execute-intent-001"
    )
    replay = await execute_refund(
        db_session, finance, aftersale.id, action, key="refund-execute-intent-001"
    )
    second_key = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-execute-intent-002",
    )
    await db_session.commit()

    assert first.id == replay.id == second_key.id
    assert first.status == "prepared" and first.active_slot == 1
    assert first.out_refund_no.startswith("R") and len(first.out_refund_no) == 32
    assert first.payment_id == order.active_payment_id
    assert first.order_id == order.id and first.total_cent == 5000
    assert order.refund_reserved_cent == first.total_cent  # no second reservation
    assert aftersale.status == "refunding"
    assert await db_session.scalar(select(func.count()).select_from(MallRefund)) == 1
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallJob).where(MallJob.kind == "mall_refund_execute")
        )
        == 1
    )


@pytest.mark.asyncio
async def test_verified_success_replay_updates_money_stock_performance_and_jobs_once(
    db_session, monkeypatch
):
    finance, order, aftersale, skus, items, payment = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-success-execute-001",
    )
    aftersale_item = await db_session.scalar(
        select(MallAftersaleItem).where(MallAftersaleItem.aftersale_id == aftersale.id)
    )
    fact = refund_fact(refund, payment)
    for _ in range(20):
        await apply_verified_refund(db_session, refund.id, fact)
    await db_session.commit()

    assert refund.status == "succeeded" and refund.active_slot is None
    assert order.refunded_goods_cent == 5000 and order.refunded_freight_cent == 0
    assert order.refund_reserved_cent == 0 and aftersale.status == "completed"
    assert items[1].refunded_quantity == 1 and items[1].aftersale_reserved_quantity == 0
    assert skus[1].available_qty == 9  # the unshipped unit returned once
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallStockMovement)
            .where(
                MallStockMovement.event_key == f"aftersale:{aftersale_item.id}:pre-shipment-refund"
            )
        )
        == 1
    )
    source = await db_session.scalar(
        select(MallConsumption).where(MallConsumption.order_id == order.id)
    )
    assert source.successful_goods_refund_cent == 5000
    assert source.performance_base_cent == source.original_goods_cent == 20000
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(MallJob.kind == "mall_invoice_refund_review")
        )
        == 1
    )


@pytest.mark.asyncio
async def test_abnormal_refund_keeps_money_and_quantity_holds_for_manual_work(
    db_session, monkeypatch
):
    finance, order, aftersale, _, items, payment = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-abnormal-execute-001",
    )
    await apply_verified_refund(
        db_session, refund.id, refund_fact(refund, payment, status="ABNORMAL")
    )
    await db_session.commit()

    assert refund.status == "abnormal" and refund.active_slot == 1
    assert aftersale.status == "disputed" and order.refund_reserved_cent == 5000
    assert items[1].aftersale_reserved_quantity == 1 and items[1].refunded_quantity == 0
    assert (
        await db_session.scalar(
            select(func.count()).select_from(MallJob).where(MallJob.status == "manual")
        )
        >= 1
    )


@pytest.mark.asyncio
async def test_processing_fact_keeps_one_hold_and_cannot_be_downgraded_by_stale_status(
    db_session, monkeypatch
):
    finance, order, aftersale, _, _, payment = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-processing-execute-001",
    )
    await apply_verified_refund(
        db_session, refund.id, refund_fact(refund, payment, status="PROCESSING")
    )
    await apply_verified_refund(
        db_session, refund.id, refund_fact(refund, payment, status="PROCESSING")
    )
    await db_session.commit()

    assert refund.status == "processing" and refund.active_slot == 1
    assert order.refund_reserved_cent == 5000 and order.refunded_goods_cent == 0


@pytest.mark.asyncio
async def test_refund_fact_with_mismatched_order_or_amount_is_rejected_without_mutation(
    db_session, monkeypatch
):
    finance, order, aftersale, _, _, _ = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="refund-mismatch-execute-001",
    )
    with pytest.raises(ConflictException):
        await apply_verified_refund(
            db_session,
            refund.id,
            RefundFact(
                out_refund_no=refund.out_refund_no,
                out_trade_no="ALIEN-ORDER",
                status="SUCCESS",
                total_cent=refund.original_amount_cent,
                refund_cent=refund.total_cent,
                currency="CNY",
                channel_refund_id="synthetic-channel-refund",
                success_at=datetime(2026, 11, 6, 10, 30),
            ),
        )
    assert order.refunded_goods_cent == 0 and order.refund_reserved_cent == 5000
