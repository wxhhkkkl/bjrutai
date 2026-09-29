"""Contract tests for personal intra-org commission overrides."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token, seed_user


def _headers(*permissions: str) -> dict:
    token = make_access_token(
        user_id=1, user_type="admin", permissions=list(permissions)
    )
    return {"Authorization": f"Bearer {token}"}


R_RW = _headers("sharing_rules.read", "sharing_rules.write")
R_R = _headers("sharing_rules.read")
NO_PERM = _headers("org.read")


def _data(response):
    body = response.json()
    assert body["code"] == 0
    return body["data"]


async def _seed_distributor(db: AsyncSession, org_id: int) -> int:
    user_id = await seed_user(
        db,
        openid="personal_performance_user",
        user_type="distributor",
        name="专属提成员",
        phone="13900000001",
    )
    from src.models.distributor import Distributor

    distributor = Distributor(user_id=user_id, org_id=org_id)
    db.add(distributor)
    await db.flush()
    await db.refresh(distributor)
    return distributor.id


@pytest.mark.asyncio
async def test_personal_rule_overrides_and_can_restore_org_inheritance(
    client: AsyncClient, db_session: AsyncSession
):
    org = await organization_service.create_org(
        db_session, OrgCreate(name="总部", orgType="headquarters")
    )
    distributor_id = await _seed_distributor(db_session, org.id)
    organization_tiers = [{"minCent": 0, "maxCent": None, "ratio": 0.05}]
    personal_tiers = [
        {"minCent": 0, "maxCent": 500000, "ratio": 0.08},
        {"minCent": 500000, "maxCent": None, "ratio": 0.12},
    ]

    await client.put(
        f"/api/v1/admin/orgs/{org.id}/performance-rules/intra_org",
        json={"tiers": organization_tiers},
        headers=R_RW,
    )
    detail_url = f"/api/v1/admin/distributors/{distributor_id}/personal-performance-rule"
    original = _data(await client.get(detail_url, headers=R_R))
    assert original["personalRule"] is None
    assert original["organizationRule"]["tiers"] == organization_tiers

    saved = _data(
        await client.put(
            detail_url,
            json={"tiers": personal_tiers},
            headers=R_RW,
        )
    )
    assert saved["tiers"] == personal_tiers

    org_rules = _data(
        await client.get(
            f"/api/v1/admin/orgs/{org.id}/personal-performance-rules",
            headers=R_R,
        )
    )
    assert org_rules["items"][0]["distributorId"] == str(distributor_id)
    assert org_rules["items"][0]["tiers"] == personal_tiers

    cleared = _data(await client.delete(detail_url, headers=R_RW))
    assert cleared["inherited"] is True
    restored = _data(await client.get(detail_url, headers=R_R))
    assert restored["personalRule"] is None
    assert restored["organizationRule"]["tiers"] == organization_tiers


@pytest.mark.asyncio
async def test_personal_rule_endpoints_check_permissions(
    client: AsyncClient, db_session: AsyncSession
):
    org = await organization_service.create_org(
        db_session, OrgCreate(name="权限测试组织", orgType="headquarters")
    )
    distributor_id = await _seed_distributor(db_session, org.id)
    detail_url = f"/api/v1/admin/distributors/{distributor_id}/personal-performance-rule"

    read_denied = await client.get(detail_url, headers=NO_PERM)
    write_denied = await client.put(
        detail_url,
        json={"tiers": [{"minCent": 0, "maxCent": None, "ratio": 0.05}]},
        headers=R_R,
    )
    assert read_denied.json()["code"] == 40300
    assert write_denied.json()["code"] == 40300
