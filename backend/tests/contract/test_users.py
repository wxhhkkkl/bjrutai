"""Contract tests for current-user profile editing."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
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
            "organization": "北京鲁泰",
            "version": version,
        },
    )
    assert update_response.status_code == 200
    update_body = update_response.json()
    assert_response_envelope(update_body)
    assert update_body["data"]["name"] == "新姓名"
    assert update_body["data"]["organization"] == "北京鲁泰"
