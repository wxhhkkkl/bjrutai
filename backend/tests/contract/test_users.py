"""Contract tests for current-user profile editing."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.distributor import Distributor
from src.models.organization import Organization
from src.models.user import User
from tests.conftest import assert_response_envelope, seed_user


def _auth_headers(user_id: int) -> dict:
    token = create_access_token(data={"sub": str(user_id), "user_type": "promoter"})
    return {"Authorization": f"Bearer {token}"}


async def test_profile_update_accepts_version_returned_by_get_profile(
    client: AsyncClient, db_session: AsyncSession
):
    user_id = await seed_user(db_session, openid="wx_profile_contract", name="旧姓名")
    headers = _auth_headers(user_id)

    get_response = await client.get("/api/v1/me/profile", headers=headers)
    assert get_response.status_code == 200
    get_body = get_response.json()
    assert_response_envelope(get_body)
    version = get_body["data"]["version"]
    assert isinstance(version, str)

    update_response = await client.put(
        "/api/v1/me/profile",
        headers=headers,
        json={
            "name": "新姓名",
            "version": version,
        },
    )
    assert update_response.status_code == 200
    update_body = update_response.json()
    assert_response_envelope(update_body)
    assert update_body["data"]["name"] == "新姓名"


async def test_profile_update_rejects_manual_organization_change(
    client: AsyncClient, db_session: AsyncSession
):
    user_id = await seed_user(db_session, openid="wx_profile_org_locked", name="测试用户")
    headers = _auth_headers(user_id)
    version = (await client.get("/api/v1/me/profile", headers=headers)).json()["data"]["version"]

    response = await client.put(
        "/api/v1/me/profile",
        headers=headers,
        json={"organization": "其他机构", "version": version},
    )

    assert response.status_code == 400
    assert "所属机构由系统维护" in response.json()["message"]


async def test_profile_uses_the_distributor_assigned_organization(
    client: AsyncClient, db_session: AsyncSession
):
    user_id = await seed_user(db_session, openid="wx_profile_assigned_org", name="测试用户")
    user = await db_session.get(User, user_id)
    user.organization = "旧机构名称"
    org = Organization(name="后台分配机构", org_type="branch", level=1, sort_order=0)
    db_session.add(org)
    await db_session.flush()
    db_session.add(Distributor(user_id=user_id, org_id=org.id))
    await db_session.commit()

    response = await client.get("/api/v1/me/profile", headers=_auth_headers(user_id))

    assert response.status_code == 200
    assert response.json()["data"]["organization"] == "后台分配机构"
