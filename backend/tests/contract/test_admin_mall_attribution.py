"""Evidence-based attribution is a separately authorized admin action."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.role import Role
from src.models.user import admin_account_roles
from tests.conftest import auth_header, make_access_token, seed_admin
from tests.mall_consumption_fixtures import add_mall_source, performance_context


@pytest.mark.asyncio
async def test_attribution_requires_its_live_dedicated_permission(
    client: AsyncClient, db_session: AsyncSession
):
    admin_id = await seed_admin(db_session)
    role = Role(name="仅查看消费", permissions={"permissions": ["contributions.read"]})
    db_session.add(role)
    await db_session.flush()
    await db_session.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    await db_session.commit()

    headers = auth_header(make_access_token(user_id=admin_id, user_type="admin"))
    headers["Idempotency-Key"] = "attribution-denied-probe-1"
    response = await client.post(
        "/api/v1/admin/mall/consumptions/999/attribution",
        headers=headers,
        json={"expectedVersion": 1, "distributorId": "1", "reason": "核实绑定凭证"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_authorized_attribution_is_idempotent_and_preserves_payment_period(
    client: AsyncClient, db_session: AsyncSession
):
    context = await performance_context(db_session)
    _, source = await add_mall_source(
        db_session, context, 300000, __import__("datetime").datetime(2026, 7, 15), attributed=False
    )
    admin_id = await seed_admin(db_session)
    role = Role(
        name="商城归属核实",
        permissions={"permissions": ["mall.attribution.write"]},
    )
    db_session.add(role)
    await db_session.flush()
    await db_session.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    await db_session.commit()

    headers = auth_header(make_access_token(user_id=admin_id, user_type="admin"))
    headers["Idempotency-Key"] = "attribution-contract-command-001"
    url = f"/api/v1/admin/mall/consumptions/{source.id}/attribution"
    body = {
        "expectedVersion": source.source_version,
        "distributorId": str(context["distributorId"]),
        "customerId": str(context["customerId"]),
        "reason": "支付时已生效的授权绑定记录",
    }

    first = await client.post(url, headers=headers, json=body)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["status"] == "assigned"
    assert data["businessPeriod"] == "2026-07"
    assert data["performanceHandling"] == "ready_for_settlement"
    assert "phone" not in data and "invoiceTitle" not in data

    retry = await client.post(url, headers=headers, json=body)
    assert retry.status_code == 200, retry.text
    assert retry.json()["data"]["sourceVersion"] == data["sourceVersion"] == 2

    changed_body = {**body, "reason": "改写原因"}
    mismatch = await client.post(url, headers=headers, json=changed_body)
    assert mismatch.status_code == 409
