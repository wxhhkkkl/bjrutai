"""Unit tests for org_performance_service (US5) — 消费金额（分）口径."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.core.exceptions import ForbiddenException
from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.distributor import Distributor
from src.schemas.distributor import DistributorCreate, DistributorRoleUpdate
from src.schemas.organization import OrgCreate
from src.services import distributor_service, organization_service, org_performance_service


async def _make_bill(db, distributor_id: int, paid_cent: int, txn_id: str, when: datetime | None = None) -> int:
    customer = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000", phone_masked="138****8000",
        id_card_encrypted="x", id_card_masked="y", binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(customer)
    await db.flush()
    b = Bill(
        customer_id=customer.id, transaction_id=txn_id,
        transaction_time=when or datetime.now(timezone.utc),
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent,
        transaction_status=TransactionStatus.PAID,
    )
    db.add(b)
    await db.flush()
    return b.id


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
    await _make_bill(db, int(d1["distributorId"]), 10000, "txn_admin", now)
    await _make_bill(db, int(d2["distributorId"]), 5000, "txn_member", now)
    return int(d1["distributorId"]), int(d2["distributorId"]), root.id


@pytest.mark.asyncio
async def test_admin_sees_subtree_consumption(db_session):
    admin_did, _, root_id = await _seed_scenario(db_session)
    admin_user_id = (await db_session.execute(select(Distributor.user_id).where(Distributor.id == admin_did))).scalar()
    result = await org_performance_service.get_org_performance(db_session, admin_user_id)
    assert result["orgId"] == str(root_id)
    assert result["summary"]["cumulative"] == 15000  # 10000 + 5000 (includes sub-org)
    assert result["summary"]["thisMonth"] == 15000
    assert len(result["members"]) == 2


@pytest.mark.asyncio
async def test_non_admin_forbidden(db_session):
    _, member_did, _ = await _seed_scenario(db_session)
    member_user_id = (await db_session.execute(select(Distributor.user_id).where(Distributor.id == member_did))).scalar()
    with pytest.raises(ForbiddenException):
        await org_performance_service.get_org_performance(db_session, member_user_id)


@pytest.mark.asyncio
async def test_month_filter(db_session):
    admin_did, _, _ = await _seed_scenario(db_session)
    admin_user_id = (await db_session.execute(select(Distributor.user_id).where(Distributor.id == admin_did))).scalar()
    result = await org_performance_service.get_org_performance(db_session, admin_user_id, month="2000-01")
    assert result["summary"]["thisMonth"] == 0
    assert result["summary"]["cumulative"] == 15000


@pytest.mark.asyncio
async def test_revoked_admin_forbidden_after_role_change(db_session):
    admin_did, _, _ = await _seed_scenario(db_session)
    await distributor_service.set_role(db_session, admin_did, DistributorRoleUpdate(orgRole="member"))
    admin_user_id = (await db_session.execute(select(Distributor.user_id).where(Distributor.id == admin_did))).scalar()
    with pytest.raises(ForbiddenException):
        await org_performance_service.get_org_performance(db_session, admin_user_id)
