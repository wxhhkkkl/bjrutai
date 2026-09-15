"""Integration coverage for spec 019 role, customer and staff-invite flows."""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.models.binding import BindingRequest, BindingStatus, Customer
from src.models.distributor import Distributor, DistributorStatus, OrgRole
from src.models.organization import Organization, OrgStatus
from src.models.promotion import PromotionCode, PromotionCodeStatus
from src.models.user import User, UserType
from src.services.auth_service import get_auth_service
from src.services.binding_service import BindingService
from tests.conftest import make_access_token, seed_org_qualification


class PendingRutaiClient:
    async def bind_bj_user(self, **kwargs):
        return {
            "match_status": "pending",
            "match_level": "none",
            "hrb_user_id": None,
        }


class FullPhoneWechatClient:
    async def get_phone_number(self, code: str) -> str:
        assert code == "valid-phone-code"
        return "13800138000"


async def _staff(db, *, role=OrgRole.MEMBER, phone="13900139000"):
    org = Organization(name="测试组织", level=1, status=OrgStatus.ACTIVE)
    db.add(org)
    await db.flush()
    user = User(
        name="测试人员",
        phone=phone,
        phone_masked="139****9000",
        user_type=UserType.DISTRIBUTOR,
    )
    db.add(user)
    await db.flush()
    distributor = Distributor(
        user_id=user.id,
        org_id=org.id,
        org_role=role,
        status=DistributorStatus.ACTIVE,
    )
    db.add(distributor)
    await db.flush()
    await seed_org_qualification(db, org_id=org.id, status="approved")
    return org, user, distributor


@pytest.mark.asyncio
async def test_new_wechat_login_stays_outside_organization(db_session, mock_wechat_client):
    mock_wechat_client.set_valid_code("new-person", openid="openid-person")
    with patch("src.services.auth_service.get_wechat_client", return_value=mock_wechat_client):
        result = await get_auth_service().wechat_login(db_session, "new-person")

    assert result["user"]["role"] == "personal"
    assert result["hasBusinessMembership"] is False
    assert "distributor" not in result
    distributors = (await db_session.execute(select(Distributor))).scalars().all()
    assert distributors == []


@pytest.mark.asyncio
async def test_personal_session_reports_no_business_membership(db_session):
    user = User(name="个人账号", user_type=UserType.PERSONAL)
    db_session.add(user)
    await db_session.flush()

    result = await get_auth_service().get_session(db_session, user.id, "personal", 1893456000)

    assert result["user"]["role"] == "personal"
    assert result["hasBusinessMembership"] is False
    assert result["membershipStatus"] == "none"


@pytest.mark.asyncio
async def test_personal_account_cannot_access_customer_api(client, db_session):
    user = User(name="个人账号", user_type=UserType.PERSONAL)
    db_session.add(user)
    await db_session.flush()
    token = make_access_token(user_id=user.id, user_type="personal")

    response = await client.get(
        "/api/v1/customers",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "成为业务员后才能使用客户和消费功能"

    performance_response = await client.get(
        "/api/v1/my/performance/commission",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert performance_response.status_code == 403


@pytest.mark.asyncio
async def test_staff_preentry_creates_pending_customer_and_links_request(db_session):
    _org, user, distributor = await _staff(db_session)
    service = BindingService(rutai_client=PendingRutaiClient())

    result = await service.submit_binding_request(
        db_session,
        data={
            "promoterId": str(user.id),
            "customerInfo": {"phone": "138 0013 8000"},
            "sourceType": "manual",
        },
        submitted_by=user.id,
        idempotency_key="preentry-1",
    )

    customer = (
        await db_session.execute(select(Customer).where(Customer.phone_normalized == "13800138000"))
    ).scalars().one()
    request = await db_session.get(BindingRequest, int(result["requestId"]))
    assert customer.distributor_id == distributor.id
    assert customer.name is None
    assert customer.binding_status == BindingStatus.PENDING
    assert request.customer_id == customer.id


@pytest.mark.asyncio
async def test_staff_preentry_never_transfers_same_phone_to_another_staff(db_session):
    _org_a, user_a, distributor_a = await _staff(db_session, phone="13900139001")
    _org_b, user_b, _distributor_b = await _staff(db_session, phone="13900139002")
    existing = Customer(
        distributor_id=distributor_a.id,
        name="患者甲",
        phone="13800138000",
        phone_normalized="13800138000",
        phone_masked="138****8000",
        binding_status=BindingStatus.PENDING,
    )
    db_session.add(existing)
    await db_session.flush()

    service = BindingService(rutai_client=PendingRutaiClient())
    with pytest.raises(Exception) as error:
        await service.submit_binding_request(
            db_session,
            data={
                "promoterId": str(user_b.id),
                "customerInfo": {"phone": "13800138000"},
                "sourceType": "manual",
            },
            submitted_by=user_b.id,
            idempotency_key="cross-owner",
        )

    assert "其他业务员" in str(error.value)


@pytest.mark.asyncio
async def test_patient_claim_merges_preentered_customer(client, db_session):
    _org, user, distributor = await _staff(db_session)
    patient_user = User(
        name="患者个人账号",
        phone="13800138000",
        phone_masked="138****8000",
        user_type=UserType.PERSONAL,
    )
    code = PromotionCode(
        distributor_id=distributor.id,
        ref_token="patient-token-123456",
        status=PromotionCodeStatus.AVAILABLE,
        share_path="/pages/patient-binding/index?refToken=patient-token-123456",
    )
    customer = Customer(
        distributor_id=distributor.id,
        name="业务员预录姓名",
        phone="13800138000",
        phone_normalized="13800138000",
        phone_masked="138****8000",
        binding_status=BindingStatus.PENDING,
    )
    db_session.add_all([patient_user, code, customer])
    await db_session.flush()

    with patch(
        "src.services.customer_binding_code_service.get_wechat_client",
        return_value=FullPhoneWechatClient(),
    ):
        response = await client.post(
            "/api/v1/customer-binding-codes/patient-token-123456/claim",
            json={
                "phoneCode": "valid-phone-code",
                "name": "患者本人姓名",
                "consentConfirmed": True,
            },
        )
        repeated = await client.post(
            "/api/v1/customer-binding-codes/patient-token-123456/claim",
            json={
                "phoneCode": "valid-phone-code",
                "name": "患者本人姓名",
                "consentConfirmed": True,
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["customerId"] == str(customer.id)
    assert data["distributorName"] == user.name
    customers = (
        await db_session.execute(select(Customer).where(Customer.phone_normalized == "13800138000"))
    ).scalars().all()
    assert len(customers) == 1
    assert customers[0].binding_status == BindingStatus.BOUND
    assert customers[0].user_id == patient_user.id
    assert repeated.status_code == 200
    assert repeated.json()["data"]["customerId"] == str(customer.id)
    await db_session.refresh(code)
    assert code.bind_count == 1


@pytest.mark.asyncio
async def test_only_org_admin_can_create_staff_invite_and_person_can_join(client, db_session):
    org, admin_user, _admin_distributor = await _staff(db_session, role=OrgRole.ADMIN)
    _member_org, member_user, _member_distributor = await _staff(
        db_session, phone="13900139003"
    )
    admin_token = make_access_token(user_id=admin_user.id, user_type="distributor")
    member_token = make_access_token(user_id=member_user.id, user_type="distributor")

    denied = await client.get(
        "/api/v1/staff-invite-code",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert denied.status_code == 403

    created = await client.get(
        "/api/v1/staff-invite-code",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert created.status_code == 200
    invite = created.json()["data"]
    assert invite["orgId"] == str(org.id)

    with patch(
        "src.services.staff_invite_service.get_wechat_client",
        return_value=FullPhoneWechatClient(),
    ):
        joined = await client.post(
            f"/api/v1/staff-invite-codes/{invite['refToken']}/join",
            json={
                "phoneCode": "valid-phone-code",
                "name": "新业务员",
                "consentConfirmed": True,
            },
        )

    assert joined.status_code == 200
    joined_data = joined.json()["data"]
    assert joined_data["orgId"] == str(org.id)
    assert joined_data["orgRole"] == "member"
