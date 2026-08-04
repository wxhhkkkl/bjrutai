"""Contract tests for admin performance rules endpoints (US1-US3 + calc).

Verifies the unified response envelope and documented behaviors from
contracts/performance-rules.md against the SQLite test DB via the client fixture.
"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.commission_result import CommissionResult
from src.models.performance_rule import PerformanceRuleChangeLog
from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token, seed_user


def _admin_headers(*perms: str) -> dict:
    token = make_access_token(user_id=1, user_type="admin", permissions=list(perms))
    return {"Authorization": f"Bearer {token}"}


R_RW = _admin_headers("sharing_rules.read", "sharing_rules.write")
R_R = _admin_headers("sharing_rules.read")
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
    """Build tier list from (minCent, maxCent, ratio) tuples; last maxCent null => open-ended."""
    out = []
    for i, (mn, mx, ratio) in enumerate(pairs):
        out.append({"minCent": mn, "maxCent": mx, "ratio": ratio})
    return out


# ──────────────────────────────────────────────────────────────────
# US1: GET rules for org
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_rules_unconfigured(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    data = _assert_envelope(await client.get(f"/api/v1/admin/orgs/{org_id}/performance-rules", headers=R_R))
    assert data["intraOrg"] is None
    assert data["orgManagement"] is None
    assert data["summary"] == {"intraOrgConfigured": False, "orgManagementConfigured": False}


@pytest.mark.asyncio
async def test_get_rules_requires_read_permission(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    resp = await client.get(f"/api/v1/admin/orgs/{org_id}/performance-rules", headers=NO_PERM)
    assert _status_code(resp) == 40300


# ──────────────────────────────────────────────────────────────────
# US2: PUT intra_org
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_save_intra_org_create_and_update(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    resp = await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, 1000000, 0.05), (1000000, None, 0.08))},
        headers=R_RW,
    )
    data = _assert_envelope(resp)
    assert data["ruleType"] == "intra_org"
    assert data["version"] == 1
    assert len(data["tiers"]) == 2

    resp2 = await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, None, 0.10))},
        headers=R_RW,
    )
    assert _assert_envelope(resp2)["version"] == 2

    logs = (await db_session.execute(select(PerformanceRuleChangeLog))).scalars().all()
    assert len(logs) == 2  # created + update, both logged (FR-007)


@pytest.mark.asyncio
async def test_save_rule_invalid_tiers_rejected(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    # First tier minCent != 0
    resp = await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((1000000, None, 0.05))},
        headers=R_RW,
    )
    assert _status_code(resp) == 40000

    # Overlapping tiers
    resp2 = await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, 500000, 0.05), (400000, None, 0.08))},
        headers=R_RW,
    )
    assert _status_code(resp2) == 40000

    # Gapped tiers (500000~700000 uncovered) -> rejected, any amount must be covered
    resp3 = await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, 500000, 0.05), (700000, None, 0.08))},
        headers=R_RW,
    )
    assert _status_code(resp3) == 40000


@pytest.mark.asyncio
async def test_save_rule_requires_write_permission(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    resp = await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, None, 0.05))},
        headers=NO_PERM,
    )
    assert _status_code(resp) == 40300


# ──────────────────────────────────────────────────────────────────
# US3: PUT org_management
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_save_org_management_rule(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    resp = await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/org_management",
        json={"tiers": _tiers((0, None, 0.08))},
        headers=R_RW,
    )
    data = _assert_envelope(resp)
    assert data["ruleType"] == "org_management"

    got = _assert_envelope(await client.get(f"/api/v1/admin/orgs/{org_id}/performance-rules", headers=R_R))
    assert got["orgManagement"] is not None
    assert got["summary"]["orgManagementConfigured"] is True


# ──────────────────────────────────────────────────────────────────
# 计算引擎: preview + commission-results
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_preview_member_commission_and_unconfigured(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, paid_cent=800000, txn_id="txn_1")
    await _seed_bill(db_session, cid, paid_cent=200000, txn_id="txn_2")

    await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, 1000000, 0.05), (1000000, None, 0.08))},
        headers=R_RW,
    )

    preview = _assert_envelope(await client.get(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/preview", params={"period": "2026-07"}, headers=R_R
    ))
    assert len(preview["intraOrg"]) == 1
    item = preview["intraOrg"][0]
    assert item["baseCent"] == 1000000  # 800000 + 200000
    assert item["ratio"] == 0.08
    assert item["commissionCent"] == 80000
    assert preview["unconfigured"] == ["org_management"]

    # Preview must NOT persist.
    results = (await db_session.execute(select(CommissionResult))).scalars().all()
    assert len(results) == 0


@pytest.mark.asyncio
async def test_preview_excludes_refunded_bills(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    dist = await _seed_distributor(db_session, org_id)
    cid = await _seed_customer(db_session, dist)
    await _seed_bill(db_session, cid, paid_cent=1000000, txn_id="txn_ok")
    await _seed_bill(db_session, cid, paid_cent=500000, txn_id="txn_refund", status=TransactionStatus.REFUNDED)

    await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, None, 0.05))},
        headers=R_RW,
    )
    preview = _assert_envelope(await client.get(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/preview", params={"period": "2026-07"}, headers=R_R
    ))
    assert preview["intraOrg"][0]["baseCent"] == 1000000  # refunded 500000 excluded


@pytest.mark.asyncio
async def test_apply_rule_to_descendants(client: AsyncClient, db_session: AsyncSession):
    root = await organization_service.create_org(db_session, OrgCreate(name="总部", orgType="headquarters"))
    child = await organization_service.create_org(db_session, OrgCreate(name="华北区", orgType="region", parentId=root.id))
    grand = await organization_service.create_org(db_session, OrgCreate(name="石家庄", orgType="region", parentId=child.id))

    await client.put(
        f"/api/v1/admin/orgs/{root.id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, 500000, 0.05), (500000, None, 0.08))},
        headers=R_RW,
    )

    resp = await client.post(
        f"/api/v1/admin/orgs/{root.id}/performance-rules/intra_org/apply-to-descendants",
        headers=R_RW,
    )
    data = _assert_envelope(resp)
    assert data["applied"] == 2  # child + grand
    assert set(data["orgIds"]) == {str(child.id), str(grand.id)}

    child_rules = _assert_envelope(await client.get(f"/api/v1/admin/orgs/{child.id}/performance-rules", headers=R_R))
    assert child_rules["intraOrg"]["tiers"][0]["ratio"] == 0.05
    grand_rules = _assert_envelope(await client.get(f"/api/v1/admin/orgs/{grand.id}/performance-rules", headers=R_R))
    assert grand_rules["intraOrg"] is not None


@pytest.mark.asyncio
async def test_apply_rule_requires_source_config(client: AsyncClient, db_session: AsyncSession):
    org_id = await _seed_org(db_session)
    resp = await client.post(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/org_management/apply-to-descendants",
        headers=R_RW,
    )
    assert _status_code(resp) == 40000


@pytest.mark.asyncio
async def test_apply_org_management_rule_to_descendants(client: AsyncClient, db_session: AsyncSession):
    root = await organization_service.create_org(db_session, OrgCreate(name="总部", orgType="headquarters"))
    child = await organization_service.create_org(db_session, OrgCreate(name="华北区", orgType="region", parentId=root.id))

    await client.put(
        f"/api/v1/admin/orgs/{root.id}/performance-rules/org_management",
        json={"tiers": _tiers((0, 1000000, 0.08), (1000000, None, 0.12))},
        headers=R_RW,
    )

    resp = await client.post(
        f"/api/v1/admin/orgs/{root.id}/performance-rules/org_management/apply-to-descendants",
        headers=R_RW,
    )
    data = _assert_envelope(resp)
    assert data["applied"] == 1
    assert data["orgIds"] == [str(child.id)]

    child_rules = _assert_envelope(await client.get(f"/api/v1/admin/orgs/{child.id}/performance-rules", headers=R_R))
    assert child_rules["orgManagement"] is not None
    assert child_rules["orgManagement"]["tiers"][1]["ratio"] == 0.12


@pytest.mark.asyncio
async def test_history_records_operation_and_account(client: AsyncClient, db_session: AsyncSession):
    from src.core.security import get_password_hash
    from src.models.user import AdminAccount

    db_session.add(AdminAccount(id=1, username="admin", password_hash=get_password_hash("x"), status="active"))
    await db_session.flush()

    org_id = await _seed_org(db_session)
    await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, None, 0.05))}, headers=R_RW,
    )
    await client.put(
        f"/api/v1/admin/orgs/{org_id}/performance-rules/intra_org",
        json={"tiers": _tiers((0, None, 0.08))}, headers=R_RW,
    )

    data = _assert_envelope(await client.get(f"/api/v1/admin/orgs/{org_id}/performance-rules/history", headers=R_R))
    assert len(data["items"]) == 2
    assert data["items"][0]["operationType"] == "update"
    assert data["items"][1]["operationType"] == "create"
    assert data["items"][0]["changedBy"] == "admin"
    assert data["items"][0]["oldValue"]["tiers"][0]["ratio"] == 0.05
    assert data["items"][0]["newValue"]["tiers"][0]["ratio"] == 0.08
