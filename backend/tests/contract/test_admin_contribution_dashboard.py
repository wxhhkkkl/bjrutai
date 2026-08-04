"""Contract tests for admin contribution dashboard endpoints (US1-US5)."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.binding import BindingStatus, Customer
from src.models.contribution import ContributionCategory, ContributionRecord, ContributionStatus
from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token, seed_user


def _admin_headers(*perms: str) -> dict:
    token = make_access_token(user_id=1, user_type="admin", permissions=list(perms))
    return {"Authorization": f"Bearer {token}"}


R = _admin_headers("contributions.read")
NO_PERM = _admin_headers("unrelated.read")


def _assert_envelope(resp):
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "success"
    return body["data"]


def _status_code(resp):
    return resp.json().get("code")


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


async def _seed_bound_customer(db: AsyncSession, distributor_id: int, id_card: str) -> int:
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
async def test_dashboard_stats_trend_latest(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    d1 = await _seed_distributor(db_session, org_id, "13900000001")
    d2 = await _seed_distributor(db_session, org_id, "13900000002")
    c1 = await _seed_bound_customer(db_session, d1, "110101199001011234")
    c2 = await _seed_bound_customer(db_session, d1, "110101199001011235")
    await _seed_contribution(db_session, d1, c1, "100.00", datetime(2026, 7, 10))
    await _seed_contribution(db_session, d1, c2, "50.00", datetime(2026, 7, 15))
    await _seed_contribution(db_session, d2, c1, "200.00", datetime(2026, 6, 20))  # 上月

    data = _assert_envelope(await client.get(
        "/api/v1/admin/contributions/dashboard", params={"month": "2026-07"}, headers=R
    ))
    assert data["stats"]["monthlyPoints"] == 150.0  # 100 + 50 (上月不计入)
    assert data["stats"]["totalPoints"] == 350.0
    assert data["stats"]["orgCount"] == 1
    assert data["stats"]["personCount"] == 2
    assert data["stats"]["boundUserCount"] == 2
    assert len(data["trend"]) == 12
    assert data["trend"][-1]["month"] == "2026-07"
    assert len(data["latest"]) == 3  # 含上月记录（最新 30 条不限当月）
    assert data["latest"][0]["points"] == 50.0   # occurred_at 倒序：07-15 最新
    assert data["latest"][2]["points"] == 200.0  # 06-20 最旧


@pytest.mark.asyncio
async def test_dashboard_requires_read_permission(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    resp = await client.get("/api/v1/admin/contributions/dashboard", params={"month": "2026-07"}, headers=NO_PERM)
    assert _status_code(resp) == 40300


@pytest.mark.asyncio
async def test_orgs_ranking(client: AsyncClient, db_session: AsyncSession):
    root = await _seed_org(db_session)
    child = (await organization_service.create_org(db_session, OrgCreate(name="华北区", orgType="region", parentId=root))).id
    d_root = await _seed_distributor(db_session, root, "13900000001")
    d_child = await _seed_distributor(db_session, child, "13900000002")
    c1 = await _seed_bound_customer(db_session, d_root, "110101199001011234")
    c2 = await _seed_bound_customer(db_session, d_child, "110101199001011235")
    await _seed_contribution(db_session, d_root, c1, "300.00", datetime(2026, 7, 5))
    await _seed_contribution(db_session, d_child, c2, "600.00", datetime(2026, 7, 6))

    data = _assert_envelope(await client.get(
        "/api/v1/admin/contributions/rankings/orgs", params={"month": "2026-07"}, headers=R
    ))
    assert data["total"] == 2
    assert data["items"][0]["rank"] == 1
    assert data["items"][0]["orgId"] == str(child)
    assert data["items"][0]["points"] == 600.0
    assert data["items"][1]["points"] == 300.0


@pytest.mark.asyncio
async def test_persons_ranking(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    d1 = await _seed_distributor(db_session, org_id, "13900000001")
    d2 = await _seed_distributor(db_session, org_id, "13900000002")
    c = await _seed_bound_customer(db_session, d1, "110101199001011234")
    await _seed_contribution(db_session, d1, c, "100.00", datetime(2026, 7, 10))
    await _seed_contribution(db_session, d2, c, "250.00", datetime(2026, 7, 11))

    data = _assert_envelope(await client.get(
        "/api/v1/admin/contributions/rankings/persons", params={"month": "2026-07"}, headers=R
    ))
    assert data["total"] == 2
    assert data["items"][0]["distributorId"] == str(d2)
    assert data["items"][0]["points"] == 250.0
    assert data["items"][1]["points"] == 100.0


@pytest.mark.asyncio
async def test_bindings_ranking_person_and_org(client: AsyncClient, db_session: AsyncSession):
    root = await _seed_org(db_session)
    child = (await organization_service.create_org(db_session, OrgCreate(name="华北区", orgType="region", parentId=root))).id
    d_root = await _seed_distributor(db_session, root, "13900000001")
    d_child = await _seed_distributor(db_session, child, "13900000002")
    await _seed_bound_customer(db_session, d_root, "110101199001011234")
    await _seed_bound_customer(db_session, d_root, "110101199001011235")
    await _seed_bound_customer(db_session, d_child, "110101199001011236")

    person = _assert_envelope(await client.get(
        "/api/v1/admin/contributions/rankings/bindings", params={"scope": "person"}, headers=R
    ))
    assert person["total"] == 2
    by_id = {i["distributorId"]: i["boundCount"] for i in person["items"]}
    assert by_id[str(d_root)] == 2
    assert by_id[str(d_child)] == 1

    org_data = _assert_envelope(await client.get(
        "/api/v1/admin/contributions/rankings/bindings", params={"scope": "org"}, headers=R
    ))
    assert org_data["total"] == 2
    by_org = {i["orgId"]: i["boundCount"] for i in org_data["items"]}
    assert by_org[str(root)] == 2
    assert by_org[str(child)] == 1
