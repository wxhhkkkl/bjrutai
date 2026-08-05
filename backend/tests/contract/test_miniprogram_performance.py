"""Contract tests for mini-program performance endpoints (008, US3, FR-009)."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.commission_result import CommissionResult
from src.models.performance_rule import RuleType
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token, seed_user


def _headers(user_id: int, user_type: str = "promoter") -> dict:
    token = make_access_token(user_id=user_id, user_type=user_type)
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(*perms: str) -> dict:
    return {"Authorization": f"Bearer {make_access_token(user_id=1, user_type='admin', permissions=list(perms))}"}


def _assert_envelope(resp):
    body = resp.json()
    assert body["code"] == 0
    return body["data"]


async def _seed_org(db: AsyncSession) -> int:
    return (await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))).id


async def _seed_distributor(db: AsyncSession, org_id: int, user_id: int, role: str = "member") -> int:
    from src.models.distributor import Distributor, OrgRole

    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole(role))
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return d.id


async def _seed_customer(db: AsyncSession, distributor_id: int) -> int:
    c = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000", phone_masked="138****8000",
        id_card_encrypted="110101199001011234", id_card_masked="110***********1234",
        binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


async def _seed_bill(db: AsyncSession, customer_id: int, paid_cent: int, txn_id: str) -> None:
    b = Bill(
        customer_id=customer_id, transaction_id=txn_id, transaction_time=datetime(2026, 7, 15),
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent, transaction_status=TransactionStatus.PAID,
    )
    db.add(b)
    await db.flush()


async def _config_intra_rule(client: AsyncClient, org_id: int) -> None:
    await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": [{"minCent": 0, "maxCent": 1000000, "ratio": 0.05}, {"minCent": 1000000, "maxCent": None, "ratio": 0.08}]},
        headers=_admin_headers("sharing_rules.read", "sharing_rules.write"),
    )


async def _config_mgmt_rule(client: AsyncClient, org_id: int) -> None:
    await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/org_management",
        json={"tiers": [{"minCent": 0, "maxCent": None, "ratio": 0.08}]},
        headers=_admin_headers("sharing_rules.read", "sharing_rules.write"),
    )


@pytest.mark.asyncio
async def test_my_commission_estimate_and_confirmed(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    user_id = await seed_user(db_session, openid="openid_p", user_type="distributor", name="推广员A")
    dist = await _seed_distributor(db_session, org_id, user_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 800000, "txn_1")
    await _config_intra_rule(client, org_id)

    # Reviewed month with frozen result + pending month that must NOT surface
    db_session.add(CommissionResult(
        period="2026-06", distributor_id=dist, org_id=org_id, rule_type=RuleType.INTRA_ORG,
        base_cent=600000, ratio="0.050000", commission_cent=30000,
    ))
    db_session.add(PerformanceSettlement(period="2026-06", status=SettlementStatus.REVIEWED))
    db_session.add(PerformanceSettlement(period="2026-05", status=SettlementStatus.PENDING))
    await db_session.flush()

    data = _assert_envelope(await client.get(
        "/api/v1/my/performance/commission", params={"month": "2026-07"}, headers=_headers(user_id),
    ))
    cur = data["currentMonth"]
    assert cur["month"] == "2026-07"
    assert cur["status"] == "estimate"
    assert cur["intraOrg"]["baseCent"] == 800000
    assert cur["intraOrg"]["commissionCent"] == 40000
    assert cur["orgManagement"] is None

    months = {m["month"]: m for m in data["confirmed"]}
    assert "2026-06" in months
    assert months["2026-06"]["intraOrg"]["commissionCent"] == 30000
    assert "2026-05" not in months  # pending month not shown as confirmed (FR-004)


@pytest.mark.asyncio
async def test_estimate_matches_admin_estimates(client: AsyncClient, db_session: AsyncSession):
    """SC-008: mini-program estimate equals admin estimates for the same distributor."""
    org_id = await _seed_org(db_session)
    user_id = await seed_user(db_session, openid="openid_q", user_type="distributor", name="推广员A")
    dist = await _seed_distributor(db_session, org_id, user_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 800000, "txn_1")
    await _config_intra_rule(client, org_id)

    admin_data = _assert_envelope(await client.get(
        "/api/v1/admin/performance/estimates", params={"period": "2026-07", "orgId": org_id},
        headers=_admin_headers("sharing_rules.read"),
    ))
    mp_data = _assert_envelope(await client.get(
        "/api/v1/my/performance/commission", params={"month": "2026-07"}, headers=_headers(user_id),
    ))
    admin_item = admin_data["intraOrg"][0]
    mp_item = mp_data["currentMonth"]["intraOrg"]
    assert admin_item["distributorId"] == str(dist)
    assert mp_item["baseCent"] == admin_item["baseCent"]
    assert mp_item["commissionCent"] == admin_item["commissionCent"]


@pytest.mark.asyncio
async def test_org_commission_requires_admin(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    user_id = await seed_user(db_session, openid="openid_m", user_type="distributor", name="成员")
    await _seed_distributor(db_session, org_id, user_id, role="member")
    resp = await client.get("/api/v1/org/performance/commission", headers=_headers(user_id))
    assert resp.json()["code"] == 40300


@pytest.mark.asyncio
async def test_org_commission_admin_view(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    user_id = await seed_user(db_session, openid="openid_adm", user_type="distributor", name="管理员")
    dist = await _seed_distributor(db_session, org_id, user_id, role="admin")
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 500000, "txn_1")
    await _config_mgmt_rule(client, org_id)

    data = _assert_envelope(await client.get(
        "/api/v1/org/performance/commission", params={"month": "2026-07"}, headers=_headers(user_id),
    ))
    assert data["orgId"] == str(org_id)
    cur = data["currentMonth"]
    assert cur["status"] == "estimate"
    assert cur["summary"]["baseCent"] == 500000
    assert cur["summary"]["commissionCent"] == 40000
    assert len(cur["members"]) == 1
