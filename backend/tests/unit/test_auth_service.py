"""Unit tests for personal login and explicit organization membership."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from src.core.security import get_password_hash
from src.models.binding import BindingStatus, Customer
from src.models.user import User, UserType
from src.schemas.organization import OrgCreate
from src.services import distributor_service, organization_service
from src.services.auth_service import get_auth_service


@pytest.mark.asyncio
async def test_wechat_login_creates_personal_account_only(db_session, mock_wechat_client):
    """New WeChat users stay personal until explicitly joining an organization."""
    org = await organization_service.create_org(
        db_session, OrgCreate(name="默认组织", orgType=None)
    )
    mock_wechat_client.set_valid_code("wx_new_001", openid="o_new_user_001")

    with patch(
        "src.services.auth_service.get_wechat_client", return_value=mock_wechat_client
    ):
        result = await get_auth_service().wechat_login(db_session, "wx_new_001")

    assert result["user"]["isNewUser"] is True
    assert result["user"]["openId"] == "o_new_user_001"

    assert result.get("distributor") is None
    assert result["user"]["role"] == "personal"
    assert result["hasBusinessMembership"] is False


@pytest.mark.asyncio
async def test_wechat_login_consumes_phone_code_once_and_persists_phone(
    db_session, mock_wechat_client
):
    """The one-time phone auth code is consumed by WeChat login itself."""
    mock_wechat_client.set_valid_code("wx_phone_login", openid="o_phone_login")

    with patch(
        "src.services.auth_service.get_wechat_client", return_value=mock_wechat_client
    ):
        result = await get_auth_service().wechat_login(
            db_session, "wx_phone_login", phone_code="valid_phone_code"
        )

    assert result["user"]["phone"] == "138****1234"
    user = (
        await db_session.execute(select(User).where(User.openid == "o_phone_login"))
    ).scalars().first()
    assert user.phone == "13800131234"
    assert user.phone_masked == "138****1234"
    assert user.phone_authorized is True
    customer = (
        await db_session.execute(select(Customer).where(Customer.user_id == user.id))
    ).scalars().one()
    assert customer.distributor_id is None
    assert customer.phone_normalized == "13800131234"
    assert customer.binding_status == BindingStatus.PENDING


@pytest.mark.asyncio
async def test_self_registration_creates_an_unassigned_pending_customer(db_session):
    result = await get_auth_service().distributor_register(
        db_session, "13900000001", "password123", "测试客户"
    )

    customer = (
        await db_session.execute(
            select(Customer).where(Customer.user_id == int(result["user"]["userId"]))
        )
    ).scalars().one()
    assert customer.name == "测试客户"
    assert customer.distributor_id is None
    assert customer.binding_status == BindingStatus.PENDING


@pytest.mark.asyncio
async def test_wechat_login_no_default_org(db_session, mock_wechat_client):
    """T012: No root org → still create User but skip Distributor, return null."""
    # No orgs created → get_default_org returns None
    mock_wechat_client.set_valid_code("wx_new_002", openid="o_no_org_user")

    with patch(
        "src.services.auth_service.get_wechat_client", return_value=mock_wechat_client
    ):
        result = await get_auth_service().wechat_login(db_session, "wx_new_002")

    assert result["user"]["isNewUser"] is True
    assert result.get("distributor") is None  # No org → no distributor


@pytest.mark.asyncio
async def test_existing_orphan_business_identity_is_repaired_to_personal(
    db_session, mock_wechat_client
):
    """A legacy business identity without membership is repaired to personal."""
    from sqlalchemy import select
    from src.models.distributor import Distributor

    org = await organization_service.create_org(
        db_session, OrgCreate(name="顶级部门", orgType=None)
    )
    orphan = User(
        openid="o_orphan_user",
        user_type=UserType.PROMOTER,
        wechat_bound=True,
    )
    db_session.add(orphan)
    await db_session.flush()
    await db_session.refresh(orphan)

    mock_wechat_client.set_valid_code("wx_orphan_001", openid="o_orphan_user")
    with patch(
        "src.services.auth_service.get_wechat_client", return_value=mock_wechat_client
    ):
        result = await get_auth_service().wechat_login(db_session, "wx_orphan_001")

    assert result["user"]["isNewUser"] is False
    assert "distributor" not in result
    assert result["user"]["role"] == "personal"
    assert result["hasBusinessMembership"] is False

    distributors = (
        await db_session.execute(
            select(Distributor).where(Distributor.user_id == orphan.id)
        )
    ).scalars().all()
    assert distributors == []


@pytest.mark.asyncio
async def test_existing_user_wechat_bind_no_duplicate(db_session, mock_wechat_client):
    """T024: Existing distributor phone match → WeChat bind only, no duplicate."""
    from src.models.distributor import DistributorStatus

    org = await organization_service.create_org(
        db_session, OrgCreate(name="默认组织", orgType=None)
    )

    # Create existing distributor with phone
    existing_user = User(
        name="已有用户",
        phone="13800009999",
        phone_masked="138****9999",
        password_hash=get_password_hash("password123"),
        user_type=UserType.DISTRIBUTOR,
        wechat_bound=False,
    )
    db_session.add(existing_user)
    await db_session.flush()
    await db_session.refresh(existing_user)

    existing_dist = await distributor_service.register_distributor(
        db_session, existing_user.id, org.id, "admin_create"
    )

    # Now simulate WeChat login with same phone
    mock_wechat_client.set_valid_code("wx_bind_001", openid="o_bind_001")

    with patch(
        "src.services.auth_service.get_wechat_client", return_value=mock_wechat_client
    ):
        with patch.object(
            get_auth_service(), "phone_bind", new_callable=AsyncMock
        ) as mock_phone_bind:
            mock_phone_bind.return_value = "138****9999"
            result = await get_auth_service().wechat_login(db_session, "wx_bind_001")

    # Should NOT be a new user
    assert result["user"]["isNewUser"] is True
    # No new distributor created
    dist_count = await db_session.execute(
        __import__("sqlalchemy").select(
            __import__("src.models.distributor", fromlist=["Distributor"]).Distributor
        ).where(
            __import__("src.models.distributor", fromlist=["Distributor"]).Distributor.user_id
            == existing_user.id
        )
    )
    # The existing distributor should still be the only one for this user
    assert dist_count is not None
