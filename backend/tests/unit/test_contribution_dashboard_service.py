"""Unit tests for contribution_dashboard_service (FR-001~FR-008)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.binding import BindingStatus, Customer
from src.models.contribution import ContributionCategory, ContributionRecord, ContributionStatus
from src.schemas.organization import OrgCreate
from src.services import organization_service
from src.services.contribution_dashboard_service import (
    bindings_ranking,
    get_dashboard,
    org_ranking,
    persons_ranking,
)
from tests.conftest import seed_user


async def _seed_org(db: AsyncSession) -> int:
    return (await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))).id


async def _seed_distributor(db: AsyncSession, org_id: int, phone: str) -> int:
    user_id = await seed_user(db, openid=f"openid_{phone}", user_type="distributor", name=f"员{phone[-2:]}", phone=phone)
    from src.models.distributor import Distributor, OrgRole

    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole.MEMBER)
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return d.id


async def _seed_customer(db: AsyncSession, distributor_id: int, id_card: str) -> int:
    c = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000",
        phone_masked="138****8000", id_card_encrypted=id_card,
        id_card_masked="110***********1234", binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


async def _seed_contribution(db: AsyncSession, distributor_id: int, customer_id: int, points: str, txn: datetime) -> None:
    db.add(ContributionRecord(
        distributor_id=distributor_id, customer_id=customer_id, points=points,
        category=ContributionCategory.BILL, status=ContributionStatus.CONFIRMED,
        title="消费贡献", occurred_at=txn,
    ))
    await db.flush()


@pytest.mark.asyncio
async def test_dashboard_latest_30_ordered(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    d = await _seed_distributor(db_session, org_id, "13900000001")
    c = await _seed_customer(db_session, d, "110101199001011234")
    base = datetime(2026, 7, 1)
    for i in range(35):
        await _seed_contribution(db_session, d, c, "10.00", base + timedelta(hours=i))

    data = await get_dashboard(db_session, "2026-07")
    assert len(data["latest"]) == 30
    assert data["stats"]["monthlyPoints"] == 350.0
    # Latest is ordered by occurred_at desc
    times = [x["occurredAt"] for x in data["latest"]]
    assert times == sorted(times, reverse=True)


@pytest.mark.asyncio
async def test_org_ranking_ties_same_rank(db_session: AsyncSession):
    root = await _seed_org(db_session)
    child = (await organization_service.create_org(db_session, OrgCreate(name="华北区", orgType="region", parentId=root))).id
    d_root = await _seed_distributor(db_session, root, "13900000001")
    d_child = await _seed_distributor(db_session, child, "13900000002")
    c1 = await _seed_customer(db_session, d_root, "110101199001011234")
    c2 = await _seed_customer(db_session, d_child, "110101199001011235")
    await _seed_contribution(db_session, d_root, c1, "100.00", datetime(2026, 7, 5))
    await _seed_contribution(db_session, d_child, c2, "100.00", datetime(2026, 7, 6))  # 同分

    data = await org_ranking(db_session, "2026-07")
    assert data["total"] == 2
    assert data["items"][0]["rank"] == data["items"][1]["rank"] == 1


@pytest.mark.asyncio
async def test_persons_ranking_order(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    d1 = await _seed_distributor(db_session, org_id, "13900000001")
    d2 = await _seed_distributor(db_session, org_id, "13900000002")
    c = await _seed_customer(db_session, d1, "110101199001011234")
    await _seed_contribution(db_session, d1, c, "50.00", datetime(2026, 7, 10))
    await _seed_contribution(db_session, d2, c, "50.00", datetime(2026, 7, 11))
    await _seed_contribution(db_session, d2, c, "20.00", datetime(2026, 7, 12))

    data = await persons_ranking(db_session, "2026-07")
    assert data["total"] == 2
    assert data["items"][0]["distributorId"] == str(d2)
    assert data["items"][0]["points"] == 70.0
    assert data["items"][1]["points"] == 50.0


@pytest.mark.asyncio
async def test_bindings_ranking_person_org(db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    d1 = await _seed_distributor(db_session, org_id, "13900000001")
    d2 = await _seed_distributor(db_session, org_id, "13900000002")
    await _seed_customer(db_session, d1, "110101199001011234")
    await _seed_customer(db_session, d1, "110101199001011235")
    await _seed_customer(db_session, d2, "110101199001011236")

    person = await bindings_ranking(db_session, "person")
    by_id = {i["distributorId"]: i["boundCount"] for i in person["items"]}
    assert by_id[str(d1)] == 2
    assert by_id[str(d2)] == 1

    org = await bindings_ranking(db_session, "org")
    assert org["items"][0]["orgId"] == str(org_id)
    assert org["items"][0]["boundCount"] == 3
