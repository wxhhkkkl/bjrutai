"""Unit tests for customer_admin_service (US1-US4 service layer)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog
from src.models.binding import BindingStatus, Customer
from src.models.customer_change_log import ChangeOperationType, CustomerChangeLog
from src.schemas.customer_admin import CustomerCreateRequest, CustomerTransferRequest, CustomerUpdateRequest
from src.services import customer_admin_service
from src.schemas.organization import OrgCreate
from src.services import organization_service
from tests.conftest import seed_promoter, seed_user


async def _seed_org_tree(db: AsyncSession) -> tuple[int, int]:
    root = await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))
    child = await organization_service.create_org(db, OrgCreate(name="华北区", orgType="region", parentId=root.id))
    return root.id, child.id


async def _seed_distributor(db: AsyncSession, org_id: int, phone: str = "13900000001") -> int:
    user_id = await seed_user(db, openid=f"openid_{phone}", user_type="distributor", name="推广员A", phone=phone)
    return await seed_promoter(db, user_id=user_id, node_id=org_id, qualification_status="approved")


async def _seed_customer(db: AsyncSession, distributor_id: int, status: str = "bound") -> int:
    c = Customer(
        distributor_id=distributor_id, name="张伟", phone="13800001234",
        phone_masked="138****1234", id_card_encrypted="110101199001011234",
        id_card_masked="110***********1234", medical_account_encrypted="23010011223344",
        binding_status=BindingStatus(status), version=1,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c.id


class FakeRutai:
    def __init__(self, match_status: str = "matched"):
        self._match_status = match_status

    async def bind_bj_user(self, **kwargs):
        if self._match_status == "matched":
            return {"match_status": "matched", "match_level": "exact", "hrb_user_id": "hrb_unit_1"}
        return {"match_status": "no_match", "match_level": "none"}


@pytest.mark.asyncio
async def test_list_customers_by_org_subtree(db_session: AsyncSession):
    root_id, child_id = await _seed_org_tree(db_session)
    d_child = await _seed_distributor(db_session, child_id)
    d_root = await _seed_distributor(db_session, root_id, phone="13900000002")
    await _seed_customer(db_session, d_child)
    await _seed_customer(db_session, d_root)

    data = await customer_admin_service.list_customers_by_org(db_session, root_id)
    assert data["total"] == 2

    data = await customer_admin_service.list_customers_by_org(db_session, child_id)
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_list_customers_filter_status(db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    d = await _seed_distributor(db_session, child_id)
    await _seed_customer(db_session, d, status="bound")
    await _seed_customer(db_session, d, status="pending")

    data = await customer_admin_service.list_customers_by_org(db_session, child_id, status="pending")
    assert data["total"] == 1
    assert data["items"][0]["bindingStatus"] == "pending"


@pytest.mark.asyncio
async def test_create_manual_customer_matched(db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    d = await _seed_distributor(db_session, child_id)

    req = CustomerCreateRequest(
        name="王芳", phone="13900005678", idCard="110101199505056789",
        medicalAccount="23010011223344", distributorId=str(d),
    )
    result = await customer_admin_service.create_manual_customer(db_session, req, operator_id=1, rutai_client=FakeRutai("matched"))
    assert result["bindingStatus"] == "bound"
    assert result["rutaiUserId"] == "hrb_unit_1"

    logs = (await db_session.execute(select(CustomerChangeLog))).scalars().all()
    assert len(logs) == 1 and logs[0].operation_type == ChangeOperationType.CREATED


@pytest.mark.asyncio
async def test_create_manual_customer_no_match_keeps_pending(db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    d = await _seed_distributor(db_session, child_id)

    req = CustomerCreateRequest(
        name="赵六", phone="13900001111", idCard="110101198803034567", distributorId=str(d),
    )
    result = await customer_admin_service.create_manual_customer(db_session, req, operator_id=1, rutai_client=FakeRutai("no_match"))
    assert result["bindingStatus"] == "pending"
    assert result["matchResult"]["matched"] is False


@pytest.mark.asyncio
async def test_create_manual_customer_duplicate_rejected(db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    d = await _seed_distributor(db_session, child_id)
    await _seed_customer(db_session, d)

    from src.core.exceptions import ConflictException

    req = CustomerCreateRequest(name="重复", phone="13900002222", idCard="110101199001011234", distributorId=str(d))
    with pytest.raises(ConflictException):
        await customer_admin_service.create_manual_customer(db_session, req, operator_id=1, rutai_client=FakeRutai())


@pytest.mark.asyncio
async def test_update_sensitive_requires_reason_and_audits(db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    d = await _seed_distributor(db_session, child_id)
    cid = await _seed_customer(db_session, d)

    from src.core.exceptions import BadRequestException

    req = CustomerUpdateRequest(phone="13800007777")
    with pytest.raises(BadRequestException):
        await customer_admin_service.update_customer_profile(db_session, cid, req, operator_id=1)

    req = CustomerUpdateRequest(phone="13800007777", changeReason="客户换号")
    result = await customer_admin_service.update_customer_profile(db_session, cid, req, operator_id=1)
    assert result["phoneMasked"] == "138****7777"

    audits = (await db_session.execute(select(AuditLog).where(AuditLog.action == "update_customer_sensitive"))).scalars().all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_transfer_records_change_log(db_session: AsyncSession):
    _, child_id = await _seed_org_tree(db_session)
    d_a = await _seed_distributor(db_session, child_id)
    d_b = await _seed_distributor(db_session, child_id, phone="13900000002")
    cid = await _seed_customer(db_session, d_a)

    req = CustomerTransferRequest(newDistributorId=str(d_b), reason="区域调整")
    result = await customer_admin_service.transfer_customer(db_session, cid, req, operator_id=1)
    assert result["newDistributorId"] == str(d_b)

    logs = await customer_admin_service.get_change_logs(db_session, cid)
    assert len(logs["items"]) == 1
    assert logs["items"][0]["operationType"] == "transfer"
    assert logs["items"][0]["reason"] == "区域调整"
