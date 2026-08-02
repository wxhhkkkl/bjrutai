"""Unit tests for org_performance_service (US5)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.core.exceptions import ForbiddenException
from src.models.binding import BindingStatus, Customer
from src.models.contribution import ContributionCategory, ContributionRecord, ContributionStatus
from src.models.distributor import Distributor
from src.models.user import User
from src.schemas.distributor import DistributorCreate, DistributorRoleUpdate
from src.schemas.organization import OrgCreate
from src.services import distributor_service, organization_service, org_performance_service


async def _make_contribution(db, distributor_id: int, points: str, occurred_at: datetime) -> int:
    customer = Customer(distributor_id=distributor_id, binding_status=BindingStatus.BOUND)
    db.add(customer)
    await db.flush()
    cr = ContributionRecord(
        distributor_id=distributor_id,
        customer_id=customer.id,
        points=points,
        status=ContributionStatus.PENDING,
        category=ContributionCategory.BILL,
        title="test",
        occurred_at=occurred_at,
    )
    db.add(cr)
    await db.flush()
    return cr.id


async def _seed_scenario(db):
    """Root -> A. Admin distributor under root (user1); member under A (user2)."""
    root = await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))
    child_a = await organization_service.create_org(db, OrgCreate(name="A区", orgType="region", parentId=root.id))

    d1 = await distributor_service.create_distributor(
        db, root.id, DistributorCreate(name="管理员", phone="13800000001", initialPassword="password123")
    )
    await distributor_service.set_role(db, int(d1["distributorId"]), DistributorRoleUpdate(orgRole="admin"))
    d2 = await distributor_service.create_distributor(
        db, child_a.id, DistributorCreate(name="成员", phone="13800000002", initialPassword="password123")
    )

    now = datetime.now(timezone.utc)
    await _make_contribution(db, int(d1["distributorId"]), "100.00", now)
    await _make_contribution(db, int(d2["distributorId"]), "50.00", now)
    return int(d1["distributorId"]), int(d2["distributorId"]), root.id, int(d1["distributorId"])


@pytest.mark.asyncio
async def test_admin_sees_subtree_performance(db_session):
    admin_did, _, root_id, _ = await _seed_scenario(db_session)
    admin_user_id = (await db_session.execute(select(Distributor.user_id).where(Distributor.id == admin_did))).scalar()
    result = await org_performance_service.get_org_performance(db_session, admin_user_id)
    assert result["orgId"] == str(root_id)
    assert result["summary"]["cumulative"] == "150.00"   # 100 + 50 (includes sub-org)
    assert result["summary"]["thisMonth"] == "150.00"
    assert len(result["members"]) == 2


@pytest.mark.asyncio
async def test_non_admin_forbidden(db_session):
    _, member_did, _, _ = await _seed_scenario(db_session)
    member_user_id = (await db_session.execute(select(Distributor.user_id).where(Distributor.id == member_did))).scalar()
    with pytest.raises(ForbiddenException):
        await org_performance_service.get_org_performance(db_session, member_user_id)


@pytest.mark.asyncio
async def test_month_filter(db_session):
    admin_did, _, _, _ = await _seed_scenario(db_session)
    admin_user_id = (await db_session.execute(select(Distributor.user_id).where(Distributor.id == admin_did))).scalar()
    result = await org_performance_service.get_org_performance(db_session, admin_user_id, month="2000-01")
    assert result["summary"]["thisMonth"] == "0.00"
    assert result["summary"]["cumulative"] == "150.00"


@pytest.mark.asyncio
async def test_revoked_admin_forbidden_after_role_change(db_session):
    admin_did, _, _, _ = await _seed_scenario(db_session)
    await distributor_service.set_role(db_session, admin_did, DistributorRoleUpdate(orgRole="member"))
    admin_user_id = (await db_session.execute(select(Distributor.user_id).where(Distributor.id == admin_did))).scalar()
    with pytest.raises(ForbiddenException):
        await org_performance_service.get_org_performance(db_session, admin_user_id)
