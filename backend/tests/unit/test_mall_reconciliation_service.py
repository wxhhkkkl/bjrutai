"""Evidence-backed reconciliation keeps channel, refund and local facts distinct."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.core.exceptions import ConflictException, ValidationException
from src.models.mall_base import utc_now
from src.models.mall_finance import (
    MallReconciliationBatch,
    MallReconciliationDifference,
)
from src.models.mall_operations import MallFile
from tests.unit.test_mall_aftersale_service import admin_actor
from tests.unit.test_mall_payment_service import payable, success
from tests.unit.test_mall_refund_service import refund_fact, refund_ready


async def paid_at(db, monkeypatch, *, openid, occurred_at):
    from src.services.mall_payment_service import apply_verified_payment

    _, order, _, payment = await payable(db, monkeypatch, openid=openid)
    fact = replace(
        success(payment, order, paid_at=occurred_at),
        transaction_id="synthetic-recon-payment-" + uuid4().hex,
        openid=openid,
    )
    await apply_verified_payment(db, payment.id, fact)
    return order, payment


async def evidence_file(db, *, admin_id, content_hash=None):
    file = MallFile(
        object_key=f"mall/reconciliation_evidence/admin/{uuid4().hex}.pdf",
        purpose="reconciliation_evidence",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        order_id=None,
        mime="application/pdf",
        size=4096,
        sha256=content_hash or "d" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db.add(file)
    await db.flush()
    return file


@pytest.mark.asyncio
async def test_reconciliation_uses_beijing_day_and_success_timestamps_only(db_session, monkeypatch):
    from src.schemas.mall_catalog import VersionAction
    from src.schemas.mall_reconciliation import ReconciliationCreate
    from src.services.mall_reconciliation_service import create_reconciliation
    from src.services.mall_refund_service import apply_verified_refund, execute_refund

    business_date = date(2026, 11, 6)
    included_order, included_payment = await paid_at(
        db_session,
        monkeypatch,
        openid="recon-payment-start-" + uuid4().hex,
        occurred_at=datetime(2026, 11, 5, 16, 0, 0),  # Beijing midnight, inclusive.
    )
    await paid_at(
        db_session,
        monkeypatch,
        openid="recon-payment-before-" + uuid4().hex,
        occurred_at=datetime(2026, 11, 5, 15, 59, 59),  # Previous Beijing day.
    )
    await paid_at(
        db_session,
        monkeypatch,
        openid="recon-payment-end-" + uuid4().hex,
        occurred_at=datetime(2026, 11, 6, 16, 0, 0),  # Next Beijing day, exclusive.
    )
    _, pending_order, _, pending_payment = await payable(
        db_session, monkeypatch, openid="recon-payment-unknown-" + uuid4().hex
    )
    pending_payment.status = "unknown"
    pending_payment.last_error_code = "gateway_timeout"

    finance, refund_order, aftersale, _, _, payment = await refund_ready(db_session, monkeypatch)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="recon-day-refund-submit-001",
    )
    refund_result = replace(
        refund_fact(refund, payment),
        channel_refund_id="synthetic-recon-refund-" + uuid4().hex,
        success_at=datetime(2026, 11, 5, 16, 0, 0),  # Refund success time, not request time.
    )
    await apply_verified_refund(db_session, refund.id, refund_result)

    reviewer = await admin_actor(
        db_session, ["mall.reconciliations.read", "mall.reconciliations.write"]
    )
    statement = await evidence_file(db_session, admin_id=reviewer.actor_id)
    data = ReconciliationCreate(
        business_date=business_date,
        statement_file_id=str(statement.id),
        expected_paid_cent=included_order.payable_amount_cent,
        expected_refund_cent=refund.total_cent,
        evidence_note="虚构渠道日账单，仅用于本地边界验收",
    )

    batch = await create_reconciliation(db_session, reviewer, data, key="recon-day-create-0000001")
    replay = await create_reconciliation(db_session, reviewer, data, key="recon-day-create-0000001")
    await db_session.commit()

    assert batch.id == replay.id
    assert batch.business_date == business_date
    assert batch.channel == "wechat" and batch.seller_identity == "test-merchant"
    assert batch.statement_sha256 == statement.sha256
    assert batch.expected_paid_cent == batch.local_paid_cent == included_order.payable_amount_cent
    assert batch.expected_refund_cent == batch.local_refund_cent == refund.total_cent
    assert batch.status == "draft"
    assert included_payment.status == "succeeded"
    assert pending_payment.status == "unknown" and pending_payment.confirmed_at is None
    assert pending_order.paid_amount_cent == 0
    assert (
        refund_order.refunded_goods_cent + refund_order.refunded_freight_cent == refund.total_cent
    )
    assert await db_session.scalar(select(func.count()).select_from(MallReconciliationBatch)) == 1


@pytest.mark.asyncio
async def test_unlinked_difference_needs_assignment_evidence_and_review_before_close(
    db_session, monkeypatch
):
    from src.schemas.mall_aftersale import ReasonAction
    from src.schemas.mall_reconciliation import (
        DifferenceCreate,
        DifferenceUpdate,
        ReconciliationCreate,
    )
    from src.services.mall_reconciliation_service import (
        add_difference,
        close_reconciliation,
        create_reconciliation,
        update_difference,
    )

    _, order, _, unknown_payment = await payable(
        db_session, monkeypatch, openid="recon-difference-unknown-" + uuid4().hex
    )
    unknown_payment.status = "unknown"
    finance = await admin_actor(
        db_session, ["mall.reconciliations.read", "mall.reconciliations.write"]
    )
    statement = await evidence_file(db_session, admin_id=finance.actor_id)
    batch = await create_reconciliation(
        db_session,
        finance,
        ReconciliationCreate(
            business_date=date(2026, 11, 6),
            statement_file_id=str(statement.id),
            expected_paid_cent=0,
            expected_refund_cent=0,
            evidence_note="虚构的空白日账单",
        ),
        key="recon-difference-batch-0001",
    )
    difference = await add_difference(
        db_session,
        finance,
        batch.id,
        DifferenceCreate(
            external_reference="SYNTHETIC-UNLINKED-001",
            difference_type="unlinked",
            expected_cent=0,
            actual_cent=3500,
            reason="渠道账单记录暂时无法关联本地支付",
        ),
        key="recon-difference-add-000001",
    )
    assert difference.status == "open"
    assert difference.order_id is None and difference.payment_id is None
    assert difference.external_reference == "SYNTHETIC-UNLINKED-001"
    await db_session.refresh(batch)

    with pytest.raises(ConflictException, match="未决差异|未关闭|差异"):
        await close_reconciliation(
            db_session,
            finance,
            batch.id,
            ReasonAction(expectedVersion=batch.version, reason="尝试提前关闭"),
            key="recon-close-open-difference-01",
        )
    with pytest.raises(ConflictException, match="证据|复核|差异"):
        await update_difference(
            db_session,
            finance,
            difference.id,
            DifferenceUpdate(
                expectedVersion=difference.version,
                targetStatus="closed",
                reason="无证据不可标为一致",
            ),
            key="recon-difference-fake-close-01",
        )

    processing = await update_difference(
        db_session,
        finance,
        difference.id,
        DifferenceUpdate(
            expectedVersion=difference.version,
            targetStatus="processing",
            assignedTo=str(finance.actor_id),
            reason="财务开始核查渠道记录",
        ),
        key="recon-difference-assign-0001",
    )
    assert processing.status == "processing"
    resolution_file = await evidence_file(
        db_session, admin_id=finance.actor_id, content_hash="e" * 64
    )
    review = await update_difference(
        db_session,
        finance,
        difference.id,
        DifferenceUpdate(
            expectedVersion=processing.version,
            targetStatus="review",
            reason="已取得虚构的渠道核查材料",
            evidenceFileIds=[str(resolution_file.id)],
        ),
        key="recon-difference-review-01",
    )
    assert review.status == "review"
    closed_difference = await update_difference(
        db_session,
        finance,
        difference.id,
        DifferenceUpdate(
            expectedVersion=review.version,
            targetStatus="closed",
            reason="证据核对后确认差异原因并处理",
            evidenceFileIds=[str(resolution_file.id)],
        ),
        key="recon-difference-close-0001",
    )
    assert closed_difference.status == "closed"

    await db_session.refresh(batch)
    closed_batch = await close_reconciliation(
        db_session,
        finance,
        batch.id,
        ReasonAction(expectedVersion=batch.version, reason="日账差异均已处理并复核"),
        key="recon-close-reviewed-batch-01",
    )
    await db_session.commit()
    assert closed_batch.status == "closed"
    assert unknown_payment.status == "unknown"
    assert order.paid_amount_cent == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallReconciliationDifference)
            .where(MallReconciliationDifference.status != "closed")
        )
        == 0
    )


@pytest.mark.asyncio
async def test_reconciliation_rejects_unverified_statement_file(db_session, monkeypatch):
    from src.schemas.mall_reconciliation import ReconciliationCreate
    from src.services.mall_reconciliation_service import create_reconciliation

    finance = await admin_actor(db_session, ["mall.reconciliations.write"])
    invalid_statement = MallFile(
        object_key=f"mall/reconciliation_evidence/admin/{uuid4().hex}.pdf",
        purpose="reconciliation_evidence",
        owner_actor_type="admin",
        owner_actor_id=finance.actor_id,
        mime="application/pdf",
        size=4096,
        sha256="f" * 64,
        status="uploading",
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db_session.add(invalid_statement)
    await db_session.flush()
    with pytest.raises((ConflictException, ValidationException), match="核验|文件|证据"):
        await create_reconciliation(
            db_session,
            finance,
            ReconciliationCreate(
                business_date=date(2026, 11, 6),
                statement_file_id=str(invalid_statement.id),
                expected_paid_cent=0,
                expected_refund_cent=0,
                evidence_note="不得用未核验账单关闭对账",
            ),
            key="recon-unverified-statement-001",
        )
    assert await db_session.scalar(select(func.count()).select_from(MallReconciliationBatch)) == 0
