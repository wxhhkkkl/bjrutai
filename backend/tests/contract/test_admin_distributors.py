"""Contract tests for admin distributor endpoints + distributor login (US3/US4)."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import ActivationStatus, User, UserType
from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token


def _headers(*perms: str) -> dict:
    token = make_access_token(user_id=1, user_type="admin", permissions=list(perms))
    return {"Authorization": f"Bearer {token}"}


DIST_RW = _headers("distributor.read", "distributor.write", "org_admin.write")
NO_ADMIN_PERM = _headers("distributor.read", "distributor.write")


async def _seed_org(db: AsyncSession) -> int:
    org = await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))
    return org.id


@pytest.mark.asyncio
async def test_create_list_update_role_flow(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)

    created = await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors",
        json={"name": "张三", "phone": "13800000001", "initialPassword": "password123"},
        headers=DIST_RW,
    )
    assert created.status_code == 200
    did = created.json()["data"]["distributorId"]

    listing = await client.get(
        f"/api/v1/admin/orgs/{org_id}/distributors", headers=DIST_RW
    )
    assert listing.json()["data"]["total"] == 1

    role = await client.put(
        f"/api/v1/admin/distributors/{did}/role",
        json={"orgRole": "admin"},
        headers=DIST_RW,
    )
    assert role.status_code == 200
    assert role.json()["data"]["orgRole"] == "admin"


@pytest.mark.asyncio
async def test_attach_existing_personal_account_to_org(
    client: AsyncClient, db_session: AsyncSession
):
    org_id = await _seed_org(db_session)
    user = User(
        name="个人用户",
        phone="13800000009",
        phone_masked="138****0009",
        user_type=UserType.PERSONAL,
        activation_status=ActivationStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()

    unassigned = await client.get(
        "/api/v1/admin/users/unassigned?keyword=个人用户", headers=DIST_RW
    )
    item = unassigned.json()["data"]["items"][0]
    assert item["phone"] == "138****0009"
    assert "phoneValue" not in item

    attached = await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors/attach",
        json={"userId": user.id, "orgRole": "admin"},
        headers=DIST_RW,
    )
    assert attached.status_code == 200
    assert attached.json()["data"]["orgRole"] == "admin"

    repeated = await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors/attach",
        json={"userId": user.id, "orgRole": "member"},
        headers=DIST_RW,
    )
    assert repeated.status_code == 409


@pytest.mark.asyncio
async def test_unassigned_search_and_attach_reject_non_personal_accounts(
    client: AsyncClient, db_session: AsyncSession
):
    org_id = await _seed_org(db_session)
    legacy_business_user = User(
        name="历史业务账号",
        phone="13800000019",
        phone_masked="138****0019",
        user_type=UserType.DISTRIBUTOR,
        activation_status=ActivationStatus.ACTIVE,
    )
    db_session.add(legacy_business_user)
    await db_session.flush()

    unassigned = await client.get(
        "/api/v1/admin/users/unassigned?keyword=历史业务账号", headers=DIST_RW
    )
    assert unassigned.json()["data"]["items"] == []

    attached = await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors/attach",
        json={"userId": legacy_business_user.id, "orgRole": "member"},
        headers=DIST_RW,
    )
    assert attached.status_code == 409
    assert "个人账号" in attached.json()["message"]


@pytest.mark.asyncio
async def test_attach_as_org_admin_requires_org_admin_permission(
    client: AsyncClient, db_session: AsyncSession
):
    org_id = await _seed_org(db_session)
    user = User(
        name="个人用户",
        phone="13800000029",
        phone_masked="138****0029",
        user_type=UserType.PERSONAL,
    )
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors/attach",
        json={"userId": user.id, "orgRole": "admin"},
        headers=NO_ADMIN_PERM,
    )
    assert response.status_code == 403
    assert "org_admin.write" in response.json()["message"]


@pytest.mark.asyncio
async def test_role_without_org_admin_permission_forbidden(
    client: AsyncClient, db_session: AsyncSession
):
    org_id = await _seed_org(db_session)
    created = await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors",
        json={"name": "张三", "phone": "13800000001", "initialPassword": "password123"},
        headers=DIST_RW,
    )
    did = created.json()["data"]["distributorId"]

    resp = await client.put(
        f"/api/v1/admin/distributors/{did}/role",
        json={"orgRole": "admin"},
        headers=NO_ADMIN_PERM,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_distributor_login_and_bind_wechat(
    client: AsyncClient, db_session: AsyncSession, mock_wechat_client
):
    org_id = await _seed_org(db_session)
    await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors",
        json={"name": "张三", "phone": "13800000001", "initialPassword": "password123"},
        headers=DIST_RW,
    )

    login = await client.post(
        "/api/v1/auth/distributor-login",
        json={"phone": "13800000001", "password": "password123"},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["code"] == 0
    assert body["data"]["requiresWechatBinding"] is True

    mock_wechat_client.set_valid_code("wx_code_1", openid="o_dist_001")
    with patch("src.services.auth_service.get_wechat_client", return_value=mock_wechat_client):
        bind = await client.post(
            "/api/v1/auth/bind-wechat",
            json={"code": "wx_code_1"},
            headers={"Authorization": f"Bearer {body['data']['accessToken']}"},
        )
    assert bind.status_code == 200
    assert bind.json()["data"]["bound"] is True


@pytest.mark.asyncio
async def test_set_role_second_admin_rejected(client: AsyncClient, db_session: AsyncSession):
    """FR-008: an org can have only one admin; setting a second is rejected."""
    org_id = await _seed_org(db_session)

    a = (await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors",
        json={"name": "甲", "phone": "13800000011", "initialPassword": "password123"},
        headers=DIST_RW,
    )).json()["data"]["distributorId"]
    b = (await client.post(
        f"/api/v1/admin/orgs/{org_id}/distributors",
        json={"name": "乙", "phone": "13800000022", "initialPassword": "password123"},
        headers=DIST_RW,
    )).json()["data"]["distributorId"]

    # Promote A to admin -> success
    resp = await client.put(
        f"/api/v1/admin/distributors/{a}/role",
        json={"orgRole": "admin"}, headers=DIST_RW,
    )
    assert resp.json()["code"] == 0

    # Promote B to admin -> rejected (org already has an admin)
    resp2 = await client.put(
        f"/api/v1/admin/distributors/{b}/role",
        json={"orgRole": "admin"}, headers=DIST_RW,
    )
    assert resp2.json()["code"] == 40000
    assert "已有管理员" in resp2.json()["message"]

    # Revoke A, then promote B -> success
    await client.put(f"/api/v1/admin/distributors/{a}/role", json={"orgRole": "member"}, headers=DIST_RW)
    resp3 = await client.put(
        f"/api/v1/admin/distributors/{b}/role",
        json={"orgRole": "admin"}, headers=DIST_RW,
    )
    assert resp3.json()["code"] == 0
