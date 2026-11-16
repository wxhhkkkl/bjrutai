"""Mall-only authorization must be checked against current database state."""

import pytest

from src.core.exceptions import ForbiddenException
from src.models.role import Role
from src.models.user import AdminStatus, User, admin_account_roles
from tests.conftest import seed_admin, seed_user


@pytest.mark.asyncio
async def test_mall_buyer_requires_a_live_personal_account(db_session):
    from src.api.mall_deps import require_mall_buyer

    user_id = await seed_user(db_session, user_type="personal", activation_status="active")
    payload = {"sub": str(user_id), "user_type": "personal"}

    actor = await require_mall_buyer(payload, db_session)
    assert actor.actor_type == "user"
    assert actor.actor_id == user_id

    user = await db_session.get(User, user_id)
    user.activation_status = "disabled"
    await db_session.flush()
    with pytest.raises(ForbiddenException, match="停用"):
        await require_mall_buyer(payload, db_session)


@pytest.mark.asyncio
async def test_mall_admin_rechecks_status_and_permissions_not_jwt_claims(db_session):
    from src.api.mall_deps import require_mall_admin_permission

    admin_id = await seed_admin(db_session)
    role = Role(name="商城财务", permissions={"permissions": ["mall.payments.read"]})
    db_session.add(role)
    await db_session.flush()
    await db_session.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    payload = {
        "sub": str(admin_id),
        "user_type": "admin",
        "permissions": ["mall.payments.read", "mall.refunds.write"],
    }

    actor = await require_mall_admin_permission(payload, db_session, "mall.payments.read")
    assert actor.actor_type == "admin"
    assert actor.permissions == frozenset({"mall.payments.read"})

    with pytest.raises(ForbiddenException, match="权限"):
        await require_mall_admin_permission(payload, db_session, "mall.refunds.write")

    admin = await db_session.get(User, admin_id)
    assert admin is None  # AdminAccount IDs must never be treated as users.
    from src.models.user import AdminAccount

    account = await db_session.get(AdminAccount, admin_id)
    account.status = AdminStatus.DISABLED
    await db_session.flush()
    with pytest.raises(ForbiddenException, match="停用"):
        await require_mall_admin_permission(payload, db_session, "mall.payments.read")


@pytest.mark.asyncio
async def test_active_business_user_can_buy_without_a_membership_check(db_session):
    from src.api.mall_deps import require_mall_buyer

    user_id = await seed_user(db_session, user_type="distributor")
    actor = await require_mall_buyer({"sub": str(user_id), "user_type": "distributor"}, db_session)
    assert actor.actor_id == user_id


def test_mall_owner_and_raw_data_gate_are_fail_closed():
    from src.api.mall_deps import MallActor, require_mall_object_owner, require_raw_data_delivery

    buyer = MallActor(actor_type="user", actor_id=7, permissions=frozenset())
    require_mall_object_owner(buyer, owner_user_id=7)
    with pytest.raises(ForbiddenException, match="本人"):
        require_mall_object_owner(buyer, owner_user_id=8)
    with pytest.raises(ForbiddenException, match="资料"):
        require_raw_data_delivery()
    require_raw_data_delivery(raw_data_enabled=True)
