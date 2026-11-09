"""Recipient release is default-off and requires current consent and runtime gates."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from src.core.config import get_settings
from src.models.audit import AuditLog
from src.models.consent import ConsentRecord
from tests.contract.test_admin_mall_orders import admin
from tests.contract.test_mall_fulfillment import paid_order


@pytest.mark.asyncio
async def test_valid_paid_order_recipient_release_stays_closed_by_default(
    client, db_session, monkeypatch
):
    _, order, _ = await paid_order(db_session, monkeypatch)
    raw_phone = order.address_snapshot["phone"]
    raw_recipient = order.address_snapshot["recipientName"]
    _, _, headers = await admin(db_session, ["mall.fulfillment.release"])
    headers["Idempotency-Key"] = "raw-recipient-release-g-data-001"

    result = await client.post(
        f"/api/v1/admin/mall/orders/{order.id}/fulfillment-release",
        headers=headers,
        json={
            "expectedVersion": order.version,
            "purpose": "shipping_label",
            "reason": "运行配置未就绪时确认原文拒绝",
        },
    )

    assert result.status_code == 403, result.text
    assert "原文资料交付当前未获授权" in result.text
    assert result.headers["cache-control"] == "no-store, private, max-age=0"
    assert result.headers["pragma"] == "no-cache"
    assert result.headers["expires"] == "0"
    assert raw_phone not in result.text
    assert raw_recipient not in result.text
    assert "address" not in result.text and "recipientName" not in result.text
    event = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "mall_admin_fulfillment_data_release_denied")
    )
    assert event is not None
    assert raw_phone not in str(event.detail) and raw_recipient not in str(event.detail)


@pytest.mark.asyncio
async def test_enabled_fulfillment_release_is_one_order_no_store_and_rechecks_consent(
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
    _, order, _ = await paid_order(db_session, monkeypatch)
    raw_phone = order.address_snapshot["phone"]
    raw_recipient = order.address_snapshot["recipientName"]
    raw_address = order.address_snapshot["addressLine"]
    _, _, headers = await admin(db_session, ["mall.fulfillment.release"])
    headers["Idempotency-Key"] = "raw-recipient-release-enabled-001"
    url = f"/api/v1/admin/mall/orders/{order.id}/fulfillment-release"
    body = {
        "expectedVersion": order.version,
        "purpose": "shipping_label",
        "reason": "办理指定订单面单",
    }

    released = await client.post(url, headers=headers, json=body)
    assert released.status_code == 200, released.text
    assert released.headers["cache-control"] == "no-store, private, max-age=0"
    assert released.headers["pragma"] == "no-cache"
    assert released.headers["expires"] == "0"
    data = released.json()["data"]
    assert data["orderId"] == str(order.id)
    assert data["recipientName"] == raw_recipient
    assert data["phone"] == raw_phone
    assert data["addressLine"] == raw_address
    expires_at = datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    assert now < expires_at <= now + timedelta(seconds=60)
    assert data["auditId"].isdigit()
    assert "Idempotency-Key" not in released.text
    await db_session.refresh(order)
    assert order.version == body["expectedVersion"]

    event = await db_session.get(AuditLog, int(data["auditId"]))
    assert event.action == "mall_admin_fulfillment_data_released"
    assert event.user_id is None
    assert event.detail["adminAccountId"]
    assert raw_phone not in str(event.detail)
    assert raw_recipient not in str(event.detail)
    assert raw_address not in str(event.detail)

    consent = await db_session.get(ConsentRecord, order.consent_record_id)
    consent.status = "withdrawn"
    await db_session.commit()
    denied = await client.post(url, headers=headers, json=body)
    assert denied.status_code == 403, denied.text
    assert denied.headers["cache-control"] == "no-store, private, max-age=0"
    assert denied.headers["pragma"] == "no-cache"
    assert denied.headers["expires"] == "0"
    assert raw_phone not in denied.text and raw_address not in denied.text
