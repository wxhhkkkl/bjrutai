"""Integration test: full performance settlement journey (008, US1-US4, SC-003/SC-004/SC-006)."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.commission_result import CommissionResult
from src.models.performance_settlement import PerformanceSettlement, SettlementStatus
from src.schemas.organization import OrgCreate
from src.services import commission_service, organization_service
from tests.conftest import make_access_token, seed_user


def _admin_headers(*perms: str) -> dict:
    return {"Authorization": f"Bearer {make_access_token(user_id=1, user_type='admin', permissions=list(perms))}"}


def _headers(user_id: int) -> dict:
    return {"Authorization": f"Bearer {make_access_token(user_id=user_id, user_type='promoter')}"}


async def _seed_org(db: AsyncSession) -> int:
    return (await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))).id


async def _seed_distributor(db: AsyncSession, org_id: int, user_id: int) -> int:
    from src.models.distributor import Distributor, OrgRole

    d = Distributor(user_id=user_id, org_id=org_id, org_role=OrgRole.MEMBER)
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


async def _seed_bill(db: AsyncSession, customer_id: int, paid_cent: int, txn_id: str, when: datetime) -> None:
    b = Bill(
        customer_id=customer_id, transaction_id=txn_id, transaction_time=when,
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent, transaction_status=TransactionStatus.PAID,
    )
    db.add(b)
    await db.flush()


async def _config_rule(client: AsyncClient, org_id: int, ratio: float) -> None:
    await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": [{"minCent": 0, "maxCent": None, "ratio": ratio}]},
        headers=_admin_headers("sharing_rules.read", "sharing_rules.write"),
    )


@pytest.mark.asyncio
async def test_settle_review_freeze_and_confirmed_display(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    user_id = await seed_user(db_session, openid="openid_f", user_type="distributor", name="推广员A")
    dist = await _seed_distributor(db_session, org_id, user_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 800000, "txn_0701", datetime(2026, 7, 10))
    await _config_rule(client, org_id, 0.05)

    # ── settle July 2026 (auto-compute creates pending batch + results with snapshot) ──
    result = await commission_service.compute_commission(db_session, "2026-07")
    await db_session.commit()
    assert result["frozen"] is False
    rows = (await db_session.execute(select(CommissionResult))).scalars().all()
    assert len(rows) == 1
    assert rows[0].commission_cent == 40000
    assert rows[0].rule_snapshot["tiers"][0]["ratio"] == 0.05

    # ── SC-003: pending month not shown as confirmed to mini-program ──
    mp = (await client.get("/api/v1/my/performance/commission", params={"month": "2026-07"}, headers=_headers(user_id))).json()["data"]
    assert mp["currentMonth"]["intraOrg"]["commissionCent"] == 40000
    assert "2026-07" not in {m["month"] for m in mp["confirmed"]}

    # ── review → reviewed with reviewer recorded (SC-006) ──
    reviewed = (await client.post("/api/v1/admin/performance/settlements/2026-07/review", headers=_admin_headers("performance.settle"))).json()["data"]
    assert reviewed["status"] == "reviewed"
    assert reviewed["reviewedBy"] == 1

    # ── SC-004: frozen — recompute on reviewed period rejected ──
    resp = await client.post("/api/v1/admin/performance/settlements/2026-07/recompute", headers=_admin_headers("performance.settle"))
    assert resp.json()["code"] == 40000

    # ── confirmed now surfaces with frozen value ──
    mp2 = (await client.get("/api/v1/my/performance/commission", params={"month": "2026-07"}, headers=_headers(user_id))).json()["data"]
    confirmed = {m["month"]: m for m in mp2["confirmed"]}
    assert confirmed["2026-07"]["intraOrg"]["commissionCent"] == 40000

    # ── SC-005: rule change does NOT alter the confirmed/frozen month ──
    await _config_rule(client, org_id, 0.10)
    rows_after = (await db_session.execute(select(CommissionResult))).scalars().all()
    assert rows_after[0].commission_cent == 40000  # unchanged (frozen)

    # ── export reflects the frozen result (SC-007) ──
    export = await client.get("/api/v1/admin/performance/settlements/2026-07/export", headers=_admin_headers("performance.settle"))
    assert export.status_code == 200
    assert "40000" in export.text


# ──────────────────────────────────────────────────────────────────
# 010: settle (US1) → report record (US2) → review freeze/reject (US3)
# ──────────────────────────────────────────────────────────────────
from src.models.report import Report


@pytest.mark.asyncio
async def test_settle_report_review_reject_full_loop(client: AsyncClient, db_session: AsyncSession):
    """Full loop: settle → report pending → review freeze → reject/recompute → report sync (SC-003/SC-004/SC-005/SC-006/SC-008)."""
    org_id = await _seed_org(db_session)
    user_id = await seed_user(db_session, openid="openid_010", user_type="distributor", name="推广员010")
    dist = await _seed_distributor(db_session, org_id, user_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, 800000, "txn_010_1", datetime(2026, 6, 10))
    await _seed_bill(db_session, cid, 800000, "txn_010_2", datetime(2026, 7, 10))
    await _config_rule(client, org_id, 0.05)

    # ── US1: settleable periods lists June & July ──
    periods = (await client.get("/api/v1/admin/performance/settleable-periods", headers=_admin_headers("sharing_rules.read"))).json()["data"]["periods"]
    assert "2026-06" in periods and "2026-07" in periods

    # ── US1: settle July → pending + report record (FR-001/FR-004/FR-005) ──
    settled = (await client.post("/api/v1/admin/performance/settlements/2026-07/settle", headers=_admin_headers("performance.settle"))).json()["data"]
    assert settled["status"] == "pending"
    reports = (await db_session.execute(select(Report))).scalars().all()
    assert len(reports) == 1
    assert reports[0].period == "2026-07" and reports[0].status == "pending"
    assert reports[0].generated_by == "User 1"

    # ── US2: report visible in 数据报表 list with pending status (SC-003) ──
    list_resp = (await client.get("/api/v1/reports", headers=_admin_headers("sharing_rules.read", "performance.settle"))).json()["data"]
    settlement_items = [i for i in list_resp["items"] if i.get("source") == "performance_settlement"]
    assert len(settlement_items) == 1
    assert settlement_items[0]["status"] == "pending"
    assert settlement_items[0]["period"] == "2026-07"

    # ── US2: report detail shows summary + details (SC-006) ──
    detail = (await client.get(f"/api/v1/reports/{reports[0].id}", headers=_admin_headers("sharing_rules.read", "performance.settle"))).json()["data"]
    assert detail["sections"]["performance"]["summary"]["核算人数"] == 1
    assert detail["sections"]["performance"]["details"][0]["提成金额(元)"] == "400.00"

    # ── US3: review → frozen + audit fields (SC-004/SC-008) ──
    reviewed = (await client.post("/api/v1/admin/performance/settlements/2026-07/review", headers=_admin_headers("performance.settle"))).json()["data"]
    assert reviewed["status"] == "reviewed"
    reports = (await db_session.execute(select(Report))).scalars().all()
    assert reports[0].status == "reviewed"

    # re-settle on frozen month rejected (FR-008)
    resp = await client.post("/api/v1/admin/performance/settlements/2026-07/settle", headers=_admin_headers("performance.settle"))
    assert resp.json()["code"] == 40000

    # ── US3: reject another month with reason → report status rejected (SC-005/SC-008) ──
    await client.post("/api/v1/admin/performance/settlements/2026-06/settle", headers=_admin_headers("performance.settle"))
    rejected = (await client.post("/api/v1/admin/performance/settlements/2026-06/reject", json={"reason": "金额核对有误"}, headers=_admin_headers("performance.settle"))).json()["data"]
    assert rejected["status"] == "rejected"
    assert rejected["rejectReason"] == "金额核对有误"

    # report record reflects rejected status
    report_jun = (await db_session.execute(select(Report).where(Report.period == "2026-06"))).scalars().first()
    assert report_jun.status == "rejected"

    # ── audit trail recorded (SC-008): reviewed fields + reject reason before recompute ──
    s_jul = (await db_session.execute(select(PerformanceSettlement).where(PerformanceSettlement.period == "2026-07"))).scalars().first()
    assert s_jul.reviewed_by == 1 and s_jul.reviewed_at is not None
    s_jun = (await db_session.execute(select(PerformanceSettlement).where(PerformanceSettlement.period == "2026-06"))).scalars().first()
    assert s_jun.reject_reason == "金额核对有误"

    # ── US3: recompute rejected → pending, report syncs (FR-009); reason cleared ──
    recomputed = (await client.post("/api/v1/admin/performance/settlements/2026-06/recompute", headers=_admin_headers("performance.settle"))).json()["data"]
    assert recomputed["status"] == "pending"
    report_jun = (await db_session.execute(select(Report).where(Report.period == "2026-06"))).scalars().first()
    assert report_jun.status == "pending"
    s_jun = (await db_session.execute(select(PerformanceSettlement).where(PerformanceSettlement.period == "2026-06"))).scalars().first()
    assert s_jun.reject_reason is None
