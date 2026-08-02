"""Contract tests for org performance endpoint (US5)."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.binding import BindingStatus, Customer
from src.models.contribution import ContributionCategory, ContributionRecord, ContributionStatus
from src.models.distributor import Distributor
from src.models.user import User
from src.schemas.distributor import DistributorCreate, DistributorRoleUpdate
from src.schemas.organization import OrgCreate
from src.services import distributor_service, organization_service
from tests.conftest import make_access_token


def _dist_headers(user_id: int) -> dict:
    token = make_access_token(user_id=user_id, user_type="distributor")
    return {"Authorization": f"Bearer {token}"}


async def _seed(db: AsyncSession):
    root = await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))
    d = await distributor_service.create_distributor(
        db, root.id, DistributorCreate(name="管理员", phone="13800000001", initialPassword="password123")
    )
    await distributor_service.set_role(db, int(d["distributorId"]), DistributorRoleUpdate(orgRole="admin"))
    did = int(d["distributorId"])

    customer = Customer(distributor_id=did, binding_status=BindingStatus.BOUND)
    db.add(customer)
    await db.flush()
    db.add(ContributionRecord(
        distributor_id=did,
        customer_id=customer.id,
        points="88.00",
        status=ContributionStatus.PENDING,
        category=ContributionCategory.BILL,
        title="t",
        occurred_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    user_id = (await db.execute(select(Distributor.user_id).where(Distributor.id == did))).scalar()
    return user_id


@pytest.mark.asyncio
async def test_org_performance_returns_summary(client: AsyncClient, db_session: AsyncSession):
    admin_user_id = await _seed(db_session)
    resp = await client.get("/api/v1/org/performance", headers=_dist_headers(admin_user_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["summary"]["cumulative"] == "88.00"
    assert len(body["data"]["members"]) == 1


@pytest.mark.asyncio
async def test_non_admin_forbidden(client: AsyncClient, db_session: AsyncSession):
    root = await organization_service.create_org(db_session, OrgCreate(name="总部", orgType="headquarters"))
    await distributor_service.create_distributor(
        db_session, root.id, DistributorCreate(name="成员", phone="13800000002", initialPassword="password123")
    )
    u = (await db_session.execute(select(User).where(User.phone == "13800000002"))).scalars().first()
    resp = await client.get("/api/v1/org/performance", headers=_dist_headers(u.id))
    assert resp.status_code == 403
