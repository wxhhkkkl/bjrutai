"""Isolated buyer-to-finance invoice flow using synthetic invoice facts only."""

from datetime import timedelta
from uuid import uuid4

import pytest

from src.api.v1.mall_files import get_mall_store
from src.main import app
from src.models.mall_base import utc_now
from src.models.mall_operations import MallFile
from tests.conftest import auth_header, make_access_token, seed_user
from tests.contract.test_admin_mall_orders import admin
from tests.unit.test_mall_aftersale_service import paid_order


class SyntheticInvoiceStore:
    """In-memory metadata and private links; no COS request is made."""

    def __init__(self):
        self.objects = {}
        self.signed_expiries = []

    async def head(self, object_key):
        return self.objects.get(object_key)

    async def sign_get(self, object_key, *, expires_seconds):
        assert object_key in self.objects
        self.signed_expiries.append(expires_seconds)
        return "https://storage.invalid/synthetic-invoice?signature=temporary"


@pytest.mark.asyncio
async def test_synthetic_buyer_finance_invoice_and_private_file_flow(
    client, db_session, monkeypatch
):
    """Exercise application, finance recording, buyer history, and file access."""
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    buyer_headers = {
        **auth_header(make_access_token(user_id=buyer.actor_id, user_type="personal")),
        "Idempotency-Key": "synthetic-invoice-create-0001",
    }
    tax_no = "91110000SYNTHETIC01"
    email = "synthetic-billing@example.test"
    created = await client.post(
        "/api/v1/mall/invoice-requests",
        headers=buyer_headers,
        json={
            "orderId": str(order.id),
            "expectedOrderVersion": order.version,
            "buyerType": "company",
            "title": "集成测试主体",
            "invoiceType": "digital_normal",
            "taxNo": tax_no,
            "email": email,
            "consentVersion": "mall-test-v1",
            "consentConfirmed": True,
        },
    )
    assert created.status_code == 200, created.text
    request = created.json()["data"]
    assert request["status"] == "submitted"
    assert request["netPaidCent"] == order.paid_amount_cent
    assert request["taxNoMasked"] != tax_no
    assert tax_no not in created.text and email not in created.text

    admin_id, _, finance_headers = await admin(
        db_session, ["mall.invoices.read", "mall.invoices.write"]
    )
    claimed = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/claim",
        headers={**finance_headers, "Idempotency-Key": "synthetic-invoice-claim-001"},
        json={"expectedVersion": request["version"]},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["data"]["claimedBy"] == str(admin_id)
    assert tax_no not in claimed.text and email not in claimed.text

    file = MallFile(
        object_key=f"mall/invoice_pdf/synthetic/{uuid4().hex}.pdf",
        purpose="invoice_pdf",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        order_id=order.id,
        mime="application/pdf",
        size=2048,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db_session.add(file)
    await db_session.flush()
    store = SyntheticInvoiceStore()
    store.objects[file.object_key] = {
        "mime": file.mime,
        "size": file.size,
        "sha256": file.sha256,
    }
    monkeypatch.setitem(app.dependency_overrides, get_mall_store, lambda: store)

    issued_at = "2026-11-07T09:00:00Z"
    recorded = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/record",
        headers={**finance_headers, "Idempotency-Key": "synthetic-invoice-record-001"},
        json={
            "expectedVersion": claimed.json()["data"]["version"],
            "invoiceNo": "TEST-ONLY-NOT-A-TAX-INVOICE-001",
            "issuedAt": issued_at,
            "sellerIdentity": "集成测试销售主体",
            "totalCent": order.paid_amount_cent,
            "fileId": str(file.id),
            "reason": "仅验证本地票据记录链路，不代表真实税务出票",
        },
    )
    assert recorded.status_code == 200, recorded.text
    invoice = recorded.json()["data"]
    assert invoice["kind"] == "blue"
    assert invoice["status"] == "valid"
    assert invoice["totalCent"] == order.paid_amount_cent
    assert invoice["invoiceNo"].startswith("TEST-ONLY-")

    buyer_headers["Idempotency-Key"] = "synthetic-invoice-buyer-read-01"
    detail = await client.get(
        f"/api/v1/mall/invoice-requests/{request['id']}", headers=buyer_headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["status"] == "delivered"
    assert detail.json()["data"]["invoices"][0]["id"] == invoice["id"]
    assert tax_no not in detail.text and email not in detail.text

    history = await client.get(
        f"/api/v1/mall/orders/{order.id}/invoices",
        headers={**buyer_headers, "Idempotency-Key": "synthetic-invoice-history-01"},
    )
    assert history.status_code == 200, history.text
    assert history.json()["data"]["items"][0]["id"] == invoice["id"]

    access = await client.get(
        f"/api/v1/mall/files/{file.id}/access",
        headers={**buyer_headers, "Idempotency-Key": "synthetic-invoice-file-01"},
    )
    assert access.status_code == 200, access.text
    assert access.headers["cache-control"] == "no-store"
    assert access.json()["data"]["accessUrl"].startswith("https://storage.invalid/")
    assert "signature=temporary" in access.json()["data"]["accessUrl"]
    assert store.signed_expiries == [60]
    assert tax_no not in access.text and email not in access.text

    stranger_id = await seed_user(
        db_session,
        openid="synthetic-invoice-stranger-" + uuid4().hex,
        user_type="personal",
    )
    stranger_headers = auth_header(make_access_token(user_id=stranger_id, user_type="personal"))
    stranger = await client.get(f"/api/v1/mall/files/{file.id}/access", headers=stranger_headers)
    assert stranger.status_code == 403
