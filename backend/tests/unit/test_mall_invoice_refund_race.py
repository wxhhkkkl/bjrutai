"""A red invoice records tax correction only; refund owns consumption changes."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.models.mall_base import utc_now
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallInvoice, MallInvoiceRequest, MallPayment
from src.models.mall_operations import MallFile, MallJob
from src.models.performance_adjustment import PerformanceAdjustment
from tests.unit.test_mall_aftersale_service import (
    admin_actor,
    paid_order,
    request as aftersale_request,
)


@pytest.mark.asyncio
async def test_successful_partial_refund_and_red_invoice_replay_change_performance_once(
    db_session, monkeypatch
):
    from src.schemas.mall_catalog import VersionAction
    from src.schemas.mall_invoice import RedInvoiceRecord, RedPendingUpdate
    from src.services.mall_aftersale_service import apply_aftersale
    from src.services.mall_invoice_service import record_red_invoice, set_red_pending
    from src.services.mall_refund_service import apply_verified_refund, execute_refund
    from tests.unit.test_mall_refund_service import refund_fact

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    finance = await admin_actor(
        db_session,
        ["mall.aftersales.review", "mall.refunds.execute", "mall.invoices.write"],
    )
    invoice_request = MallInvoiceRequest(
        request_no=f"IR{uuid4().hex[:28]}",
        order_id=order.id,
        buyer_user_id=buyer.actor_id,
        buyer_type="personal",
        title="个人",
        invoice_type="digital_normal",
        requested_goods_cent=order.goods_amount_cent,
        requested_freight_cent=order.freight_amount_cent,
        source_order_version=order.version,
        status="delivered",
        active_slot=1,
        claimed_by=finance.actor_id,
    )
    db_session.add(invoice_request)
    blue_file = MallFile(
        object_key=f"mall/verified/invoice/blue-{uuid4().hex}.pdf",
        purpose="invoice_pdf",
        owner_actor_type="admin",
        owner_actor_id=finance.actor_id,
        order_id=order.id,
        mime="application/pdf",
        size=4096,
        sha256="d" * 64,
        status="bound",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db_session.add(blue_file)
    await db_session.flush()
    blue = MallInvoice(
        request_id=invoice_request.id,
        order_id=order.id,
        kind="blue",
        seller_identity="测试销售主体",
        invoice_no=f"INV-{uuid4().hex[:20]}",
        issued_at=utc_now(),
        total_cent=order.paid_amount_cent,
        seller_snapshot={"name": "测试主体"},
        file_id=blue_file.id,
        status="valid",
        recorded_by=finance.actor_id,
    )
    db_session.add(blue)
    await db_session.flush()
    blue_file.invoice_id = blue.id

    application = await apply_aftersale(
        db_session,
        buyer,
        aftersale_request(order, items[1]),
        key="invoice-refund-race-apply-001",
    )
    payment = await db_session.get(MallPayment, order.active_payment_id)
    refund = await execute_refund(
        db_session,
        finance,
        application.id,
        VersionAction(expectedVersion=application.version),
        key="invoice-refund-race-execute-001",
    )
    await apply_verified_refund(
        db_session, refund.id, refund_fact(refund, payment)
    )

    source = await db_session.scalar(
        select(MallConsumption).where(MallConsumption.order_id == order.id)
    )
    base_after_refund = source.performance_base_cent
    source_version_after_refund = source.source_version
    assert source.successful_goods_refund_cent == 5000
    assert base_after_refund == source.original_goods_cent
    assert blue.status == "red_pending"
    assert await db_session.scalar(
        select(func.count()).select_from(MallJob).where(
            MallJob.kind == "mall_invoice_refund_review"
        )
    ) == 1
    adjustments_before_red = await db_session.scalar(
        select(func.count()).select_from(PerformanceAdjustment)
    )

    pending = await set_red_pending(
        db_session,
        finance,
        blue.id,
        RedPendingUpdate(
            expectedVersion=blue.version,
            targetStatus="red_pending",
            reason="退款成功待部分红冲",
        ),
        key="invoice-refund-race-red-pending-001",
    )
    red_file = MallFile(
        object_key=f"mall/verified/invoice/red-{uuid4().hex}.pdf",
        purpose="invoice_pdf",
        owner_actor_type="admin",
        owner_actor_id=finance.actor_id,
        order_id=order.id,
        mime="application/pdf",
        size=2048,
        sha256="e" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db_session.add(red_file)
    await db_session.flush()
    record = RedInvoiceRecord(
        expectedVersion=pending.version,
        invoiceNo=f"RED-{uuid4().hex[:20]}",
        issuedAt=utc_now(),
        totalCent=refund.total_cent,
        fileId=str(red_file.id),
        reason="依据真实部分退款回传红票",
    )
    first = await record_red_invoice(
        db_session,
        finance,
        blue.id,
        record,
        key="invoice-refund-race-red-record-001",
    )
    replay = await record_red_invoice(
        db_session,
        finance,
        blue.id,
        record,
        key="invoice-refund-race-red-record-001",
    )
    await db_session.refresh(source)
    await db_session.refresh(blue)
    assert first.id == replay.id and first.original_invoice_id == blue.id
    assert blue.status == "partially_red"
    assert source.performance_base_cent == base_after_refund
    assert source.source_version == source_version_after_refund
    assert await db_session.scalar(
        select(func.count()).select_from(PerformanceAdjustment)
    ) == adjustments_before_red
    assert await db_session.scalar(
        select(func.count()).select_from(MallInvoice).where(MallInvoice.kind == "red")
    ) == 1
    assert await db_session.scalar(
        select(func.count()).select_from(MallJob).where(
            MallJob.kind == "mall_invoice_refund_review"
        )
    ) == 1

