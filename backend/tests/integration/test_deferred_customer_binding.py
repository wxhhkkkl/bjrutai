"""Deferred QR attribution uses the logged-in identity and existing claim rules."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.models.binding import BindingRequest, BindingStatus, Customer
from src.models.consent import ConsentRecord
from src.models.distributor import Distributor, DistributorStatus
from src.models.organization import Organization, OrgStatus
from src.models.promotion import PromotionCode, PromotionCodeStatus
from src.models.user import ActivationStatus, User, UserType
from src.services.auth_service import _ensure_unassigned_customer
from tests.conftest import make_access_token


async def scenario(db):
    org = Organization(name="测试机构", level=1, status=OrgStatus.ACTIVE)
    staff = User(name="测试顾问", phone="13900139000", user_type=UserType.DISTRIBUTOR)
    patient = User(name="测试客户", phone="13800138000", user_type=UserType.PERSONAL)
    db.add_all([org, staff, patient])
    await db.flush()
    distributor = Distributor(user_id=staff.id, org_id=org.id, status=DistributorStatus.ACTIVE)
    db.add(distributor)
    await db.flush()
    code = PromotionCode(distributor_id=distributor.id, ref_token="deferred-test-token",
                         status=PromotionCodeStatus.AVAILABLE)
    db.add(code)
    await db.flush()
    return org, staff, distributor, patient, code


def headers(user):
    token = make_access_token(user_id=user.id, user_type=user.user_type.value)
    return {"Authorization": f"Bearer {token}"}


URL = "/api/v1/customer-binding-codes/deferred-test-token/claim-session"


@pytest.mark.asyncio
async def test_deferred_claim_links_login_customer_and_is_idempotent(client, db_session):
    _, _, distributor, patient, code = await scenario(db_session)
    await _ensure_unassigned_customer(db_session, patient)
    original = (await db_session.execute(select(Customer))).scalars().one()
    assert original.distributor_id is None
    # Never perform another WeChat exchange or trust a phone/customer from the body.
    with patch("src.services.auth_service.get_wechat_client", side_effect=AssertionError("one-use code reused")):
        for _ in range(2):
            response = await client.post(URL, headers=headers(patient), json={
                "consentConfirmed": True, "phone": "13700137000", "userId": "999",
            })
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert data["customerId"] == str(original.id)
            assert data["bindingStatus"] == "bound"
            assert data["rutaiMatchStatus"] == "pending_match"
            assert "session" not in data
    assert original.distributor_id == distributor.id
    assert original.user_id == patient.id
    assert original.phone == patient.phone
    assert original.binding_status == BindingStatus.BOUND
    assert len((await db_session.execute(select(Customer))).scalars().all()) == 1
    requests = (await db_session.execute(select(BindingRequest))).scalars().all()
    consents = (await db_session.execute(select(ConsentRecord))).scalars().all()
    assert len(requests) == len(consents) == 1
    assert requests[0].ref_token == code.ref_token
    assert consents[0].confirmed is True
    assert consents[0].scopes["customer_attribution"] is True
    assert code.bind_count == 1


@pytest.mark.asyncio
async def test_deferred_claim_creates_first_customer(client, db_session):
    _, _, distributor, patient, code = await scenario(db_session)
    response = await client.post(URL, headers=headers(patient), json={"consentConfirmed": True})
    assert response.status_code == 200
    customer = (await db_session.execute(select(Customer))).scalars().one()
    assert customer.distributor_id == distributor.id
    assert customer.user_id == patient.id
    assert code.lead_count == code.bind_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing_auth", "no_consent", "missing_code", "expired", "revoked", "staff_disabled", "org_disabled", "patient_disabled", "no_phone", "staff_account", "other_owner", "admin"])
async def test_deferred_claim_rejects_invalid_identity_code_or_owner(client, db_session, state):
    org, staff, distributor, patient, code = await scenario(db_session)
    expected = 400
    target = patient
    url = URL
    if state == "missing_auth": expected = 401
    if state == "missing_code":
        url = URL.replace("deferred-test-token", "unknown-token")
        expected = 404
    if state == "expired": code.expires_at = datetime.utcnow() - timedelta(seconds=1)
    if state == "revoked": code.status = PromotionCodeStatus.DISABLED
    if state == "staff_disabled": distributor.status = DistributorStatus.DISABLED
    if state == "org_disabled": org.status = OrgStatus.DISABLED
    if state == "patient_disabled":
        patient.activation_status = ActivationStatus.DISABLED
        expected = 403
    if state == "no_phone": patient.phone = None
    if state == "staff_account":
        target = staff
        expected = 409
    if state == "admin": expected = 403
    existing = None
    if state == "other_owner":
        other_staff = User(name="其他顾问", phone="13900139001", user_type=UserType.DISTRIBUTOR)
        db_session.add(other_staff)
        await db_session.flush()
        other = Distributor(user_id=other_staff.id, org_id=org.id, status=DistributorStatus.ACTIVE)
        db_session.add(other)
        await db_session.flush()
        existing = Customer(user_id=patient.id, distributor_id=other.id, phone=patient.phone,
                            phone_normalized=patient.phone, binding_status=BindingStatus.BOUND)
        db_session.add(existing)
        expected = 409
    await db_session.flush()
    auth = {} if state == "missing_auth" else headers(target)
    if state == "admin":
        auth = {"Authorization": f"Bearer {make_access_token(user_id=patient.id, user_type='admin')}"}
    response = await client.post(url, headers=auth, json={"consentConfirmed": state != "no_consent"})
    assert response.status_code == expected, response.text
    if state == "staff_account": assert response.json()["code"] == 40024
    if state == "other_owner":
        assert response.json()["code"] == 40023
        assert existing.distributor_id != distributor.id
    assert code.bind_count == 0
    assert (await db_session.execute(select(BindingRequest))).scalars().all() == []
