"""Contract tests for admin org qualification endpoints (US2)."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token


def _headers(*perms: str) -> dict:
    token = make_access_token(user_id=1, user_type="admin", permissions=list(perms))
    return {"Authorization": f"Bearer {token}"}


ORG_RW = _headers("org.read", "org.write", "qualifications.write")
NO_REVIEW = _headers("org.read", "org.write")


async def _seed_org(db: AsyncSession) -> int:
    org = await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))
    return org.id


def _payload():
    return {
        "legalEntityName": "北京儒泰测试公司",
        "qualificationTypes": ["business_license"],
        "creditCode": "91110000TEST000001",
        "fileUrls": [{"url": "https://cos.example.com/q.pdf", "type": "pdf", "size": 1}],
        "validUntil": (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d"),
    }


@pytest.mark.asyncio
async def test_upload_and_review_flow(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)

    resp = await client.post(
        f"/api/v1/admin/orgs/{org_id}/qualifications", json=_payload(), headers=ORG_RW
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    qid = body["data"]["qualificationId"]
    assert body["data"]["status"] == "reviewing"

    review = await client.post(
        f"/api/v1/admin/org-qualifications/{qid}/review",
        json={"action": "approve"},
        headers=ORG_RW,
    )
    assert review.status_code == 200
    assert review.json()["data"]["status"] == "approved"

    listing = await client.get(f"/api/v1/admin/orgs/{org_id}/qualifications", headers=ORG_RW)
    assert listing.json()["data"]["items"][0]["status"] == "approved"


@pytest.mark.asyncio
async def test_review_without_permission_forbidden(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    resp = await client.post(
        f"/api/v1/admin/orgs/{org_id}/qualifications", json=_payload(), headers=ORG_RW
    )
    qid = resp.json()["data"]["qualificationId"]

    review = await client.post(
        f"/api/v1/admin/org-qualifications/{qid}/review",
        json={"action": "approve"},
        headers=NO_REVIEW,
    )
    assert review.status_code == 403
