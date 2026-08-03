"""Contract tests for admin customer management endpoints (US1-US4).

Verifies the unified response envelope and documented behaviors from
contracts/customers.md against the real SQLite test DB via the client fixture.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog
from src.models.binding import BindingRequest, BindingStatus, Customer
from src.models.customer_change_log import ChangeOperationType, CustomerChangeLog
from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import make_access_token, seed_promoter, seed_user


def _admin_headers(*perms: str) -> dict:
    token = make_access_token(user_id=1, user_type="admin", permissions=list(perms))
    return {"Authorization": f"Bearer {token}"}


CUST_RW = _admin_headers("customers.read", "customers.write")
CUST_R = _admin_headers("customers.read")
NO_PERM = _admin_headers("unrelated.read")


def _assert_envelope(resp):
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "success"
    assert "requestId" in body and "serverTime" in body
    return body["data"]


def _status_code(resp):
    return resp.json().get("code")


async def _seed_org_tree(db: AsyncSession) -> tuple[int, int]:
    root = await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))
    child = await organization_service.create_org(db, OrgCreate(name="华北区", orgType="region", parentId=root.id))
    return root.id, child.id


async def _seed_distributor(db: AsyncSession, org_id: int, phone: str = "13900000001") -> int:
    user_id = await seed_user(db, openid=f"openid_{phone}", user_type="distributor", name="推广员A", phone=phone)
    # seed_promoter with qualification_status="approved" also seeds an approved
    # org qualification so the distributor's org is business-ready (selectable).
    return await seed_promoter(db, user_id=user_id, node_id=org_id, qualification_status="approved")


async def _seed_customer(
    db: AsyncSession, distributor_id: int, name="张伟", phone="13800001234",
    id_card="110101199001011234", status: str = "bound", medical="23010000112233",
) -> int:
    c = Customer(
        distributor_id=distributor_id,
        name=name,
        phone=phone,
        phone_masked=phone[:3] + "****" + phone[-4:],
        id_card_encrypted=id_card,
        id_card_masked=id_card[:3] + "***********" + id_card[-4:],
        medical_account_encrypted=medical,
        binding_status=BindingStatus(status),
        version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


# ──────────────────────────────────────────────────────────────────
# US1: GET /admin/customers — org-scoped list
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_customers_org_subtree(client: AsyncClient, db_session: AsyncSession):
    root_id, child_id = await _seed_org_tree(db_session)
    dist_child = await _seed_distributor(db_session, child_id)
    dist_root = await _seed_distributor(db_session, root_id, phone="13900000002")
    await _seed_customer(db_session, dist_child)
    await _seed_customer(db_session, dist_root, name="李雷", phone="13800009999")

    # Selecting the root returns both (subtree); selecting child returns only child's.
    data = _assert_envelope(await client.get("/api/v1/admin/customers", params={"orgId": root_id}, headers=CUST_R))
    assert data["total"] == 2
    names = {i["name"] for i in data["items"]}
    assert names == {"张伟", "李雷"}
    assert all(i["phoneMasked"].endswith("1234") or i["phoneMasked"].endswith("9999") for i in data["items"])

    data = _assert_envelope(await client.get("/api/v1/admin/customers", params={"orgId": child_id}, headers=CUST_R))
    assert data["total"] == 1
    assert data["items"][0]["name"] == "张伟"
    assert data["items"][0]["orgName"] == "华北区"


@pytest.mark.asyncio
async def test_list_customers_filter_and_pagination(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)
    await _seed_customer(db_session, dist, status="bound")
    await _seed_customer(db_session, dist, name="王芳", status="pending")

    data = _assert_envelope(await client.get(
        "/api/v1/admin/customers", params={"orgId": child_id, "status": "pending"}, headers=CUST_R
    ))
    assert data["total"] == 1
    assert data["items"][0]["bindingStatus"] == "pending"

    data = _assert_envelope(await client.get(
        "/api/v1/admin/customers", params={"orgId": child_id, "keyword": "王芳"}, headers=CUST_R
    ))
    assert data["total"] == 1

    data = _assert_envelope(await client.get(
        "/api/v1/admin/customers", params={"orgId": child_id, "pageSize": 1, "page": 1}, headers=CUST_R
    ))
    assert data["hasMore"] is True


@pytest.mark.asyncio
async def test_list_customers_requires_read_permission(client: AsyncClient, db_session: AsyncSession):
    root_id, _ = await _seed_org_tree(db_session)
    resp = await client.get("/api/v1/admin/customers", params={"orgId": root_id}, headers=NO_PERM)
    assert _status_code(resp) == 40300


# ──────────────────────────────────────────────────────────────────
# US2: POST /admin/customers — manual creation + hospital match
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_customer_matched(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)

    from unittest.mock import AsyncMock, patch

    async def fake_match(**kwargs):
        return {"match_status": "matched", "match_level": "exact", "hrb_user_id": "hrb_test_1"}

    with patch("src.integrations.rutai_client.get_rutai_client") as mock_factory:
        mock_factory.return_value = AsyncMock(bind_bj_user=fake_match)
        resp = await client.post(
            "/api/v1/admin/customers",
            json={"name": "王芳", "phone": "13900005678", "idCard": "110101199505056789",
                  "medicalAccount": "23010011223344", "distributorId": str(dist)},
            headers=CUST_RW,
        )
    assert resp.status_code == 200
    data = _assert_envelope(resp)
    assert data["bindingStatus"] == "bound"
    assert data["rutaiUserId"] == "hrb_test_1"
    assert data["matchResult"]["matched"] is True
    assert data["idCardMasked"].startswith("110")

    # A 'created' change log + a manual binding request should exist.
    logs = (await db_session.execute(select(CustomerChangeLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].operation_type == ChangeOperationType.CREATED
    assert logs[0].new_distributor_id == dist
    reqs = (await db_session.execute(select(BindingRequest))).scalars().all()
    assert len(reqs) == 1


@pytest.mark.asyncio
async def test_create_customer_match_failure_keeps_profile(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)

    from unittest.mock import AsyncMock, patch

    async def fake_match(**kwargs):
        return {"match_status": "no_match", "match_level": "none"}

    with patch("src.integrations.rutai_client.get_rutai_client") as mock_factory:
        mock_factory.return_value = AsyncMock(bind_bj_user=fake_match)
        resp = await client.post(
            "/api/v1/admin/customers",
            json={"name": "赵六", "phone": "13900001111", "idCard": "110101198803034567",
                  "distributorId": str(dist)},
            headers=CUST_RW,
        )
    data = _assert_envelope(resp)
    assert data["bindingStatus"] == "pending"
    assert data["matchResult"]["matched"] is False
    assert data["matchResult"]["failureReason"]


@pytest.mark.asyncio
async def test_create_customer_duplicate_id_card_rejected(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)
    await _seed_customer(db_session, dist)

    resp = await client.post(
        "/api/v1/admin/customers",
        json={"name": "重复", "phone": "13900002222", "idCard": "110101199001011234",
              "distributorId": str(dist)},
        headers=CUST_RW,
    )
    assert _status_code(resp) == 40900


@pytest.mark.asyncio
async def test_create_customer_missing_fields_rejected(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)

    resp = await client.post(
        "/api/v1/admin/customers",
        json={"name": "缺身份证", "phone": "13900003333", "distributorId": str(dist)},
        headers=CUST_RW,
    )
    assert resp.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_create_customer_requires_write_permission(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)
    resp = await client.post(
        "/api/v1/admin/customers",
        json={"name": "王芳", "phone": "13900005678", "idCard": "110101199505056789",
              "distributorId": str(dist)},
        headers=NO_PERM,
    )
    assert _status_code(resp) == 40300


# ──────────────────────────────────────────────────────────────────
# US3: GET / PATCH /admin/customers/{id}
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_customer_detail_masked(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)
    cid = await _seed_customer(db_session, dist, medical="23010011223344")

    data = _assert_envelope(await client.get(f"/api/v1/admin/customers/{cid}", headers=CUST_R))
    assert data["idCardMasked"].startswith("110")
    assert "1990" not in data["idCardMasked"]  # masked — no plaintext segment
    assert data["medicalAccountMasked"].startswith("2301")
    assert data["promoterName"] == "推广员A"
    assert data["orgName"] == "华北区"


@pytest.mark.asyncio
async def test_update_sensitive_field_requires_change_reason(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)
    cid = await _seed_customer(db_session, dist)

    resp = await client.patch(
        f"/api/v1/admin/customers/{cid}",
        json={"phone": "13800007777"},
        headers=CUST_RW,
    )
    assert _status_code(resp) == 40000

    resp = await client.patch(
        f"/api/v1/admin/customers/{cid}",
        json={"phone": "13800007777", "changeReason": "客户换号"},
        headers=CUST_RW,
    )
    data = _assert_envelope(resp)
    assert data["phoneMasked"] == "138****7777"

    audits = (await db_session.execute(select(AuditLog).where(AuditLog.action == "update_customer_sensitive"))).scalars().all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_patch_requires_write_permission(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)
    cid = await _seed_customer(db_session, dist)

    resp = await client.patch(f"/api/v1/admin/customers/{cid}", json={"name": "改名"}, headers=NO_PERM)
    assert _status_code(resp) == 40300


# ──────────────────────────────────────────────────────────────────
# US4: POST transfer + GET change-logs
# ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_transfer_promoter_and_change_logs(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist_a = await _seed_distributor(db_session, child_id, phone="13900000001")
    dist_b = await _seed_distributor(db_session, child_id, phone="13900000002")
    cid = await _seed_customer(db_session, dist_a)

    resp = await client.post(
        f"/api/v1/admin/customers/{cid}/transfer",
        json={"newDistributorId": str(dist_b), "reason": "客户区域调整"},
        headers=CUST_RW,
    )
    data = _assert_envelope(resp)
    assert data["previousDistributorId"] == str(dist_a)
    assert data["newDistributorId"] == str(dist_b)

    logs = _assert_envelope(await client.get(f"/api/v1/admin/customers/{cid}/change-logs", headers=CUST_R))
    assert len(logs["items"]) == 1
    assert logs["items"][0]["operationType"] == "transfer"
    assert logs["items"][0]["reason"] == "客户区域调整"
    assert logs["items"][0]["newPromoterName"] == "推广员A"


@pytest.mark.asyncio
async def test_transfer_to_same_promoter_rejected(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist = await _seed_distributor(db_session, child_id)
    cid = await _seed_customer(db_session, dist)

    resp = await client.post(
        f"/api/v1/admin/customers/{cid}/transfer",
        json={"newDistributorId": str(dist), "reason": "不变"},
        headers=CUST_RW,
    )
    assert _status_code(resp) == 40000


@pytest.mark.asyncio
async def test_transfer_requires_write_permission(client: AsyncClient, db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    dist_a = await _seed_distributor(db_session, child_id)
    dist_b = await _seed_distributor(db_session, child_id, phone="13900000009")
    cid = await _seed_customer(db_session, dist_a)

    resp = await client.post(
        f"/api/v1/admin/customers/{cid}/transfer",
        json={"newDistributorId": str(dist_b), "reason": "调整"},
        headers=NO_PERM,
    )
    assert _status_code(resp) == 40300
