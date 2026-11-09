import pytest

from src.core.config import get_settings
from src.services.mall_settings_service import get_mall_settings


@pytest.mark.asyncio
async def test_checkout_settings_are_public_minimal_and_never_expose_admin_data(
    client, db_session, monkeypatch
):
    runtime = get_settings()
    monkeypatch.setattr(runtime, "mall_enabled", True)
    monkeypatch.setattr(runtime, "mall_purchase_enabled", True)
    settings = await get_mall_settings(db_session)
    settings.enabled = True
    settings.purchase_enabled = True
    settings.freight_mode = "fixed"
    settings.freight_cent = 1200
    settings.policy_versions = {"policy": "mall-policy-2026-11"}
    settings.contact = "internal-contact-must-not-leak"
    settings.dispatch_address_snapshot = {"addressLine": "internal-dispatch-must-not-leak"}
    await db_session.commit()

    response = await client.get("/api/v1/mall/checkout/settings")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert data == {
        "purchasingAvailable": True,
        "freightMode": "fixed",
        "freightCent": 1200,
        "policyVersion": "mall-policy-2026-11",
    }
    assert "internal-contact-must-not-leak" not in response.text
    assert "internal-dispatch-must-not-leak" not in response.text

    monkeypatch.setattr(runtime, "mall_purchase_enabled", False)
    unavailable = await client.get("/api/v1/mall/checkout/settings")
    assert unavailable.status_code == 200
    assert unavailable.json()["data"]["purchasingAvailable"] is False


@pytest.mark.asyncio
async def test_buyer_address_returns_selected_region_labels_but_keeps_full_address_masked(
    client, db_session
):
    from tests.conftest import auth_header, make_access_token, seed_user
    from src.services.mall_settings_service import get_mall_settings

    user_id = await seed_user(db_session, user_type="personal", openid="region-label-buyer")
    settings = await get_mall_settings(db_session)
    settings.policy_versions = {"policy": "region-label-policy-v1"}
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=user_id, user_type="personal"))
    headers["Idempotency-Key"] = "address-region-label-0001"
    response = await client.post(
        "/api/v1/mall/addresses",
        headers=headers,
        json={
            "recipientName": "买家",
            "phone": "13800138000",
            "regionCodes": ["110000", "110100", "110101"],
            "regionNames": ["北京市", "北京市", "东城区"],
            "addressLine": "真实街道门牌不返回",
            "consentVersion": "region-label-policy-v1",
        },
    )

    assert response.status_code == 200, response.text
    address = response.json()["data"]
    assert address["regionNames"] == ["北京市", "北京市", "东城区"]
    assert "真实街道门牌不返回" not in response.text
