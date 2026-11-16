"""Command-result reads reauthorize the buyer and do not use stale token state."""

import pytest

from src.api.mall_deps import MallActor
from src.services.mall_command_service import complete_mall_command, reserve_mall_command
from tests.conftest import auth_header, make_access_token, seed_admin, seed_user


@pytest.mark.asyncio
async def test_buyer_reads_only_own_command_and_revocation_applies_immediately(client, db_session):
    user_id = await seed_user(db_session, user_type="personal", activation_status="active")
    reservation = await reserve_mall_command(
        db_session,
        actor=MallActor(actor_type="user", actor_id=user_id, permissions=frozenset()),
        action="mall.checkout.create",
        key="read-command-key",
        payload={"skuId": 1, "quantity": 1},
    )
    await complete_mall_command(
        db_session,
        reservation,
        entity_type="mall_order",
        entity_id=55,
    )
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=user_id, user_type="personal"))

    response = await client.get(f"/api/v1/mall/commands/{reservation.command.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == {
        "commandId": str(reservation.command.id),
        "status": "completed",
        "entityId": "55",
        "version": 1,
    }

    from src.models.user import ActivationStatus, User

    user = await db_session.get(User, user_id)
    user.activation_status = ActivationStatus.DISABLED
    await db_session.commit()
    denied = await client.get(f"/api/v1/mall/commands/{reservation.command.id}", headers=headers)
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_admin_command_rechecks_the_original_action_permission(client, db_session):
    from src.models.role import Role
    from src.models.user import admin_account_roles

    admin_id = await seed_admin(db_session)
    role = Role(name="商品编辑", permissions={"permissions": ["mall.products.write"]})
    db_session.add(role)
    await db_session.flush()
    await db_session.execute(
        admin_account_roles.insert().values(
            admin_account_id=admin_id,
            role_id=role.id,
        )
    )
    reservation = await reserve_mall_command(
        db_session,
        actor=MallActor("admin", admin_id, frozenset()),
        action="createAdminMallProduct",
        key="admin-command-probe",
        payload={"name": "测试"},
    )
    await db_session.commit()
    headers = auth_header(
        make_access_token(user_id=admin_id, user_type="admin", permissions=["mall.products.write"])
    )
    url = f"/api/v1/admin/mall/commands/{reservation.command.id}"
    assert (await client.get(url, headers=headers)).status_code == 200
    role.permissions = {"permissions": []}
    await db_session.commit()
    assert (await client.get(url, headers=headers)).status_code == 403
