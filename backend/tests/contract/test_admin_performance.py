"""Contract tests for admin performance module (008, US1/US2/US4).

Covers: estimates (US1), settlement review/reject/recompute (US2),
and CSV export (US4), per contracts/admin-performance.md.
"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.commission_result import CommissionResult
from src.models.performance_rule import RuleType
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token, seed_user


def _admin_headers(*perms: str) -> dict:
    token = make_access_token(user_id=1, user_type="admin", permissions=list(perms))
    return {"Authorization": f"Bearer {token}"}


R_R = _admin_headers("sharing_rules.read")
R_RW = _admin_headers("sharing_rules.read", "sharing_rules.write")
R_SETTLE = _admin_headers("performance.settle")
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


async def _seed_distributor(db: AsyncSession, org_id: int, phone: str = "13900000001", role: str = "member") -> int:
    user_id = await seed_user(db, openid=f"openid_{phone}", user_type="distributor", name="推广员A", phone=phone)
    from src.models.distributor import Distributor, OrgRole

    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole(role))
    db.add(d)
    await db.flush()
    await db.refresh(d)
    return d.id


async def _seed_customer(db: AsyncSession, distributor_id: int) -> int:
    c = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000",
        phone_masked="138****8000", id_card_encrypted="110101199001011234",
        id_card_masked="110***********1234", binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


async def _seed_bill(db: AsyncSession, customer_id: int, paid_cent: int, txn_id: str, status=TransactionStatus.PAID) -> int:
    b = Bill(
        customer_id=customer_id, transaction_id=txn_id, transaction_time=datetime(2026, 7, 15),
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent, transaction_status=status,
    )
    db.add(b)
    await db.flush()
    return b.id


def _tiers(*pairs) -> list:
    out = []
    for mn, mx, ratio in pairs:
        out.append({"minCent": mn, "maxCent": mx, "ratio": ratio})
    return out


async def _config_intra_rule(client: AsyncClient, org_id: int, tiers=None):
    return await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": tiers or _tiers((0, None, 0.05))},
        headers=R_RW,
    )


async def _seed_settlement(db: AsyncSession, period: str, status: SettlementStatus = SettlementStatus.PENDING) -> int:
    s = PerformanceSettlement(period=period, status=status)
    db.add(s)
    await db.flush()
    await db.refresh(s)
    return s.id


# ──────────────────────────────────────────────────────────────────
# US1: estimates (real-time, not persisted)
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_estimates_returns_person_estimates(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, paid_cent=800000, txn_id="txn_1")

    await _config_intra_rule(client, org_id, _tiers((0, 1000000, 0.05), (1000000, None, 0.08)))

    data = _assert_envelope(await client.get(
        "/api/v1/admin/performance/estimates",
        params={"period": "2026-07", "orgId": org_id}, headers=R_R,
    ))
    assert data["orgId"] == str(org_id)
    assert len(data["intraOrg"]) == 1
    assert data["intraOrg"][0]["baseCent"] == 800000
    assert data["intraOrg"][0]["ratio"] == 0.05
    assert data["intraOrg"][0]["commissionCent"] == 40000
    assert "org_management" in data["unconfigured"]

    # Estimate must NOT persist (SC-002)
    results = (await db_session.execute(select(CommissionResult))).scalars().all()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_estimates_requires_read_permission(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    resp = await client.get(
        "/api/v1/admin/performance/estimates",
        params={"period": "2026-07", "orgId": org_id}, headers=NO_PERM,
    )
    assert _status_code(resp) == 40300


# ──────────────────────────────────────────────────────────────────
# US2: settlement review / reject / recompute
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_settlement_review_marks_reviewed(client: AsyncClient, db_session: AsyncSession):
    await _seed_settlement(db_session, "2026-07")
    data = _assert_envelope(await client.post("/api/v1/admin/performance/settlements/2026-07/review", headers=R_SETTLE))
    assert data["status"] == "reviewed"
    assert data["reviewedBy"] == 1

    got = _assert_envelope(await client.get("/api/v1/admin/performance/settlements", params={"period": "2026-07"}, headers=R_R))
    assert got["items"][0]["status"] == "reviewed"
    assert got["items"][0]["reviewedBy"] == 1


@pytest.mark.asyncio
async def test_settlement_review_idempotent(client: AsyncClient, db_session: AsyncSession):
    await _seed_settlement(db_session, "2026-07", SettlementStatus.REVIEWED)
    resp = await client.post("/api/v1/admin/performance/settlements/2026-07/review", headers=R_SETTLE)
    assert _status_code(resp) == 40000  # already confirmed -> reject duplicate


@pytest.mark.asyncio
async def test_settlement_reject_then_recompute(client: AsyncClient, db_session: AsyncSession):
    await _seed_settlement(db_session, "2026-07")
    data = _assert_envelope(await client.post(
        "/api/v1/admin/performance/settlements/2026-07/reject",
        json={"reason": "核对有误"}, headers=R_SETTLE,
    ))
    assert data["status"] == "rejected"
    assert data["rejectReason"] == "核对有误"

    data2 = _assert_envelope(await client.post("/api/v1/admin/performance/settlements/2026-07/recompute", headers=R_SETTLE))
    assert data2["status"] == "pending"


@pytest.mark.asyncio
async def test_settlement_reject_requires_reason(client: AsyncClient, db_session: AsyncSession):
    await _seed_settlement(db_session, "2026-07")
    # Blank reason is rejected by the service (business rule, FR-013)
    resp = await client.post("/api/v1/admin/performance/settlements/2026-07/reject", json={"reason": ""}, headers=R_SETTLE)
    assert _status_code(resp) == 40000


@pytest.mark.asyncio
async def test_settlement_actions_require_settle_permission(client: AsyncClient, db_session: AsyncSession):
    await _seed_settlement(db_session, "2026-07")
    for action in ("review", "reject", "recompute"):
        resp = await client.post(f"/api/v1/admin/performance/settlements/2026-07/{action}", json={}, headers=R_R)
        assert _status_code(resp) == 40300


@pytest.mark.asyncio
async def test_settlement_review_frozen_blocks_recompute(client: AsyncClient, db_session: AsyncSession):
    await _seed_settlement(db_session, "2026-07", SettlementStatus.REVIEWED)
    resp = await client.post("/api/v1/admin/performance/settlements/2026-07/recompute", headers=R_SETTLE)
    assert _status_code(resp) == 40000  # frozen period cannot recompute (FR-006)


# ──────────────────────────────────────────────────────────────────
# US4: export CSV
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_export_csv(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    db_session.add(CommissionResult(
        period="2026-07", distributor_id=dist, org_id=org_id,
        rule_type=RuleType.INTRA_ORG, base_cent=800000, ratio="0.050000",
        commission_cent=40000, rule_snapshot={"ruleType": "intra_org", "tiers": [], "version": 1},
    ))
    await db_session.flush()

    resp = await client.get("/api/v1/admin/performance/settlements/2026-07/export", headers=R_SETTLE)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "2026-07" in resp.text
    assert "推广员A" in resp.text
    assert "40000" in resp.text


@pytest.mark.asyncio
async def test_export_requires_settle_permission(client: AsyncClient, db_session: AsyncSession):
    resp = await client.get("/api/v1/admin/performance/settlements/2026-07/export", headers=R_R)
    assert _status_code(resp) == 40300
