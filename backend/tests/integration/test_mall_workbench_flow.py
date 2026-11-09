"""Role-scoped workbench counts leave the queue after real local actions.

All channel, tax and storage facts in this file are synthetic. Nothing contacts
WeChat Pay, a tax platform, COS or a logistics provider.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.mall_deps import MallActor
from src.main import app
from src.models.mall_base import utc_now
from src.models.mall_operations import MallFile, MallSettings
from src.models.mall_trade import MallAftersaleItem
from src.schemas.mall_aftersale import AftersaleDecision, ReturnReceipt, ReturnShipment
from src.schemas.mall_catalog import VersionAction
from src.services.mall_aftersale_service import (
    apply_aftersale,
    decide_aftersale,
    receive_return,
    submit_return_shipment,
)
from src.services.mall_funds_state import mark_funds_unknown
from src.services.mall_payment_service import apply_verified_payment
from src.services.mall_refund_service import apply_verified_refund, execute_refund
from src.services.mall_settings_service import get_mall_settings
from tests.conftest import auth_header, make_access_token
from tests.contract.test_admin_mall_orders import admin
from tests.mall_consumption_fixtures import (
    add_frozen_evidence,
    add_mall_source,
    performance_context,
)
from tests.unit.test_mall_aftersale_service import paid_order as af_paid_order
from tests.unit.test_mall_aftersale_service import request
from tests.unit.test_mall_payment_service import payable, success
from tests.unit.test_mall_refund_service import refund_fact, refund_ready

_WORKBENCH_PERMISSIONS = [
    "mall.orders.read",
    "mall.orders.write",
    "mall.shipments.write",
    "mall.aftersales.read",
    "mall.aftersales.review",
    "mall.returns.receive",
    "mall.payments.read",
    "mall.payments.query",
    "mall.refunds.read",
    "mall.refunds.query",
    "mall.refunds.execute",
    "mall.reconciliations.read",
    "mall.attribution.write",
    "performance.settle",
    "sharing_rules.read",
    "mall.invoices.read",
    "mall.invoices.write",
    "mall.stock.read",
    "mall.stock.write",
    "mall.products.read",
    "mall.products.write",
    "contributions.read",
]


async def _workbench(client, headers):
    response = await client.get("/api/v1/admin/mall/workbench", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_shipment_aftersale_and_return_counts_exit_without_losing_history(
    client, db_session, monkeypatch
):
    buyer, order, _skus, items = await af_paid_order(db_session, monkeypatch)
    admin_id, _, admin_headers = await admin(db_session, _WORKBENCH_PERMISSIONS)
    operator = MallActor("admin", admin_id, frozenset(_WORKBENCH_PERMISSIONS))
    before = await _workbench(client, admin_headers)
    assert before["pendingShipment"] == 1

    shipped = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/ship",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-ship-0001"},
        json={
            "expectedVersion": order.version,
            "courierCode": "sf",
            "trackingNo": "T126SHIP0001",
        },
    )
    assert shipped.status_code == 200, shipped.text
    assert (await _workbench(client, admin_headers))["pendingShipment"] == 0
    admin_order = await client.get(f"/api/v1/admin/mall/orders/{order.id}", headers=admin_headers)
    assert admin_order.status_code == 200
    assert admin_order.json()["data"]["shipment"]["trackingNo"] == "T126SHIP0001"

    settings = await db_session.get(MallSettings, 1)
    settings.return_address_snapshot = {
        "recipientName": "集成测试收件人",
        "phone": "138****0000",
        "addressLine": "虚构退货地址",
    }
    await db_session.commit()
    await db_session.refresh(order)
    buyer_headers = auth_header(
        make_access_token(user_id=buyer.actor_id, user_type="personal")
    )
    aftersale = await apply_aftersale(
        db_session,
        buyer,
        request(order, items[1], method="return_refund"),
        key="t126-workbench-return-apply-001",
    )
    await db_session.commit()
    assert (await _workbench(client, admin_headers))["pendingAftersale"] == 1

    aftersale = await decide_aftersale(
        db_session,
        operator,
        aftersale.id,
        AftersaleDecision(
            expectedVersion=aftersale.version,
            decision="approve",
            reason="合成退货验收用例通过",
        ),
        key="t126-workbench-return-approve-01",
    )
    await db_session.commit()
    summary = await _workbench(client, admin_headers)
    assert summary["pendingAftersale"] == summary["pendingReturnReceipt"] == 0

    aftersale = await submit_return_shipment(
        db_session,
        buyer,
        aftersale.id,
        ReturnShipment(
            expectedVersion=aftersale.version,
            courierCode="sf",
            trackingNo="T126RETURN0001",
        ),
        key="t126-workbench-return-label-01",
    )
    await db_session.commit()
    assert (await _workbench(client, admin_headers))["pendingReturnReceipt"] == 1

    line = await db_session.scalar(
        select(MallAftersaleItem).where(MallAftersaleItem.aftersale_id == aftersale.id)
    )
    received = await receive_return(
        db_session,
        operator,
        aftersale.id,
        ReturnReceipt(
            expectedVersion=aftersale.version,
            result="accepted",
            sellableItems=[{"aftersaleItemId": str(line.id), "quantity": line.quantity}],
            reason="合成商品验收完成",
        ),
        key="t126-workbench-return-receive-01",
    )
    await db_session.commit()
    assert (await _workbench(client, admin_headers))["pendingReturnReceipt"] == 0
    history = await client.get(
        f"/api/v1/admin/mall/aftersales/{received.id}", headers=admin_headers
    )
    assert history.status_code == 200
    assert history.json()["data"]["status"] == "awaiting_refund"
    assert history.json()["data"]["returnTrackingNo"] == "T126RETURN0001"
    assert history.json()["data"]["receiptResult"] == "accepted"
    # No WeChat subscription authorization is configured or required to read
    # the buyer's original order and aftersale history.
    buyer_order = await client.get(f"/api/v1/mall/orders/{order.id}", headers=buyer_headers)
    assert buyer_order.status_code == 200
    assert buyer_order.json()["data"]["id"] == str(order.id)


@pytest.mark.asyncio
async def test_unknown_payment_and_refund_leave_workbench_after_verified_facts(
    client, db_session, monkeypatch
):
    _buyer, order, _skus, payment = await payable(db_session, monkeypatch)
    _admin_id, _, admin_headers = await admin(db_session, _WORKBENCH_PERMISSIONS)
    now = utc_now()
    mark_funds_unknown(payment, now=now - timedelta(minutes=11))
    payment.last_query_at = now
    payment.last_error_code = "gateway_timeout"
    await db_session.commit()
    assert (await _workbench(client, admin_headers))["paymentUnknown"] == 1

    fact = replace(success(payment, order), transaction_id="t126-unique-payment-fact")
    await apply_verified_payment(db_session, payment.id, fact)
    await db_session.commit()
    summary = await _workbench(client, admin_headers)
    assert summary["paymentUnknown"] == 0
    buyer_read = await client.get(
        f"/api/v1/mall/orders/{order.id}",
        headers=auth_header(make_access_token(user_id=order.buyer_user_id, user_type="personal")),
    )
    assert buyer_read.status_code == 200
    assert buyer_read.json()["data"]["status"] == "pending_shipment"
    payment_history = await client.get(
        f"/api/v1/admin/mall/payments/{payment.id}", headers=admin_headers
    )
    assert payment_history.status_code == 200
    assert payment_history.json()["data"]["status"] == "succeeded"

    # The shared refund fixture assigns the same synthetic openid. Release it
    # after proving the payment so its separate buyer can be created safely.
    from src.models.user import User

    first_buyer = await db_session.get(User, order.buyer_user_id)
    first_buyer.openid = f"t126-released-{uuid4().hex}"
    await db_session.commit()

    finance, refund_order, aftersale, _skus, _items, refund_payment = await refund_ready(
        db_session, monkeypatch
    )
    refund = await execute_refund(
        db_session,
        finance,
        aftersale.id,
        VersionAction(expectedVersion=aftersale.version),
        key="t126-workbench-refund-execute-001",
    )
    mark_funds_unknown(refund, now=now - timedelta(minutes=11))
    refund.last_query_at = now
    refund.last_error_code = "gateway_timeout"
    await db_session.commit()
    assert (await _workbench(client, admin_headers))["refundAbnormal"] == 1

    await apply_verified_refund(db_session, refund.id, refund_fact(refund, refund_payment))
    await db_session.commit()
    assert (await _workbench(client, admin_headers))["refundAbnormal"] == 0
    refund_history = await client.get(
        f"/api/v1/admin/mall/refunds/{refund.id}", headers=admin_headers
    )
    assert refund_history.status_code == 200
    assert refund_history.json()["data"]["status"] == "succeeded"
    buyer_order = await client.get(
        f"/api/v1/mall/orders/{refund_order.id}",
        headers=auth_header(
            make_access_token(user_id=refund_order.buyer_user_id, user_type="personal")
        ),
    )
    assert buyer_order.status_code == 200
    assert buyer_order.json()["data"]["id"] == str(refund_order.id)


@pytest.mark.asyncio
async def test_attribution_adjustment_stock_and_invoice_counts_exit_with_history(
    client, db_session, monkeypatch
):
    admin_id, _, admin_headers = await admin(db_session, _WORKBENCH_PERMISSIONS)
    settings = await get_mall_settings(db_session)
    settings.policy_versions = {"policy": "t126-policy-v1"}
    await db_session.commit()

    context = await performance_context(db_session)
    _source_order, source = await add_mall_source(
        db_session, context, 300000, datetime(2026, 7, 15), attributed=False
    )
    evidence = await add_frozen_evidence(
        db_session,
        context,
        period="2026-07",
        rule_snapshot={"tiers": [{"minCent": 0, "maxCent": None, "ratio": 0.08}], "version": 4},
        original_base_cent=0,
        original_commission_cent=0,
        result_presence="not_generated",
        result_absence_reason="below_first_tier",
    )
    await db_session.commit()
    assert (await _workbench(client, admin_headers))["unassigned"] == 1

    attributed = await client.post(
        f"/api/v1/admin/mall/consumptions/{source.id}/attribution",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-attribution-01"},
        json={
            "expectedVersion": source.source_version,
            "distributorId": str(context["distributorId"]),
            "customerId": str(context["customerId"]),
            "evidenceFileIds": [],
            "reason": "合成历史绑定依据核验",
        },
    )
    assert attributed.status_code == 200, attributed.text
    assert attributed.json()["data"]["performanceHandling"] == "adjustment_pending"
    summary = await _workbench(client, admin_headers)
    assert summary["unassigned"] == 0
    assert summary["pendingAdjustment"] == 1
    adjustment_page = await client.get(
        "/api/v1/admin/performance/adjustments", headers=admin_headers
    )
    assert adjustment_page.status_code == 200
    adjustment = adjustment_page.json()["data"]["items"][0]
    reviewed = await client.post(
        f"/api/v1/admin/performance/adjustments/{adjustment['id']}/review",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-adjust-review-01"},
        json={"expectedVersion": adjustment["version"]},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert (await _workbench(client, admin_headers))["pendingAdjustment"] == 0
    adjustment_history = await client.get(
        f"/api/v1/admin/performance/adjustments/{adjustment['id']}",
        headers=admin_headers,
    )
    assert adjustment_history.json()["data"]["status"] == "reviewed"
    assert adjustment_history.json()["data"]["originEvidenceId"] == str(evidence.id)

    category = await client.post(
        "/api/v1/admin/mall/categories",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-category-01"},
        json={"name": f"T126类别{uuid4().hex[:6]}", "status": "enabled"},
    )
    assert category.status_code == 200, category.text
    image = MallFile(
        object_key=f"mall/product_image/t126/{uuid4().hex}.jpg",
        purpose="product_image",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        mime="image/jpeg",
        size=32,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db_session.add(image)
    await db_session.commit()
    created_product = await client.post(
        "/api/v1/admin/mall/products",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-product-01"},
        json={
            "name": "T126库存验收商品",
            "categoryId": category.json()["data"]["id"],
            "coverFileId": str(image.id),
            "description": "仅用于商城工作台合成验收",
            "skus": [
                {
                    "skuCode": f"T126-{uuid4().hex[:12]}",
                    "priceCent": 1999,
                    "initialStock": 1,
                    "warningQuantity": 2,
                }
            ],
        },
    )
    assert created_product.status_code == 200, created_product.text
    product = created_product.json()["data"]
    published = await client.post(
        f"/api/v1/admin/mall/products/{product['id']}/status",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-product-publish-01"},
        json={"expectedVersion": product["version"], "targetStatus": "on_sale"},
    )
    assert published.status_code == 200, published.text
    sku = published.json()["data"]["skus"][0]
    assert (await _workbench(client, admin_headers))["lowStock"] == 1
    replenished = await client.post(
        f"/api/v1/admin/mall/skus/{sku['id']}/stock-adjustments",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-restock-01"},
        json={
            "expectedVersion": sku["version"],
            "deltaAvailableQuantity": 2,
            "reason": "合成补货验收",
        },
    )
    assert replenished.status_code == 200, replenished.text
    assert (await _workbench(client, admin_headers))["lowStock"] == 0
    stock_history = await client.get(
        f"/api/v1/admin/mall/skus/{sku['id']}/stock-movements", headers=admin_headers
    )
    assert stock_history.json()["data"]["items"]

    buyer, invoice_order, _skus, _items = await af_paid_order(db_session, monkeypatch)
    invoice_order_id = invoice_order.id
    settings = await get_mall_settings(db_session)
    settings.policy_versions = {"policy": "t126-policy-v1"}
    await db_session.commit()
    checkout_settings = await client.get("/api/v1/mall/checkout/settings")
    assert checkout_settings.status_code == 200, checkout_settings.text
    policy_version = checkout_settings.json()["data"]["policyVersion"]
    assert policy_version == "t126-policy-v1"
    invoice_create = await client.post(
        "/api/v1/mall/invoice-requests",
        headers={
            **auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
            "Idempotency-Key": "t126-workbench-invoice-create-01",
        },
        json={
            "orderId": str(invoice_order.id),
            "expectedOrderVersion": invoice_order.version,
            "buyerType": "company",
            "title": "T126合成测试主体",
            "invoiceType": "digital_normal",
            "taxNo": "91110000T126TEST01",
            "email": "t126@example.test",
            "consentVersion": policy_version,
            "consentConfirmed": True,
        },
    )
    assert invoice_create.status_code == 200, invoice_create.text
    request_id = int(invoice_create.json()["data"]["id"])
    assert (await _workbench(client, admin_headers))["pendingInvoice"] == 1
    claim = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request_id}/claim",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-invoice-claim-01"},
        json={"expectedVersion": invoice_create.json()["data"]["version"]},
    )
    assert claim.status_code == 200, claim.text

    def invoice_file(key):
        return MallFile(
            object_key=f"mall/invoice_pdf/t126/{key}-{uuid4().hex}.pdf",
            purpose="invoice_pdf",
            owner_actor_type="admin",
            owner_actor_id=admin_id,
            order_id=invoice_order_id,
            mime="application/pdf",
            size=2048,
            sha256="b" * 64,
            status="verified",
            expires_at=utc_now() - timedelta(seconds=1),
        )

    blue_file = invoice_file("blue")
    db_session.add(blue_file)
    await db_session.commit()
    issue = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request_id}/record",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-invoice-record-01"},
        json={
            "expectedVersion": claim.json()["data"]["version"],
            "invoiceNo": "T126-SYNTHETIC-BLUE-001",
            "issuedAt": "2026-11-08T01:00:00Z",
            "sellerIdentity": "T126合成销售主体",
            "totalCent": invoice_order.paid_amount_cent,
            "fileId": str(blue_file.id),
            "reason": "仅记录合成税务事实，不代表真实出票",
        },
    )
    assert issue.status_code == 200, issue.text
    blue = issue.json()["data"]
    assert (await _workbench(client, admin_headers))["pendingInvoice"] == 0

    red_pending = await client.post(
        f"/api/v1/admin/mall/invoices/{blue['id']}/red-pending",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-red-pending-01"},
        json={
            "expectedVersion": blue["version"],
            "targetStatus": "red_pending",
            "reason": "合成红冲流程验收",
        },
    )
    assert red_pending.status_code == 200, red_pending.text
    assert (await _workbench(client, admin_headers))["pendingRedInvoice"] == 1
    red_file = invoice_file("red")
    db_session.add(red_file)
    await db_session.commit()
    red_issue = await client.post(
        f"/api/v1/admin/mall/invoices/{blue['id']}/red-record",
        headers={**admin_headers, "Idempotency-Key": "t126-workbench-red-record-01"},
        json={
            "expectedVersion": red_pending.json()["data"]["version"],
            "invoiceNo": "T126-SYNTHETIC-RED-001",
            "issuedAt": "2026-11-08T01:10:00Z",
            "totalCent": invoice_order.paid_amount_cent,
            "fileId": str(red_file.id),
            "reason": "仅记录合成红字事实，不代表真实税务红冲",
        },
    )
    assert red_issue.status_code == 200, red_issue.text
    assert (await _workbench(client, admin_headers))["pendingRedInvoice"] == 0
    history = await client.get(
        f"/api/v1/mall/orders/{invoice_order.id}/invoices",
        headers=auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
    )
    assert history.status_code == 200
    assert len(history.json()["data"]["items"]) == 2
    assert {row["kind"] for row in history.json()["data"]["items"]} == {"blue", "red"}


@pytest.mark.asyncio
async def test_workbench_read_failure_remains_an_error_response(client, db_session, monkeypatch):
    from src.services import mall_workbench_service

    async def fail_read(*_args, **_kwargs):
        raise RuntimeError("synthetic workbench failure")

    monkeypatch.setattr(mall_workbench_service, "get_mall_workbench", fail_read)
    _admin_id, _, headers = await admin(db_session, ["mall.invoices.read"])
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as safe_client:
        response = await safe_client.get("/api/v1/admin/mall/workbench", headers=headers)

    assert response.status_code >= 500
    assert response.json().get("code") not in (None, 0)
