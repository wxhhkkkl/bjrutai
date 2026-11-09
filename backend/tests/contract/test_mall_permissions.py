"""Contract and runtime checks for the independent mall access boundaries."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from src.models.role import Role
from src.models.user import ActivationStatus, User, admin_account_roles
from tests.conftest import (
    auth_header,
    make_access_token,
    seed_admin,
    seed_user,
)

FEATURE = Path(__file__).resolve().parents[3] / "specs/022-independent-mall"
PUBLIC_OPERATIONS = {
    "listMallCategories",
    "listMallProducts",
    "getMallProduct",
    "getMallCheckoutSettings",
}
SIGNED_PROVIDER_OPERATIONS = {"wechatPaymentNotify", "wechatRefundNotify"}


def test_all_106_contract_operations_have_an_explicit_actor_and_access_class():
    contract = json.loads((FEATURE / "contracts/openapi.json").read_text())
    operations = {
        operation["operationId"]: operation
        for methods in contract["paths"].values()
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }

    assert len(operations) == 106
    classified_authenticated = {
        name
        for name, operation in operations.items()
        if operation.get("x-actor-policy") in {"buyer", "admin"}
    }
    assert set(operations) == (
        PUBLIC_OPERATIONS | SIGNED_PROVIDER_OPERATIONS | classified_authenticated
    )

    actor_counts = {"public": 0, "buyer": 0, "admin": 0, "wechat_signature": 0}
    for operation_id, operation in operations.items():
        actor = operation.get("x-actor-policy")
        assert actor in actor_counts, operation_id
        actor_counts[actor] += 1

        if actor == "public":
            assert operation_id in PUBLIC_OPERATIONS
            assert operation.get("security") == []
        elif actor == "wechat_signature":
            assert operation_id in SIGNED_PROVIDER_OPERATIONS
            assert operation.get("security") == []
            assert operation.get("x-implementation-gate") == "G-PROTOCOL"
        else:
            assert operation.get("security", contract.get("security")) == [
                {"bearerAuth": []}
            ]

        if actor == "admin":
            assert (
                operation.get("x-permission")
                or operation.get("x-permission-policy")
            ), operation_id

    assert actor_counts == {
        "public": 4,
        "buyer": 33,
        "admin": 67,
        "wechat_signature": 2,
    }


async def _admin_with_permissions(db, permissions):
    admin_id = await seed_admin(db, username=f"mall-permission-{uuid4().hex}")
    role = Role(
        name=f"商城权限矩阵-{uuid4().hex}",
        permissions={"permissions": permissions},
    )
    db.add(role)
    await db.flush()
    await db.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    await db.commit()
    return admin_id, role


@pytest.mark.asyncio
async def test_admin_access_uses_live_role_and_rejects_anonymous_and_buyers(
    client, db_session
):
    route = "/api/v1/admin/mall/payments"
    assert (await client.get(route)).status_code == 401

    buyer_id = await seed_user(
        db_session, user_type="personal", openid=f"mall-permission-buyer-{uuid4().hex}"
    )
    await db_session.commit()
    buyer_headers = auth_header(
        make_access_token(user_id=buyer_id, user_type="personal")
    )
    assert (await client.get(route, headers=buyer_headers)).status_code == 403

    admin_id, role = await _admin_with_permissions(db_session, ["mall.payments.read"])
    # This JWT deliberately contains a permission claim. The API must consult the
    # current database role rather than trusting an older token snapshot.
    old_headers = auth_header(
        make_access_token(
            user_id=admin_id,
            user_type="admin",
            permissions=["mall.payments.read"],
        )
    )
    assert (await client.get(route, headers=old_headers)).status_code == 200

    role.permissions = {"permissions": ["mall.refunds.read"]}
    await db_session.commit()
    db_session.expire_all()
    assert (await client.get(route, headers=old_headers)).status_code == 403


@pytest.mark.asyncio
async def test_disabled_buyer_and_closed_raw_data_actions_fail_with_existing_tokens(
    client, db_session
):
    buyer_id = await seed_user(
        db_session, user_type="personal", openid=f"mall-disabled-buyer-{uuid4().hex}"
    )
    buyer_headers = auth_header(
        make_access_token(user_id=buyer_id, user_type="personal")
    )
    await db_session.commit()
    route = "/api/v1/mall/addresses"
    assert (await client.get(route, headers=buyer_headers)).status_code == 200

    buyer = await db_session.get(User, buyer_id)
    buyer.activation_status = ActivationStatus.DISABLED
    await db_session.commit()
    db_session.expire_all()
    assert (await client.get(route, headers=buyer_headers)).status_code == 403

    admin_id, _ = await _admin_with_permissions(
        db_session, ["mall.billing.release", "mall.fulfillment.release"]
    )
    admin_headers = auth_header(
        make_access_token(
            user_id=admin_id,
            user_type="admin",
            permissions=["mall.billing.release", "mall.fulfillment.release"],
        )
    )
    billing = await client.post(
        "/api/v1/admin/mall/invoice-requests/1/billing-release",
        headers={**admin_headers, "Idempotency-Key": "billing-release-matrix-001"},
        json={
            "expectedVersion": 1,
            "purpose": "invoice_issue",
            "reason": "权限矩阵验证",
        },
    )
    fulfillment = await client.post(
        "/api/v1/admin/mall/orders/1/fulfillment-release",
        headers={**admin_headers, "Idempotency-Key": "fulfillment-release-matrix-001"},
        json={
            "expectedVersion": 1,
            "purpose": "shipping_label",
            "reason": "权限矩阵验证",
        },
    )
    assert billing.status_code == 403 and "未获授权" in billing.text
    assert fulfillment.status_code == 403 and "未获授权" in fulfillment.text

