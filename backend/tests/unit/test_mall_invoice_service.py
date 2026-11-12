"""Invoice lifecycle state changes must preserve issued facts and money semantics."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.core.exceptions import ConflictException, ForbiddenException, ValidationException
from src.models.mall_base import utc_now
from src.models.mall_consumption import MallConsumption
from src.models.mall_finance import MallInvoice, MallInvoiceRequest, MallPayment
from src.models.mall_operations import MallFile, MallJob
from tests.unit.test_mall_aftersale_service import admin_actor, paid_order


async def verified_pdf(db, *, order_id, admin_id, label):
    file = MallFile(
        object_key=f"mall/verified/invoice-unit/{label}-{uuid4().hex}.pdf",
        purpose="invoice_pdf",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        order_id=order_id,
        mime="application/pdf",
        size=4096,
        sha256="b" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db.add(file)
    await db.flush()
    return file


@pytest.mark.asyncio
async def test_create_personal_or_company_request_uses_paid_order_amount_and_single_active_slot(
    db_session, monkeypatch
):
    from src.schemas.mall_invoice import InvoiceCreate
    from src.services.mall_invoice_service import create_invoice_request

    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    personal = InvoiceCreate(
        orderId=str(order.id),
        expectedOrderVersion=order.version,
        buyerType="personal",
        title="个人",
        invoiceType="digital_normal",
    )
    first = await create_invoice_request(
        db_session, buyer, personal, key="invoice-unit-create-personal-001"
    )
    replay = await create_invoice_request(
        db_session, buyer, personal, key="invoice-unit-create-personal-001"
    )
    duplicate = await create_invoice_request(
        db_session, buyer, personal, key="invoice-unit-create-personal-002"
    )
    assert first.id == replay.id == duplicate.id
    assert first.requested_goods_cent == order.goods_amount_cent
    assert first.requested_freight_cent == order.freight_amount_cent
    assert first.active_slot == 1
    assert await db_session.scalar(select(func.count()).select_from(MallInvoiceRequest)) == 1

    invalid_company = InvoiceCreate(
        orderId=str(order.id),
        expectedOrderVersion=order.version,
        buyerType="company",
        title="公司抬头",
        invoiceType="digital_normal",
    )
    with pytest.raises(ValidationException):
        await create_invoice_request(
            db_session, buyer, invalid_company, key="invoice-unit-company-missing-tax-001"
        )


@pytest.mark.asyncio
async def test_claim_info_correction_and_withdraw_are_versioned_and_permission_checked(
    db_session, monkeypatch
):
    from src.schemas.mall_invoice import InvoiceCreate, InvoicePatch
    from src.schemas.mall_aftersale import ReasonAction
    from src.schemas.mall_catalog import VersionAction
    from src.services.mall_invoice_service import (
        claim_invoice_request,
        create_invoice_request,
        need_invoice_info,
        update_invoice_request,
        withdraw_invoice_request,
    )

    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    invoice = await create_invoice_request(
        db_session,
        buyer,
        InvoiceCreate(
            orderId=str(order.id),
            expectedOrderVersion=order.version,
            buyerType="personal",
            title="初始抬头",
            invoiceType="digital_normal",
        ),
        key="invoice-unit-info-create-001",
    )
    reader = await admin_actor(db_session, ["mall.invoices.read"])
    with pytest.raises(ForbiddenException):
        await claim_invoice_request(
            db_session,
            reader,
            invoice.id,
            VersionAction(expectedVersion=invoice.version),
            key="invoice-unit-claim-readonly-001",
        )

    writer = await admin_actor(db_session, ["mall.invoices.write"])
    claimed = await claim_invoice_request(
        db_session,
        writer,
        invoice.id,
        VersionAction(expectedVersion=invoice.version),
        key="invoice-unit-claim-001",
    )
    needs_info = await need_invoice_info(
        db_session,
        writer,
        invoice.id,
        ReasonAction(expectedVersion=claimed.version, reason="请确认抬头"),
        key="invoice-unit-needs-info-001",
    )
    assert needs_info.info_request_reason == "请确认抬头"
    corrected = await update_invoice_request(
        db_session,
        buyer,
        invoice.id,
        InvoicePatch(expectedVersion=needs_info.version, title="确认后的抬头"),
        key="invoice-unit-patch-001",
    )
    assert corrected.status == "submitted" and corrected.title == "确认后的抬头"
    assert corrected.info_request_reason is None
    withdrawn = await withdraw_invoice_request(
        db_session,
        buyer,
        invoice.id,
        ReasonAction(expectedVersion=corrected.version, reason="暂不需要"),
        key="invoice-unit-withdraw-001",
    )
    assert withdrawn.status == "withdrawn" and withdrawn.active_slot is None


@pytest.mark.asyncio
async def test_invoice_record_rejects_amount_mismatch_but_persists_real_issue_after_order_changed(
    db_session, monkeypatch
):
    from src.schemas.mall_invoice import InvoiceCreate, InvoiceIssueRecord
    from src.schemas.mall_catalog import VersionAction
    from src.services.mall_invoice_service import (
        claim_invoice_request,
        create_invoice_request,
        record_invoice_issue,
    )
    from src.schemas.mall_aftersale import AftersaleDecision
    from src.services.mall_aftersale_service import apply_aftersale, decide_aftersale
    from src.services.mall_refund_service import apply_verified_refund, execute_refund
    from tests.unit.test_mall_aftersale_service import request as aftersale_request
    from tests.unit.test_mall_refund_service import refund_fact

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    invoice_request = await create_invoice_request(
        db_session,
        buyer,
        InvoiceCreate(
            orderId=str(order.id),
            expectedOrderVersion=order.version,
            buyerType="personal",
            title="个人抬头",
            invoiceType="digital_normal",
        ),
        key="invoice-unit-record-create-001",
    )
    writer = await admin_actor(
        db_session,
        ["mall.invoices.write", "mall.aftersales.review", "mall.refunds.execute"],
    )
    claimed = await claim_invoice_request(
        db_session,
        writer,
        invoice_request.id,
        VersionAction(expectedVersion=invoice_request.version),
        key="invoice-unit-claim-record-001",
    )
    file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="actual-issue"
    )
    mismatched = InvoiceIssueRecord(
        expectedVersion=claimed.version,
        invoiceNo="INV-UNIT-REAL-001",
        issuedAt=utc_now(),
        sellerIdentity="北京鲁泰测试销售主体",
        totalCent=order.paid_amount_cent - 1,
        fileId=str(file.id),
    )
    with pytest.raises(ConflictException):
        await record_invoice_issue(
            db_session, writer, invoice_request.id, mismatched, key="invoice-unit-bad-total-001"
        )
    assert await db_session.scalar(select(func.count()).select_from(MallInvoice)) == 0

    aftersale = await apply_aftersale(
        db_session,
        buyer,
        aftersale_request(order, items[1]),
        key="invoice-unit-refund-apply-001",
    )
    aftersale = await decide_aftersale(
        db_session,
        writer,
        aftersale.id,
        AftersaleDecision(
            expectedVersion=aftersale.version,
            decision="approve",
            reason="发票与退款竞态样例",
        ),
        key="invoice-unit-refund-review-001",
    )
    payment = await db_session.get(MallPayment, order.active_payment_id)
    refund = await execute_refund(
        db_session,
        writer,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="invoice-unit-refund-execute-001",
    )
    await apply_verified_refund(db_session, refund.id, refund_fact(refund, payment))
    source = await db_session.scalar(
        select(MallConsumption).where(MallConsumption.order_id == order.id)
    )
    assert source is not None
    assert source.successful_goods_refund_cent == 5000
    assert source.performance_base_cent == source.original_goods_cent

    actual = InvoiceIssueRecord(
        expectedVersion=claimed.version,
        invoiceNo="INV-UNIT-REAL-001",
        issuedAt=utc_now(),
        sellerIdentity="北京鲁泰测试销售主体",
        # The order has already recorded a successful partial refund. Preserve
        # a real invoice for the resulting net amount and route it to review.
        totalCent=order.paid_amount_cent - 5000,
        fileId=str(file.id),
    )
    recorded = await record_invoice_issue(
        db_session, writer, invoice_request.id, actual, key="invoice-unit-real-issue-001"
    )
    await db_session.flush()
    assert recorded.invoice_no == "INV-UNIT-REAL-001"
    assert recorded.total_cent == order.paid_amount_cent - 5000
    assert recorded.status == "red_pending"
    assert invoice_request.status == "unknown"
    assert await db_session.scalar(
        select(func.count()).select_from(MallJob).where(
            MallJob.kind == "mall_invoice_refund_review"
        )
    ) >= 1
    assert await db_session.scalar(select(func.count()).select_from(MallInvoice)) == 1


@pytest.mark.asyncio
async def test_partial_red_full_red_and_replacement_keep_original_rows_and_allow_same_invoice_file_retry(
    db_session, monkeypatch
):
    from src.schemas.mall_invoice import (
        InvoiceCreate,
        InvoiceFileReplace,
        InvoiceIssueRecord,
        RedInvoiceRecord,
        RedPendingUpdate,
    )
    from src.schemas.mall_catalog import VersionAction
    from src.services.mall_invoice_service import (
        claim_invoice_request,
        create_invoice_request,
        record_invoice_issue,
        record_red_invoice,
        replace_invoice_file,
        set_red_pending,
    )

    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    request = await create_invoice_request(
        db_session,
        buyer,
        InvoiceCreate(
            orderId=str(order.id),
            expectedOrderVersion=order.version,
            buyerType="personal",
            title="个人抬头",
            invoiceType="digital_normal",
        ),
        key="invoice-unit-red-create-001",
    )
    writer = await admin_actor(db_session, ["mall.invoices.write"])
    claimed = await claim_invoice_request(
        db_session,
        writer,
        request.id,
        VersionAction(expectedVersion=request.version),
        key="invoice-unit-red-claim-001",
    )
    blue_file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="red-blue"
    )
    blue = await record_invoice_issue(
        db_session,
        writer,
        request.id,
        InvoiceIssueRecord(
            expectedVersion=claimed.version,
            invoiceNo="INV-UNIT-BLUE-001",
            issuedAt=utc_now(),
            sellerIdentity="北京鲁泰测试销售主体",
            totalCent=order.paid_amount_cent,
            fileId=str(blue_file.id),
        ),
        key="invoice-unit-blue-001",
    )
    partial_pending = await set_red_pending(
        db_session,
        writer,
        blue.id,
        RedPendingUpdate(
            expectedVersion=blue.version,
            targetStatus="red_pending",
            reason="部分红冲",
        ),
        key="invoice-unit-partial-red-pending-001",
    )
    partial_file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="red-partial"
    )
    partial = await record_red_invoice(
        db_session,
        writer,
        blue.id,
        RedInvoiceRecord(
            expectedVersion=partial_pending.version,
            invoiceNo="INV-UNIT-RED-001",
            issuedAt=utc_now(),
            totalCent=5000,
            fileId=str(partial_file.id),
            reason="部分退款",
        ),
        key="invoice-unit-partial-red-record-001",
    )
    assert partial.kind == "red" and partial.original_invoice_id == blue.id
    await db_session.refresh(blue)
    assert blue.status == "partially_red"

    premature_replacement_file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="red-premature-replacement"
    )
    with pytest.raises(ConflictException):
        await record_invoice_issue(
            db_session,
            writer,
            request.id,
            InvoiceIssueRecord(
                expectedVersion=request.version,
                invoiceNo="INV-UNIT-BLUE-PREMATURE",
                issuedAt=utc_now(),
                sellerIdentity="北京鲁泰测试销售主体",
                totalCent=order.paid_amount_cent,
                fileId=str(premature_replacement_file.id),
                replacementForId=str(blue.id),
            ),
            key="invoice-unit-replacement-before-release-001",
        )

    remaining_red_pending = await set_red_pending(
        db_session,
        writer,
        blue.id,
        RedPendingUpdate(
            expectedVersion=blue.version,
            targetStatus="awaiting_counterparty",
            reason="替代蓝票前冲销旧票剩余覆盖",
        ),
        key="invoice-unit-red-remainder-pending-001",
    )
    too_large_red_file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="red-too-large"
    )
    with pytest.raises(ConflictException):
        await record_red_invoice(
            db_session,
            writer,
            blue.id,
            RedInvoiceRecord(
                expectedVersion=remaining_red_pending.version,
                invoiceNo="INV-UNIT-RED-TOO-LARGE",
                issuedAt=utc_now(),
                totalCent=order.paid_amount_cent,
                fileId=str(too_large_red_file.id),
                reason="超过旧蓝票剩余覆盖",
            ),
            key="invoice-unit-red-over-coverage-001",
        )
    remaining_red_file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="red-remainder"
    )
    remaining_red = await record_red_invoice(
        db_session,
        writer,
        blue.id,
        RedInvoiceRecord(
            expectedVersion=remaining_red_pending.version,
            invoiceNo="INV-UNIT-RED-REMAINDER-001",
            issuedAt=utc_now(),
            totalCent=order.paid_amount_cent - 5000,
            fileId=str(remaining_red_file.id),
            reason="全额冲销旧蓝票剩余覆盖",
        ),
        key="invoice-unit-red-remainder-record-001",
    )
    await db_session.refresh(blue)
    assert remaining_red.original_invoice_id == blue.id
    assert blue.status == "fully_red"

    replacement_file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="red-replacement"
    )
    replacement = await record_invoice_issue(
        db_session,
        writer,
        request.id,
        InvoiceIssueRecord(
            expectedVersion=request.version,
            invoiceNo="INV-UNIT-BLUE-002",
            issuedAt=utc_now(),
            sellerIdentity="北京鲁泰测试销售主体",
            totalCent=order.paid_amount_cent,
            fileId=str(replacement_file.id),
            replacementForId=str(blue.id),
        ),
        key="invoice-unit-replacement-001",
    )
    assert replacement.replacement_for_id == blue.id

    full_pending = await set_red_pending(
        db_session,
        writer,
        replacement.id,
        RedPendingUpdate(
            expectedVersion=replacement.version,
            targetStatus="awaiting_counterparty",
            reason="后续申请全额红冲",
        ),
        key="invoice-unit-full-red-pending-001",
    )
    full_file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="red-full"
    )
    full = await record_red_invoice(
        db_session,
        writer,
        replacement.id,
        RedInvoiceRecord(
            expectedVersion=full_pending.version,
            invoiceNo="INV-UNIT-RED-002",
            issuedAt=utc_now(),
            totalCent=order.paid_amount_cent,
            fileId=str(full_file.id),
            reason="全额红冲",
        ),
        key="invoice-unit-full-red-record-001",
    )
    await db_session.refresh(replacement)
    assert replacement.status == "fully_red" and full.original_invoice_id == replacement.id

    retry_file = await verified_pdf(
        db_session, order_id=order.id, admin_id=writer.actor_id, label="red-retry"
    )
    replaced = await replace_invoice_file(
        db_session,
        writer,
        full.id,
        InvoiceFileReplace(
            expectedVersion=full.version,
            fileId=str(retry_file.id),
            reason="同一红票补交清晰PDF",
        ),
        key="invoice-unit-file-replace-001",
    )
    await db_session.refresh(full)
    assert replaced.id == full.id and full.invoice_no == "INV-UNIT-RED-002"
    assert full.file_id == retry_file.id and full.kind == "red"
    assert await db_session.scalar(select(func.count()).select_from(MallInvoice)) == 5
