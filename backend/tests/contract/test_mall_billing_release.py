"""Single-request invoice data access remains purpose, consent, and role scoped."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.core.config import get_settings
from src.models.audit import AuditLog
from src.models.consent import ConsentRecord
from src.models.mall_finance import MallInvoiceRequest
from tests.contract.test_admin_mall_orders import admin
from tests.contract.test_mall_invoices import create_request, invoice_body
from tests.unit.test_mall_aftersale_service import paid_order


@pytest.mark.asyncio
async def test_claimed_company_invoice_release_is_minimal_no_store_and_rechecks_consent(
    client, db_session, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "mall_data_release_enabled", True, raising=False)
    monkeypatch.setattr(
        settings, "mall_data_release_retention_policy_ref", "TEST-RETENTION", raising=False
    )
    monkeypatch.setattr(
        settings,
        "mall_data_release_notice_approved_version",
        "mall-purpose-2026-11-v1",
        raising=False,
    )
    buyer, order, _, _ = await paid_order(db_session, monkeypatch)
    title = "合成测试有限公司"
    tax_no = "91110000SYNTHETIC01"
    email = "billing-only-for-delivery@example.test"
    request = await create_request(
        client,
        buyer,
        order,
        key="billing-release-request-create-001",
        body=invoice_body(
            order,
            buyerType="company",
            title=title,
            taxNo=tax_no,
            email=email,
        ),
    )
    _, _, headers = await admin(
        db_session, ["mall.invoices.read", "mall.invoices.write", "mall.billing.release"]
    )
    headers["Idempotency-Key"] = "billing-release-claim-invoice-001"
    claim = await client.post(
        f"/api/v1/admin/mall/invoice-requests/{request['id']}/claim",
        headers=headers,
        json={"expectedVersion": request["version"]},
    )
    assert claim.status_code == 200, claim.text
    request_version = claim.json()["data"]["version"]
    release_url = f"/api/v1/admin/mall/invoice-requests/{request['id']}/billing-release"
    release_body = {
        "expectedVersion": request_version,
        "purpose": "invoice_issue",
        "reason": "办理指定开票申请",
    }
    headers["Idempotency-Key"] = "billing-release-view-invoice-001"

    released = await client.post(release_url, headers=headers, json=release_body)
    assert released.status_code == 200, released.text
    assert released.headers["cache-control"] == "no-store, private, max-age=0"
    assert released.headers["pragma"] == "no-cache"
    assert released.headers["expires"] == "0"
    data = released.json()["data"]
    assert data["requestId"] == request["id"]
    assert data["buyerType"] == "company"
    assert data["title"] == title
    assert data["taxNo"] == tax_no
    assert email not in released.text
    expires_at = datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    assert now < expires_at <= now + timedelta(seconds=60)
    assert data["auditId"].isdigit()
    event = await db_session.get(AuditLog, int(data["auditId"]))
    assert event.action == "mall_admin_billing_data_released"
    assert event.user_id is None
    assert event.detail["adminAccountId"]
    assert title not in str(event.detail) and tax_no not in str(event.detail)
    assert email not in str(event.detail)

    request_row = await db_session.get(MallInvoiceRequest, int(request["id"]))
    consent = await db_session.get(ConsentRecord, request_row.consent_record_id)
    consent.status = "withdrawn"
    await db_session.commit()
    denied = await client.post(release_url, headers=headers, json=release_body)
    assert denied.status_code == 403, denied.text
    assert denied.headers["cache-control"] == "no-store, private, max-age=0"
    assert denied.headers["pragma"] == "no-cache"
    assert denied.headers["expires"] == "0"
    assert title not in denied.text and tax_no not in denied.text and email not in denied.text

    denied_event = await db_session.scalar(
        select(AuditLog)
        .where(AuditLog.action == "mall_admin_billing_data_release_denied")
        .order_by(AuditLog.id.desc())
    )
    assert denied_event is not None
    assert title not in str(denied_event.detail) and tax_no not in str(denied_event.detail)
    assert email not in str(denied_event.detail)
