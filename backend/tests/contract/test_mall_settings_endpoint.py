import pytest

from src.models.role import Role
from src.models.user import admin_account_roles
from tests.conftest import auth_header, make_access_token, seed_admin


@pytest.mark.asyncio
async def test_settings_update_replay_conflict_and_revocation(client, db_session):
    admin_id = await seed_admin(db_session)
    role = Role(
        name="商城设置", permissions={"permissions": ["mall.settings.read", "mall.settings.write"]}
    )
    db_session.add(role)
    await db_session.flush()
    await db_session.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=admin_id, user_type="admin"))
    url = "/api/v1/admin/mall/settings"
    response = await client.get(url, headers=headers)
    assert response.status_code == 200
    settings = response.json()["data"]
    assert not settings["purchaseEnabled"]
    body = {"expectedVersion": settings["version"], "settings": settings, "reason": "调整运费"}
    body["settings"]["freightCent"] = 500
    headers["Idempotency-Key"] = "settings-update-probe-001"
    result = await client.patch(url, headers=headers, json=body)
    assert result.status_code == 200
    assert result.json()["data"]["version"] == 2
    replay = await client.patch(url, headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["data"]["version"] == 2
    body["settings"]["freightCent"] = 600
    assert (await client.patch(url, headers=headers, json=body)).status_code == 409
    headers["Idempotency-Key"] = "settings-update-probe-002"
    assert (await client.patch(url, headers=headers, json=body)).status_code == 409
    role.permissions = {"permissions": []}
    await db_session.commit()
    assert (await client.patch(url, headers=headers, json=body)).status_code == 403
