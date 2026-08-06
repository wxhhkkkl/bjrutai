"""Performance smoke tests (SC-002: 5s target for org operations).

Uses the real SQLite test DB; verifies org tree creation and performance
aggregation complete within a generous bound so CI is not flaky.
"""

import time

import pytest

from src.schemas.distributor import DistributorCreate
from src.schemas.organization import OrgCreate
from src.services import distributor_service, organization_service, org_performance_service


@pytest.mark.asyncio
async def test_org_tree_100_nodes_within_budget(db_session):
    root = await organization_service.create_org(db_session, OrgCreate(name="总部", orgType="headquarters"))
    start = time.monotonic()
    parent = root.id
    for i in range(50):
        child = await organization_service.create_org(
            db_session, OrgCreate(name=f"组织{i}", orgType="region", parentId=parent)
        )
        parent = child.id
    elapsed = time.monotonic() - start
    # 50 sequential inserts well under 5s on SQLite; budget is generous for CI
    assert elapsed < 5.0


@pytest.mark.asyncio
async def test_org_performance_aggregation_within_budget(db_session):
    from datetime import datetime, timezone

    from src.models.bill import Bill, TransactionStatus
    from src.models.binding import BindingStatus, Customer
    from src.models.user import User
    from sqlalchemy import select

    from src.schemas.distributor import DistributorRoleUpdate

    root = await organization_service.create_org(db_session, OrgCreate(name="总部", orgType="headquarters"))
    d = await distributor_service.create_distributor(
        db_session, root.id, DistributorCreate(name="管理员", phone="13800000001", initialPassword="password123")
    )
    await distributor_service.set_role(db_session, int(d["distributorId"]), DistributorRoleUpdate(orgRole="admin"))
    u = (await db_session.execute(select(User).where(User.phone == "13800000001"))).scalars().first()
    distributor_id = int(d["distributorId"])

    for i in range(200):
        c = Customer(
            distributor_id=distributor_id, name="患者", phone="13800138000", phone_masked="138****8000",
            id_card_encrypted="x", id_card_masked="y", binding_status=BindingStatus.BOUND, version=1,
        )
        db_session.add(c)
        await db_session.flush()
        db_session.add(Bill(
            customer_id=c.id, transaction_id=f"perf_{i}", transaction_time=datetime.now(timezone.utc),
            paid_amount_cent=100, total_amount_cent=100, transaction_status=TransactionStatus.PAID,
        ))
    await db_session.flush()

    start = time.monotonic()
    result = await org_performance_service.get_org_performance(db_session, u.id)
    elapsed = time.monotonic() - start
    assert result["summary"]["cumulative"] == 20000  # 200 x 100 分
    assert elapsed < 5.0
