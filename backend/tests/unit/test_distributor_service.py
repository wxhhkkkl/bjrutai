"""Unit tests for distributor_service + distributor auth (US3/US4)."""

from unittest.mock import patch

import pytest

from src.core.exceptions import ConflictException, NotFoundException
from src.schemas.distributor import DistributorCreate, DistributorRoleUpdate, DistributorUpdate, ResetPassword
from src.schemas.organization import OrgCreate
from src.services import distributor_service, organization_service
from src.services.auth_service import get_auth_service


async def _seed_org_and_distributor(db, phone="13800000001"):
    org = await organization_service.create_org(db, OrgCreate(name="总部", orgType="headquarters"))
    d = await distributor_service.create_distributor(
        db, org.id,
        DistributorCreate(name="张三", phone=phone, initialPassword="password123"),
    )
    return org.id, int(d["distributorId"])


@pytest.mark.asyncio
async def test_create_distributor(db_session):
    org_id, did = await _seed_org_and_distributor(db_session)
    assert did > 0
    items = await distributor_service.list_distributors(db_session, org_id)
    assert items["total"] == 1
    assert items["items"][0]["orgRole"] == "member"


@pytest.mark.asyncio
async def test_create_duplicate_phone_rejected(db_session):
    await _seed_org_and_distributor(db_session)
    org = await organization_service.create_org(db_session, OrgCreate(name="另一组织", orgType="region"))
    with pytest.raises(ConflictException):
        await distributor_service.create_distributor(
            db_session, org.id,
            DistributorCreate(name="李四", phone="13800000001", initialPassword="password123"),
        )


@pytest.mark.asyncio
async def test_update_org_and_disable(db_session):
    org_id, did = await _seed_org_and_distributor(db_session)
    org2 = await organization_service.create_org(db_session, OrgCreate(name="B区", orgType="region"))
    updated = await distributor_service.update_distributor(
        db_session, did, DistributorUpdate(orgId=org2.id, status="disabled")
    )
    assert updated["orgId"] == str(org2.id)
    assert updated["status"] == "disabled"


@pytest.mark.asyncio
async def test_reset_password(db_session):
    _, did = await _seed_org_and_distributor(db_session)
    await distributor_service.reset_password(db_session, did, ResetPassword(newPassword="newpass1234"))
    # login with new password succeeds
    result = await get_auth_service().distributor_login(db_session, "13800000001", "newpass1234")
    assert result["accessToken"]


@pytest.mark.asyncio
async def test_set_role_admin(db_session):
    org_id, did = await _seed_org_and_distributor(db_session)
    updated = await distributor_service.set_role(
        db_session, did, DistributorRoleUpdate(orgRole="admin")
    )
    assert updated["orgRole"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(db_session):
    await _seed_org_and_distributor(db_session)
    from src.core.exceptions import AppException

    with pytest.raises(AppException):
        await get_auth_service().distributor_login(db_session, "13800000001", "wrongpassword")


@pytest.mark.asyncio
async def test_bind_wechat(db_session, mock_wechat_client):
    _, did = await _seed_org_and_distributor(db_session)
    mock_wechat_client.set_valid_code("wx_code_1", openid="o_dist_001")

    with patch("src.services.auth_service.get_wechat_client", return_value=mock_wechat_client):
        result = await get_auth_service().bind_wechat(db_session, 1, "wx_code_1")

    assert result["bound"] is True
    assert result["openId"] == "o_dist_001"


@pytest.mark.asyncio
async def test_missing_distributor_not_found(db_session):
    with pytest.raises(NotFoundException):
        await distributor_service.get_distributor_or_404(db_session, 99999)
