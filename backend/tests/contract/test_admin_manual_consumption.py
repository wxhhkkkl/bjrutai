"""API contract tests for admin manual consumption entry."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from src.models.audit import AuditLog
from src.models.bill import Bill
from src.models.role import Role
from src.services.seed_service import seed_system_admin_role
from tests.conftest import (
    make_access_token,
    seed_admin,
    seed_bound_customer_with_attribution,
)


def _headers(admin_id: int, *permissions: str, key: str | None = None) -> dict:
    token = make_access_token(user_id=admin_id, user_type="admin", permissions=list(permissions))
    result = {"Authorization": f"Bearer {token}"}
    if key:
        result["Idempotency-Key"] = key
    return result


def _payload(customer, **updates):
    body = {
        "customerId": str(customer.id),
        "customerVersion": customer.version,
        "consumedAt": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "amountCent": 12880,
        "note": "线下收款补录",
    }
    body.update(updates)
    return body


@pytest.mark.asyncio
async def test_search_and_create_manual_consumption_contract(client: AsyncClient, db_session):
    admin_id = await seed_admin(db_session)
    seeded = await seed_bound_customer_with_attribution(db_session)
    headers = _headers(admin_id, "contributions.write")

    search = await client.get(
        "/api/v1/admin/contributions/customers",
        params={"keyword": "138001"},
        headers=headers,
    )
    assert search.status_code == 200
    search_body = search.json()
    assert set(search_body) == {"code", "message", "data", "requestId", "serverTime"}
    item = search_body["data"]["items"][0]
    assert item["phoneMasked"] == "138****8000"
    assert item["personName"] == "测试拓展人"

    response = await client.post(
        "/api/v1/admin/contributions/manual",
        json=_payload(seeded["customer"]),
        headers=_headers(admin_id, "contributions.write", key="api-create-001"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "消费录入成功"
    assert body["data"]["amountCent"] == 12880
    assert body["data"]["source"] == "manual"
    assert body["data"]["replayed"] is False


@pytest.mark.asyncio
async def test_create_requires_write_permission_and_idempotency_key(client: AsyncClient, db_session):
    admin_id = await seed_admin(db_session)
    seeded = await seed_bound_customer_with_attribution(db_session)

    forbidden = await client.post(
        "/api/v1/admin/contributions/manual",
        json=_payload(seeded["customer"]),
        headers=_headers(admin_id, "contributions.read", key="read-only"),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == 40300

    forbidden_search = await client.get(
        "/api/v1/admin/contributions/customers",
        params={"keyword": "测试"},
        headers=_headers(admin_id, "contributions.read"),
    )
    assert forbidden_search.status_code == 403
    assert forbidden_search.json()["code"] == 40300

    missing_key = await client.post(
        "/api/v1/admin/contributions/manual",
        json=_payload(seeded["customer"]),
        headers=_headers(admin_id, "contributions.write"),
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["message"] == "缺少或无效的 Idempotency-Key"


@pytest.mark.asyncio
async def test_create_validates_future_time_with_chinese_message(client: AsyncClient, db_session):
    admin_id = await seed_admin(db_session)
    seeded = await seed_bound_customer_with_attribution(db_session)
    response = await client.post(
        "/api/v1/admin/contributions/manual",
        json=_payload(
            seeded["customer"],
            consumedAt=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        ),
        headers=_headers(admin_id, "contributions.write", key="future-api"),
    )
    assert response.status_code == 422
    assert response.json()["code"] == 42200
    assert response.json()["message"] == "消费时间不能晚于当前时间"


@pytest.mark.asyncio
async def test_identical_replay_returns_same_bill_without_second_audit(client: AsyncClient, db_session):
    admin_id = await seed_admin(db_session)
    seeded = await seed_bound_customer_with_attribution(db_session)
    request_body = _payload(seeded["customer"])
    headers = _headers(admin_id, "contributions.write", key="api-replay")

    first = (await client.post("/api/v1/admin/contributions/manual", json=request_body, headers=headers)).json()
    second = (await client.post("/api/v1/admin/contributions/manual", json=request_body, headers=headers)).json()

    assert first["data"]["id"] == second["data"]["id"]
    assert second["data"]["replayed"] is True
    assert (await db_session.execute(select(func.count(Bill.id)))).scalar_one() == 1
    assert (
        await db_session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.action == "manual_consumption_create")
        )
    ).scalar_one() == 1


@pytest.mark.asyncio
async def test_system_admin_seed_contains_manual_entry_permission(db_session):
    await seed_admin(db_session)
    await seed_system_admin_role(db_session)
    system_role = (
        await db_session.execute(select(Role).where(Role.is_system.is_(True)))
    ).scalar_one()
    permissions = system_role.permissions["permissions"]
    assert "contributions.read" in permissions
    assert "contributions.write" in permissions
