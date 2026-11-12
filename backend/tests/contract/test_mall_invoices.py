"""Invoice requests, real issue facts, correction chains, and buyer privacy."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.models.mall_base import utc_now
from src.models.mall_finance import MallInvoice, MallInvoiceRequest, MallPayment
from src.models.mall_operations import MallFile, MallJob
from tests.conftest import auth_header, make_access_token, seed_user
from tests.contract.test_admin_mall_orders import admin
from tests.unit.test_mall_aftersale_service import paid_order
from tests.unit.test_mall_payment_service import payable


def buyer_headers(buyer, key):
    return {
        **auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
        "Idempotency-Key": key,
    }


def invoice_body(order, **overrides):
    return {
        "orderId": str(order.id),
        "expectedOrderVersion": order.version,
        "buyerType": "personal",
        "title": "商城个人发票",
        "invoiceType": "digital_normal",
        "consentVersion": "mall-test-v1",
        "consentConfirmed": True,
        **overrides,
    }


async def create_request(client, buyer, order, *, key, body=None):
    response = await client.post(
        "/api/v1/mall/invoice-requests",
        headers=buyer_headers(buyer, key),
        json=body or invoice_body(order),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def verified_invoice_file(db, *, order_id, admin_id, label):
    file = MallFile(
        object_key=f"mall/verified/invoice-contract/{label}-{uuid4().hex}.pdf",
        purpose="invoice_pdf",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        order_id=order_id,
        mime="application/pdf",
        size=2048,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db.add(file)
    await db.flush()
    return file


@pytest.mark.asyncio
async def test_personal_request_replays_once_and_cannot_be_read_by_another_buyer(
    client, db_session, monkeypatch
):
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    body = invoice_body(order)
    first = await client.post(
        "/api/v1/mall/invoice-requests",
        headers=buyer_headers(buyer, "invoice-personal-submit-001"),
        json=body,
    )
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["buyerType"] == "personal" and data["status"] == "submitted"
    assert data["requestedGoodsCent"] == order.goods_amount_cent
    assert data["requestedFreightCent"] == order.freight_amount_cent
    assert data["netPaidCent"] == order.paid_amount_cent
    assert "taxNo" not in data

    replay = await client.post(
        "/api/v1/mall/invoice-requests",
        headers=buyer_headers(buyer, "invoice-personal-submit-001"),
        json=body,
    )
    assert replay.status_code == 200 and replay.json()["data"]["id"] == data["id"]
    duplicate = await client.post(
        "/api/v1/mall/invoice-requests",
        headers=buyer_headers(buyer, "invoice-personal-submit-002"),
        json=body,
    )
    assert duplicate.status_code == 200 and duplicate.json()["data"]["id"] == data["id"]
    assert await db_session.scalar(select(func.count()).select_from(MallInvoiceRequest)) == 1

    other_id = await seed_user(
        db_session, user_type="personal", openid="invoice-other-buyer-" + uuid4().hex
    )
    await db_session.commit()
    other = auth_header(make_access_token(user_id=other_id, user_type="personal"))
    assert (
        await client.get(f"/api/v1/mall/invoice-requests/{data['id']}", headers=other)
    ).status_code == 404
    assert "taxNo" not in (await client.get(
        f"/api/v1/mall/invoice-requests/{data['id']}",
        headers=buyer_headers(buyer, "invoice-personal-read-001"),
    )).json()["data"]


@pytest.mark.asyncio
async def test_company_requires_tax_number_and_unpaid_order_cannot_receive_invoice(
    client, db_session, monkeypatch
):
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    company_body = invoice_body(order, buyerType="company", title="测试科技有限公司")
    missing_tax = await client.post(
        "/api/v1/mall/invoice-requests",
        headers=buyer_headers(buyer, "invoice-company-missing-tax-001"),
        json=company_body,
    )
    assert missing_tax.status_code == 422

    company_body["taxNo"] = "91110000TEST202611"
    company = await client.post(
        "/api/v1/mall/invoice-requests",
        headers=buyer_headers(buyer, "invoice-company-valid-tax-001"),
        json=company_body,
    )
    assert company.status_code == 200, company.text
    assert company.json()["data"]["buyerType"] == "company"
    assert company.json()["data"]["taxNoMasked"] != company_body["taxNo"]
    assert company_body["taxNo"] not in company.text

    unpaid_buyer, unpaid_order, _, _ = await payable(
        db_session, monkeypatch, openid="payment-test-openid-unpaid-" + uuid4().hex
    )
    unpaid = await client.post(
        "/api/v1/mall/invoice-requests",
        headers=buyer_headers(unpaid_buyer, "invoice-unpaid-order-001"),
        json=invoice_body(unpaid_order),
    )
    assert unpaid.status_code in {409, 422}


@pytest.mark.asyncio
async def test_admin_claim_and_needs_info_allow_only_versioned_buyer_correction_and_withdrawal(
    client, db_session, monkeypatch
):
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    request = await create_request(
        client, buyer, order, key="invoice-info-request-create-001"
    )
    _, _, reader = await admin(db_session, ["mall.invoices.read"])
    reader["Idempotency-Key"] = "invoice-readonly-claim-denied-001"
    denied = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/claim",
        headers=reader,
        json={"expectedVersion": request["version"]},
    )
    assert denied.status_code == 403

    admin_id, _, writer = await admin(db_session, ["mall.invoices.read", "mall.invoices.write"])
    writer["Idempotency-Key"] = "invoice-claim-intent-0001"
    claimed = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/claim",
        headers=writer,
        json={"expectedVersion": request["version"]},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["data"]["claimedBy"] == str(admin_id)
    writer["Idempotency-Key"] = "invoice-needs-info-intent-01"
    needs_info = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/needs-info",
        headers=writer,
        json={
            "expectedVersion": claimed.json()["data"]["version"],
            "reason": "请确认发票抬头",
        },
    )
    assert needs_info.status_code == 200 and needs_info.json()["data"]["status"] == "needs_info"
    assert needs_info.json()["data"]["infoRequestReason"] == "请确认发票抬头"
    buyer_view = await client.get(
        f"/api/v1/mall/invoice-requests/{request['id']}",
        headers=buyer_headers(buyer, "invoice-buyer-read-needs-info-01"),
    )
    assert buyer_view.status_code == 200, buyer_view.text
    assert buyer_view.json()["data"]["infoRequestReason"] == "请确认发票抬头"

    writer["Idempotency-Key"] = "invoice-buyer-correction-001"
    corrected = await client.patch(
        f"/api/v1/mall/invoice-requests/{request['id']}",
        headers=buyer_headers(buyer, "invoice-buyer-correction-001"),
        json={
            "expectedVersion": needs_info.json()["data"]["version"],
            "title": "更正后的个人抬头",
            "email": "buyer@example.test",
            "consentVersion": "mall-test-v1",
            "consentConfirmed": True,
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["data"]["title"] == "更正后的个人抬头"
    assert corrected.json()["data"]["infoRequestReason"] is None
    writer["Idempotency-Key"] = "invoice-withdraw-before-issue-001"
    withdrawn = await client.post(
        f"/api/v1/mall/invoice-requests/{request['id']}/withdraw",
        headers=buyer_headers(buyer, "invoice-withdraw-before-issue-001"),
        json={"expectedVersion": corrected.json()["data"]["version"], "reason": "暂不需要"},
    )
    assert withdrawn.status_code == 200 and withdrawn.json()["data"]["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_admin_invoice_reads_are_masked_and_raw_billing_release_stays_closed(
    client, db_session, monkeypatch
):
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    tax_no = "91110000PRIVATE2026"
    request = await create_request(
        client,
        buyer,
        order,
        key="invoice-privacy-request-create-001",
        body=invoice_body(
            order,
            buyerType="company",
            title="隐私测试有限公司",
            taxNo=tax_no,
            email="billing-private@example.test",
            invoiceType="manual_special_request",
        ),
    )
    assert request["invoiceType"] == "manual_special_request"
    _, _, reader = await admin(db_session, ["mall.invoices.read"])
    listed = await client.get("/api/v1/admin/mall/invoice-requests", headers=reader)
    assert listed.status_code == 200, listed.text
    item = next(item for item in listed.json()["data"]["items"] if item["id"] == request["id"])
    assert item["invoiceType"] == "manual_special_request"
    assert item["taxNoMasked"] != tax_no
    assert tax_no not in listed.text and "billing-private@example.test" not in listed.text
    filtered = await client.get(
        "/api/v1/admin/mall/invoice-requests?status=needs_info", headers=reader
    )
    assert filtered.status_code == 200, filtered.text
    assert all(
        item["status"] == "needs_info" for item in filtered.json()["data"]["items"]
    )
    detail = await client.get(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}", headers=reader
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["invoiceType"] == "manual_special_request"
    assert tax_no not in detail.text and "billing-private@example.test" not in detail.text

    _, _, billing = await admin(db_session, ["mall.billing.release"])
    billing["Idempotency-Key"] = "invoice-raw-release-denied-001"
    denied = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/billing-release",
        headers=billing,
        json={
            "expectedVersion": request["version"],
            "purpose": "invoice_issue",
            "reason": "开票需要核验抬头和税号",
        },
    )
    assert denied.status_code == 403
    assert tax_no not in denied.text and "billing-private@example.test" not in denied.text
    assert "未获授权" in denied.text


@pytest.mark.asyncio
async def test_blue_invoice_requires_current_amount_and_verified_file_and_replays_same_fact(
    client, db_session, monkeypatch
):
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    paid_amount_cent = order.paid_amount_cent
    request = await create_request(
        client, buyer, order, key="invoice-blue-request-create-001"
    )
    admin_id, _, writer = await admin(db_session, ["mall.invoices.read", "mall.invoices.write"])
    writer["Idempotency-Key"] = "invoice-blue-claim-intent-01"
    claimed = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/claim",
        headers=writer,
        json={"expectedVersion": request["version"]},
    )
    assert claimed.status_code == 200, claimed.text
    file = await verified_invoice_file(
        db_session, order_id=order.id, admin_id=admin_id, label="blue"
    )
    await db_session.commit()
    body = {
        "expectedVersion": claimed.json()["data"]["version"],
        "invoiceNo": "INV-BLUE-001",
        "issuedAt": "2026-11-07T09:00:00Z",
        "sellerIdentity": "北京鲁泰测试销售主体",
        "totalCent": paid_amount_cent - 1,
        "fileId": str(file.id),
    }
    writer["Idempotency-Key"] = "invoice-blue-wrong-amount-01"
    mismatch = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/record",
        headers=writer,
        json=body,
    )
    assert mismatch.status_code in {409, 422}
    assert await db_session.scalar(select(func.count()).select_from(MallInvoice)) == 0

    body["totalCent"] = paid_amount_cent
    writer["Idempotency-Key"] = "invoice-blue-record-intent-01"
    first = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/record",
        headers=writer,
        json=body,
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["kind"] == "blue"
    assert first.json()["data"]["totalCent"] == paid_amount_cent
    admin_detail = await client.get(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}", headers=writer
    )
    assert admin_detail.status_code == 200, admin_detail.text
    assert admin_detail.json()["data"]["invoices"][0]["invoiceNo"] == "INV-BLUE-001"
    assert admin_detail.json()["data"]["invoices"][0]["status"] == "valid"
    replay = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/record",
        headers=writer,
        json=body,
    )
    assert replay.status_code == 200 and replay.json()["data"]["id"] == first.json()["data"]["id"]
    assert await db_session.scalar(select(func.count()).select_from(MallInvoice)) == 1


@pytest.mark.asyncio
async def test_partial_red_then_full_red_replacement_preserves_the_invoice_chain(
    client, db_session, monkeypatch
):
    from src.schemas.mall_aftersale import AftersaleDecision
    from src.schemas.mall_catalog import VersionAction
    from src.services.mall_aftersale_service import apply_aftersale, decide_aftersale
    from src.services.mall_refund_service import apply_verified_refund, execute_refund
    from tests.unit.test_mall_aftersale_service import admin_actor
    from tests.unit.test_mall_aftersale_service import request as aftersale_request
    from tests.unit.test_mall_refund_service import refund_fact

    buyer, order, _, items = await paid_order(db_session, monkeypatch)
    invoice_request = await create_request(
        client, buyer, order, key="invoice-red-request-create-001"
    )
    admin_id, _, writer = await admin(
        db_session,
        [
            "mall.invoices.read",
            "mall.invoices.write",
            "mall.aftersales.review",
            "mall.refunds.execute",
        ],
    )
    finance = await admin_actor(
        db_session,
        [
            "mall.invoices.read",
            "mall.invoices.write",
            "mall.aftersales.review",
            "mall.refunds.execute",
        ],
    )
    writer["Idempotency-Key"] = "invoice-red-blue-claim-001"
    claimed = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{invoice_request['id']}/claim",
        headers=writer,
        json={"expectedVersion": invoice_request["version"]},
    )
    assert claimed.status_code == 200, claimed.text
    original_file = await verified_invoice_file(
        db_session, order_id=order.id, admin_id=admin_id, label="chain-blue"
    )
    await db_session.commit()
    writer["Idempotency-Key"] = "invoice-red-blue-record-01"
    blue = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{invoice_request['id']}/record",
        headers=writer,
        json={
            "expectedVersion": claimed.json()["data"]["version"],
            "invoiceNo": "INV-CHAIN-BLUE-001",
            "issuedAt": "2026-11-07T09:00:00Z",
            "sellerIdentity": "北京鲁泰测试销售主体",
            "totalCent": order.paid_amount_cent,
            "fileId": str(original_file.id),
        },
    )
    assert blue.status_code == 200, blue.text
    blue_id = blue.json()["data"]["id"]
    _, _, other_writer = await admin(db_session, ["mall.invoices.read", "mall.invoices.write"])
    other_writer["Idempotency-Key"] = "invoice-red-unclaimed-admin-001"
    denied_red = await client.post(
        f"/api/v1/admin/mall/invoices/{blue_id}/red-pending",
        headers=other_writer,
        json={
            "expectedVersion": blue.json()["data"]["version"],
            "targetStatus": "red_pending",
            "reason": "未领取该开票申请的管理员不得操作",
        },
    )
    assert denied_red.status_code == 409
    await db_session.refresh(order)
    for item in items:
        await db_session.refresh(item)

    aftersale = await apply_aftersale(
        db_session, buyer, aftersale_request(order, items[1]), key="invoice-partial-refund-apply-01"
    )
    aftersale = await decide_aftersale(
        db_session,
        finance,
        aftersale.id,
        AftersaleDecision(
            expectedVersion=aftersale.version, decision="approve", reason="部分退款核验"
        ),
        key="invoice-partial-refund-review-01",
    )
    payment = await db_session.get(MallPayment, order.active_payment_id)
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="invoice-partial-refund-execute-01",
    )
    await apply_verified_refund(db_session, refund.id, refund_fact(refund, payment))
    await db_session.commit()

    blue_record = await db_session.get(MallInvoice, int(blue_id), populate_existing=True)
    assert blue_record is not None
    await db_session.refresh(blue_record)
    assert blue_record.status == "red_pending"
    writer["Idempotency-Key"] = "invoice-partial-red-pending-01"
    pending = await client.post(
        f"/api/v1/admin/mall/invoices/{blue_id}/red-pending",
        headers=writer,
        json={
            "expectedVersion": blue_record.version,
            "targetStatus": "red_pending",
            "reason": "部分退款成功，办理部分红冲",
        },
    )
    assert pending.status_code == 200, pending.text
    red_file = await verified_invoice_file(
        db_session, order_id=order.id, admin_id=admin_id, label="chain-red"
    )
    await db_session.commit()
    writer["Idempotency-Key"] = "invoice-partial-red-record-01"
    red = await client.post(
        f"/api/v1/admin/mall/invoices/{blue_id}/red-record",
        headers=writer,
        json={
            "expectedVersion": pending.json()["data"]["version"],
            "invoiceNo": "INV-CHAIN-RED-001",
            "issuedAt": "2026-11-07T10:00:00Z",
            "totalCent": 5000,
            "fileId": str(red_file.id),
            "reason": "对应5000分成功退款",
        },
    )
    assert red.status_code == 200, red.text
    assert red.json()["data"]["kind"] == "red"
    assert red.json()["data"]["originalInvoiceId"] == blue_id
    latest_request = await client.get(
        f"/api/v1/admin/mall/invoice-requests/{invoice_request['id']}", headers=writer
    )
    assert latest_request.status_code == 200, latest_request.text

    old_blue = await db_session.get(MallInvoice, int(blue_id), populate_existing=True)
    assert old_blue is not None
    await db_session.refresh(old_blue)
    writer["Idempotency-Key"] = "invoice-remainder-red-pending-01"
    remainder_pending = await client.post(
        f"/api/v1/admin/mall/invoices/{blue_id}/red-pending",
        headers=writer,
        json={
            "expectedVersion": old_blue.version,
            "targetStatus": "awaiting_counterparty",
            "reason": "替代蓝票前冲销旧票剩余覆盖",
        },
    )
    assert remainder_pending.status_code == 200, remainder_pending.text
    remainder_file = await verified_invoice_file(
        db_session, order_id=order.id, admin_id=admin_id, label="chain-red-remainder"
    )
    await db_session.commit()
    writer["Idempotency-Key"] = "invoice-remainder-red-record-01"
    remainder_red = await client.post(
        f"/api/v1/admin/mall/invoices/{blue_id}/red-record",
        headers=writer,
        json={
            "expectedVersion": remainder_pending.json()["data"]["version"],
            "invoiceNo": "INV-CHAIN-RED-REMAINDER",
            "issuedAt": "2026-11-07T10:30:00Z",
            "totalCent": order.paid_amount_cent - 5000,
            "fileId": str(remainder_file.id),
            "reason": "冲销旧蓝票剩余有效覆盖",
        },
    )
    assert remainder_red.status_code == 200, remainder_red.text
    await db_session.refresh(old_blue)
    assert old_blue.status == "fully_red"

    replacement_file = await verified_invoice_file(
        db_session, order_id=order.id, admin_id=admin_id, label="chain-replacement"
    )
    await db_session.commit()
    writer["Idempotency-Key"] = "invoice-partial-replacement-01"
    replacement = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{invoice_request['id']}/record",
        headers=writer,
        json={
            "expectedVersion": latest_request.json()["data"]["version"],
            "invoiceNo": "INV-CHAIN-BLUE-002",
            "issuedAt": "2026-11-07T11:00:00Z",
            "sellerIdentity": "北京鲁泰测试销售主体",
            "totalCent": order.paid_amount_cent - 5000,
            "fileId": str(replacement_file.id),
            "replacementForId": blue_id,
            "reason": "按未退款的有效金额重新开具",
        },
    )
    assert replacement.status_code == 200, replacement.text
    replacement_id = replacement.json()["data"]["id"]
    assert replacement.json()["data"]["replacementForId"] == blue_id

    writer["Idempotency-Key"] = "invoice-full-red-pending-01"
    full_pending = await client.post(
        f"/api/v1/admin/mall/invoices/{replacement_id}/red-pending",
        headers=writer,
        json={
            "expectedVersion": replacement.json()["data"]["version"],
            "targetStatus": "awaiting_counterparty",
            "reason": "更正抬头需全额红冲重开",
        },
    )
    assert full_pending.status_code == 200, full_pending.text
    full_red_file = await verified_invoice_file(
        db_session, order_id=order.id, admin_id=admin_id, label="chain-full-red"
    )
    await db_session.commit()
    writer["Idempotency-Key"] = "invoice-full-red-record-01"
    full_red = await client.post(
        f"/api/v1/admin/mall/invoices/{replacement_id}/red-record",
        headers=writer,
        json={
            "expectedVersion": full_pending.json()["data"]["version"],
            "invoiceNo": "INV-CHAIN-RED-002",
            "issuedAt": "2026-11-07T12:00:00Z",
            "totalCent": order.paid_amount_cent - 5000,
            "fileId": str(full_red_file.id),
            "reason": "全额红冲后重开",
        },
    )
    assert full_red.status_code == 200, full_red.text
    assert full_red.json()["data"]["originalInvoiceId"] == replacement_id
    assert full_red.json()["data"]["kind"] == "red"
    assert await db_session.scalar(select(func.count()).select_from(MallInvoice)) == 5
    assert order.refunded_goods_cent == 5000


@pytest.mark.asyncio
async def test_replacing_a_lost_file_keeps_same_invoice_fact_and_does_not_reissue(
    client, db_session, monkeypatch
):
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    request = await create_request(
        client, buyer, order, key="invoice-file-replace-request-001"
    )
    admin_id, _, writer = await admin(db_session, ["mall.invoices.read", "mall.invoices.write"])
    writer["Idempotency-Key"] = "invoice-file-replace-claim-001"
    claimed = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/claim",
        headers=writer,
        json={"expectedVersion": request["version"]},
    )
    assert claimed.status_code == 200, claimed.text
    first_file = await verified_invoice_file(
        db_session, order_id=order.id, admin_id=admin_id, label="replace-first"
    )
    await db_session.commit()
    writer["Idempotency-Key"] = "invoice-file-replace-record-01"
    issued = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/record",
        headers=writer,
        json={
            "expectedVersion": claimed.json()["data"]["version"],
            "invoiceNo": "INV-FILE-REPLACE-001",
            "issuedAt": "2026-11-07T09:00:00Z",
            "sellerIdentity": "北京鲁泰测试销售主体",
            "totalCent": order.paid_amount_cent,
            "fileId": str(first_file.id),
        },
    )
    assert issued.status_code == 200, issued.text
    invoice_id = issued.json()["data"]["id"]
    order_invoices = await client.get(
        f"/api/v1/mall/orders/{order.id}/invoices",
        headers=buyer_headers(buyer, "invoice-order-list-001"),
    )
    assert order_invoices.status_code == 200, order_invoices.text
    assert order_invoices.json()["data"]["items"][0]["id"] == invoice_id
    assert order_invoices.headers["cache-control"] == "no-store"

    correction_headers = buyer_headers(buyer, "invoice-correction-intent-001")
    correction_body = {
        "expectedVersion": issued.json()["data"]["version"],
        "reason": "已开票后发现抬头填写错误，请核实更正",
    }
    correction = await client.post(
        f"/api/v1/mall/invoices/{invoice_id}/correction",
        headers=correction_headers,
        json=correction_body,
    )
    assert correction.status_code == 202, correction.text
    assert correction.json()["data"]["status"] == "manual"
    replayed_correction = await client.post(
        f"/api/v1/mall/invoices/{invoice_id}/correction",
        headers=correction_headers,
        json=correction_body,
    )
    assert replayed_correction.status_code == 202
    assert replayed_correction.json()["data"]["commandId"] == correction.json()["data"]["commandId"]
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(MallJob)
            .where(MallJob.kind == "mall_invoice_correction_review")
        )
        == 1
    )
    second_file = await verified_invoice_file(
        db_session, order_id=order.id, admin_id=admin_id, label="replace-second"
    )
    await db_session.commit()
    writer["Idempotency-Key"] = "invoice-file-replace-content-01"
    replaced = await client.patch(
        f"/api/v1/admin/mall/invoices/{invoice_id}/file",
        headers=writer,
        json={
            "expectedVersion": issued.json()["data"]["version"],
            "fileId": str(second_file.id),
            "reason": "原PDF下载损坏，补交同一张真实发票文件",
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["data"]["id"] == invoice_id
    assert replaced.json()["data"]["invoiceNo"] == "INV-FILE-REPLACE-001"
    assert replaced.json()["data"]["fileId"] == str(second_file.id)
    assert await db_session.scalar(select(func.count()).select_from(MallInvoice)) == 1

