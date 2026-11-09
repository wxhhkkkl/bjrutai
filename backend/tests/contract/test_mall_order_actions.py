import pytest

from src.schemas.mall_checkout import AddressWrite
from src.services.mall_address_service import save_address
from tests.conftest import auth_header, make_access_token, seed_user
from tests.mall_checkout_fixtures import ADDRESS
from tests.unit.test_mall_order_actions import unattempted
from tests.unit.test_mall_payment_service import payable


@pytest.mark.asyncio
async def test_cancel_contract_reports_pending_and_command_query_does_not_claim_closed(
    client, db_session, monkeypatch
):
    actor, order, skus, _ = await payable(db_session, monkeypatch)
    headers = auth_header(make_access_token(user_id=actor.actor_id, user_type="personal"))
    headers["Idempotency-Key"] = "http-order-cancel-intent-001"
    url = f"/api/v1/mall/orders/{order.id}/cancel"
    body = {"expectedVersion": order.version, "reason": "不再需要"}
    response = await client.post(url, headers=headers, json=body)
    assert response.status_code == 202, response.text
    result = response.json()["data"]
    assert result["status"] == "pending" and result["entityId"] == str(order.id)
    assert response.headers["cache-control"] == "no-store"
    progress = await client.get(f'/api/v1/mall/commands/{result["commandId"]}', headers=headers)
    assert progress.json()["data"]["status"] == "pending"
    assert (await client.post(url, headers=headers, json=body)).json()["data"][
        "commandId"
    ] == result["commandId"]
    assert (
        await client.post(url, headers=headers, json={**body, "reason": "不同内容"})
    ).status_code == 409
    await db_session.refresh(order)
    await db_session.refresh(skus[0])
    assert order.status == "pending_payment" and skus[0].reserved_qty == 1
    alien_id = await seed_user(db_session, user_type="personal", openid="cancel-alien-test")
    await db_session.commit()
    alien = {
        **auth_header(make_access_token(user_id=alien_id, user_type="personal")),
        "Idempotency-Key": "alien-cancel-intent-001",
    }
    assert (await client.post(url, headers=alien, json=body)).status_code == 404


@pytest.mark.asyncio
async def test_change_order_address_contract_masks_output_and_exposes_safe_actions(
    client, db_session, monkeypatch
):
    actor, _, _, _, order = await unattempted(db_session, monkeypatch)
    address = await save_address(
        db_session, actor, AddressWrite(**{**ADDRESS, "phone": "13900004567"})
    )
    await db_session.commit()
    headers = {
        **auth_header(make_access_token(user_id=actor.actor_id, user_type="personal")),
        "Idempotency-Key": "http-change-order-address-001",
    }
    url = f"/api/v1/mall/orders/{order.id}/address"
    body = {
        "expectedVersion": order.version,
        "addressId": str(address.id),
        "reason": "电话13900004567",
    }
    result = await client.patch(url, headers=headers, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["address"]["phoneMasked"] == "139****4567"
    assert "13900004567" not in result.text and ADDRESS["addressLine"] not in result.text
    detail = (await client.get(f"/api/v1/mall/orders/{order.id}", headers=headers)).json()["data"]
    assert {"cancelMallOrder", "changeMallOrderAddress"} <= set(detail["availableActions"])
    assert detail["timeline"][-1]["action"] == "address_changed"
    assert "13900004567" not in str(detail)
    assert (
        await client.patch(url, headers=headers, json={**body, "freightCent": 1})
    ).status_code == 422


@pytest.mark.asyncio
async def test_immediate_cancel_finishes_with_closed_timeline_and_safe_reason(
    client, db_session, monkeypatch
):
    actor, _, _, _, order = await unattempted(db_session, monkeypatch)
    headers = {
        **auth_header(make_access_token(user_id=actor.actor_id, user_type="personal")),
        "Idempotency-Key": "http-immediate-cancel-001",
    }
    response = await client.post(
        f"/api/v1/mall/orders/{order.id}/cancel",
        headers=headers,
        json={"expectedVersion": order.version, "reason": "电话13800001234"},
    )
    assert response.status_code == 202 and response.json()["data"]["status"] == "completed"
    result = await client.get(f"/api/v1/mall/orders/{order.id}", headers=headers)
    detail = result.json()["data"]
    assert detail["status"] == "closed" and detail["availableActions"] == []
    assert detail["timeline"][-1]["action"] == "closed"
    assert "13800001234" not in result.text
