"""Contract tests for admin organization endpoints (US1).

Verifies the unified response envelope and documented behaviors from
contracts/org.md. Uses the real SQLite test DB via the client fixture.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token


def _admin_headers(*perms: str) -> dict:
    token = make_access_token(user_id=1, user_type="admin", permissions=list(perms))
    return {"Authorization": f"Bearer {token}"}


ORG_RW = _admin_headers("org.read", "org.write")
ORG_R = _admin_headers("org.read")
NO_PERM = _admin_headers("unrelated.read")


def _assert_envelope(resp):
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "success"
    assert "requestId" in body
    assert "serverTime" in body
    return body["data"]


async def _seed_root(db: AsyncSession) -> int:
    org = await organization_service.create_org(
        db, OrgCreate(name="总部", orgType="headquarters")
    )
    return org.id


@pytest.mark.asyncio
async def test_create_org_returns_envelope(client: AsyncClient):
    resp = await client.post("/api/v1/admin/orgs", json={"name": "总部", "orgType": "headquarters"}, headers=ORG_RW)
    assert resp.status_code == 200
    data = _assert_envelope(resp)
    assert data["orgId"]
    assert data["level"] == 1


@pytest.mark.asyncio
async def test_create_child_and_get_tree(client: AsyncClient, db_session: AsyncSession):
    root_id = await _seed_root(db_session)
    resp = await client.post(
        "/api/v1/admin/orgs",
        json={"name": "华北区", "orgType": "region", "parentId": root_id},
        headers=ORG_RW,
    )
    assert resp.status_code == 200
    assert _assert_envelope(resp)["level"] == 2

    tree = (await client.get("/api/v1/admin/orgs", headers=ORG_R)).json()["data"]
    assert tree["totalNodes"] == 2


@pytest.mark.asyncio
async def test_migrate_subtree(client: AsyncClient, db_session: AsyncSession):
    root_id = await _seed_root(db_session)
    a = await organization_service.create_org(db_session, OrgCreate(name="A区", orgType="region", parentId=root_id))
    b = await organization_service.create_org(db_session, OrgCreate(name="B区", orgType="region", parentId=root_id))

    resp = await client.post(
        f"/api/v1/admin/orgs/{a.id}/migrate",
        json={"newParentId": b.id},
        headers=ORG_RW,
    )
    assert resp.status_code == 200
    data = _assert_envelope(resp)
    assert data["parentId"] == str(b.id)


@pytest.mark.asyncio
async def test_migrate_cycle_rejected(client: AsyncClient, db_session: AsyncSession):
    root_id = await _seed_root(db_session)
    a = await organization_service.create_org(db_session, OrgCreate(name="A区", orgType="region", parentId=root_id))
    a1 = await organization_service.create_org(db_session, OrgCreate(name="A1", orgType="city", parentId=a.id))

    resp = await client.post(
        f"/api/v1/admin/orgs/{a.id}/migrate",
        json={"newParentId": a1.id},
        headers=ORG_RW,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == 40000


@pytest.mark.asyncio
async def test_delete_non_empty_rejected(client: AsyncClient, db_session: AsyncSession):
    root_id = await _seed_root(db_session)
    await organization_service.create_org(db_session, OrgCreate(name="华北区", orgType="region", parentId=root_id))

    resp = await client.delete(f"/api/v1/admin/orgs/{root_id}", headers=ORG_RW)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_history_endpoint(client: AsyncClient, db_session: AsyncSession):
    root_id = await _seed_root(db_session)

    resp = await client.get(f"/api/v1/admin/orgs/{root_id}/history", headers=ORG_R)
    assert resp.status_code == 200
    data = _assert_envelope(resp)
    assert isinstance(data["items"], list)
    assert data["items"][0]["action"] == "created"


@pytest.mark.asyncio
async def test_write_without_permission_forbidden(client: AsyncClient):
    resp = await client.post(
        "/api/v1/admin/orgs", json={"name": "无权限", "orgType": "region"}, headers=NO_PERM
    )
    assert resp.status_code == 403
