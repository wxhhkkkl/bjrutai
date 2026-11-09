"""Synthetic admin flow for Beijing-day finance reconciliation."""

import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from src.models.mall_base import utc_now
from src.models.mall_operations import MallFile
from tests.contract.test_admin_mall_orders import admin
from tests.unit.test_mall_payment_service import payable
from tests.unit.test_mall_reconciliation_service import paid_at
from tests.unit.test_mall_refund_service import refund_fact, refund_ready


async def _refund_at(db_session, monkeypatch, success_at, key_suffix):
    from src.models.user import User
    from src.schemas.mall_catalog import VersionAction
    from src.services.mall_refund_service import apply_verified_refund, execute_refund

    finance, order, aftersale, _skus, _items, payment = await refund_ready(
        db_session, monkeypatch
    )
    # The shared refund fixture uses one default openid; keep its synthetic buyer
    # unique so this integration can exercise several independent refunds.
    buyer = await db_session.get(User, order.buyer_user_id)
    buyer.openid = f"recon-flow-refund-{key_suffix}-{uuid4().hex}"
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key=f"recon-flow-refund-submit-{key_suffix}",
    )
    fact = replace(
        refund_fact(refund, payment),
        transaction_id=payment.channel_transaction_id,
        channel_refund_id=f"synthetic-recon-refund-{key_suffix}-{uuid4().hex[:8]}",
        success_at=success_at,
    )
    await apply_verified_refund(db_session, refund.id, fact)
    return refund


async def _verified_statement(db_session, admin_id, content):
    row = MallFile(
        object_key=f"mall/verified/reconciliation-evidence/{uuid4().hex}.csv",
        purpose="reconciliation_evidence",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        order_id=None,
        mime="text/csv",
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest.mark.asyncio
async def test_synthetic_daily_statement_reconciles_boundaries_and_closes_only_with_evidence(
    client, db_session, monkeypatch
):
    """Cover inclusive/exclusive Beijing midnight for both success timestamps."""
    from src.models.mall_trade import MallOrder
    from tests.unit import test_mall_aftersale_service as aftersale_fixtures

    original_success = aftersale_fixtures.success

    def unique_success(payment, order, *, paid_at=None):
        return replace(
            original_success(payment, order, paid_at=paid_at),
            transaction_id=f"synthetic-recon-paid-{uuid4().hex}",
        )

    monkeypatch.setattr(aftersale_fixtures, "success", unique_success)

    included_order, included_payment = await paid_at(
        db_session,
        monkeypatch,
        openid=f"recon-flow-inside-{uuid4().hex}",
        occurred_at=datetime(2026, 11, 5, 16, 0, 0),
    )
    await paid_at(
        db_session,
        monkeypatch,
        openid=f"recon-flow-before-{uuid4().hex}",
        occurred_at=datetime(2026, 11, 5, 15, 59, 59),
    )
    await paid_at(
        db_session,
        monkeypatch,
        openid=f"recon-flow-after-{uuid4().hex}",
        occurred_at=datetime(2026, 11, 6, 16, 0, 0),
    )
    _unknown_buyer, unknown_order, _, unknown_payment = await payable(
        db_session, monkeypatch, openid=f"recon-flow-unknown-{uuid4().hex}"
    )
    unknown_payment.status = "unknown"
    unknown_payment.last_error_code = "gateway_timeout"

    before_refund = await _refund_at(
        db_session, monkeypatch, datetime(2026, 11, 5, 15, 59, 59), "before"
    )
    included_refund = await _refund_at(
        db_session, monkeypatch, datetime(2026, 11, 5, 16, 0, 0), "inside"
    )
    await _refund_at(
        db_session, monkeypatch, datetime(2026, 11, 6, 16, 0, 0), "after"
    )
    included_order_id = str(included_order.id)
    included_order_no = included_order.order_no
    included_paid_cent = included_order.payable_amount_cent
    unknown_order_id = unknown_order.id
    included_payment_status = included_payment.status
    unknown_payment_status = unknown_payment.status

    admin_id, _, headers = await admin(
        db_session,
        [
            "mall.reconciliations.read",
            "mall.reconciliations.write",
        ],
    )
    # A small normalized CSV fixture is only synthetic evidence; reconciliation
    # records the verified file digest and manually entered totals, not a parser claim.
    expected_paid = included_paid_cent + 500
    statement_bytes = (
        "渠道流水号,订单号,北京时间,记录类型,状态,金额（分）\n"
        f"SYN-PAY-001,{included_order_no},2026-11-06 00:00:00,收款,SUCCESS,{expected_paid}\n"
        f"SYN-REF-001,LT-SYN-REF,2026-11-06 00:00:00,退款,SUCCESS,{included_refund.total_cent}\n"
    ).encode("utf-8")
    statement = await _verified_statement(db_session, admin_id, statement_bytes)
    business_date = date(2026, 11, 6)

    created = await client.post(
        "/api/v1/admin/mall/reconciliations",
        headers={**headers, "Idempotency-Key": "recon-flow-create-batch-0001"},
        json={
            "businessDate": business_date.isoformat(),
            "statementFileId": str(statement.id),
            "expectedPaidCent": expected_paid,
            "expectedRefundCent": included_refund.total_cent,
            "evidenceNote": "合成的渠道账单样例，按渠道成功时刻录入",
        },
    )
    assert created.status_code == 200, created.text
    batch = created.json()["data"]
    assert batch["localPaidCent"] == included_paid_cent
    assert batch["localRefundCent"] == included_refund.total_cent
    assert batch["expectedPaidCent"] == expected_paid
    assert batch["expectedRefundCent"] == included_refund.total_cent
    assert batch["status"] == "draft"
    assert unknown_payment_status == "unknown"
    assert before_refund.confirmed_at.replace(tzinfo=None) < datetime(2026, 11, 5, 16, 0)
    assert included_payment_status == "succeeded"
    assert await db_session.get(MallOrder, unknown_order_id) is not None

    premature_close = await client.post(
        f"/api/v1/admin/mall/reconciliations/{batch['id']}/close",
        headers={**headers, "Idempotency-Key": "recon-flow-close-mismatch-01"},
        json={"expectedVersion": batch["version"], "reason": "尝试关闭未登记差异"},
    )
    assert premature_close.status_code == 409

    difference_response = await client.post(
        f"/api/v1/admin/mall/reconciliations/{batch['id']}/differences",
        headers={**headers, "Idempotency-Key": "recon-flow-add-difference-001"},
        json={
            "orderId": included_order_id,
            "externalReference": "SYN-PAY-001",
            "differenceType": "amount_mismatch",
            "expectedCent": expected_paid,
            "actualCent": included_paid_cent,
            "assignedTo": str(admin_id),
            "reason": "账单合计与本地成功收款差500分，待复核",
        },
    )
    assert difference_response.status_code == 200, difference_response.text
    difference = difference_response.json()["data"]

    open_difference_close = await client.post(
        f"/api/v1/admin/mall/reconciliations/{batch['id']}/close",
        headers={**headers, "Idempotency-Key": "recon-flow-close-open-01"},
        json={"expectedVersion": batch["version"] + 1, "reason": "仍有待处理差异"},
    )
    assert open_difference_close.status_code == 409

    no_evidence_review = await client.patch(
        f"/api/v1/admin/mall/differences/{difference['id']}",
        headers={**headers, "Idempotency-Key": "recon-flow-review-no-evidence"},
        json={
            "expectedVersion": difference["version"],
            "targetStatus": "processing",
            "assignedTo": str(admin_id),
            "reason": "先领取，再提交复核",
        },
    )
    assert no_evidence_review.status_code == 200
    processing = no_evidence_review.json()["data"]
    blocked_review = await client.patch(
        f"/api/v1/admin/mall/differences/{difference['id']}",
        headers={**headers, "Idempotency-Key": "recon-flow-review-blocked-001"},
        json={
            "expectedVersion": processing["version"],
            "targetStatus": "review",
            "reason": "没有证据不能进入复核",
        },
    )
    assert blocked_review.status_code == 409

    resolution_bytes = b"synthetic evidence: provider case SYN-PAY-001 was reconciled"
    resolution_file = await _verified_statement(db_session, admin_id, resolution_bytes)
    review_response = await client.patch(
        f"/api/v1/admin/mall/differences/{difference['id']}",
        headers={**headers, "Idempotency-Key": "recon-flow-review-with-evidence"},
        json={
            "expectedVersion": processing["version"],
            "targetStatus": "review",
            "reason": "已核对合成流水与订单时间，差异为账单录入金额",
            "evidenceFileIds": [str(resolution_file.id)],
        },
    )
    assert review_response.status_code == 200, review_response.text
    review = review_response.json()["data"]
    assert review["status"] == "review"
    assert review["evidenceFileIds"] == [str(resolution_file.id)]

    closed_difference = await client.patch(
        f"/api/v1/admin/mall/differences/{difference['id']}",
        headers={**headers, "Idempotency-Key": "recon-flow-close-difference-01"},
        json={
            "expectedVersion": review["version"],
            "targetStatus": "closed",
            "reason": "复核完成，保留证据并关闭差异",
        },
    )
    assert closed_difference.status_code == 200, closed_difference.text
    assert closed_difference.json()["data"]["status"] == "closed"

    detail = await client.get(
        f"/api/v1/admin/mall/reconciliations/{batch['id']}", headers=headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["openDifferenceCount"] == 0
    close_response = await client.post(
        f"/api/v1/admin/mall/reconciliations/{batch['id']}/close",
        headers={**headers, "Idempotency-Key": "recon-flow-close-batch-0001"},
        json={
            "expectedVersion": detail.json()["data"]["version"],
            "reason": "成功时刻边界已核对，差异有证据并完成复核",
        },
    )
    assert close_response.status_code == 200, close_response.text
    assert close_response.json()["data"]["status"] == "closed"

