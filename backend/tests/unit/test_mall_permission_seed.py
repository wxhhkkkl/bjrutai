"""The system administrator receives mall permissions without widening others."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.models.role import Role
from src.models.user import AdminAccount, admin_account_roles
from src.services.seed_service import _ALL_PERMISSIONS, seed_system_admin_role
from tests.conftest import seed_admin

EXPECTED_MALL_PERMISSIONS = {
    "mall.products.read",
    "mall.products.write",
    "mall.stock.read",
    "mall.stock.write",
    "mall.files.read",
    "mall.files.write",
    "mall.orders.read",
    "mall.orders.write",
    "mall.shipments.write",
    "mall.fulfillment.release",
    "mall.invoices.read",
    "mall.invoices.write",
    "mall.billing.release",
    "mall.aftersales.read",
    "mall.aftersales.review",
    "mall.returns.receive",
    "mall.payments.read",
    "mall.payments.query",
    "mall.refunds.read",
    "mall.refunds.query",
    "mall.refunds.execute",
    "mall.finance.export",
    "mall.reconciliations.read",
    "mall.reconciliations.write",
    "mall.settings.read",
    "mall.settings.write",
    "mall.attribution.write",
}

FEATURE = Path(__file__).resolve().parents[3] / "specs/022-independent-mall"


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_keeps_mall_grants_on_system_admin_only(db_session):
    system_admin_id = await seed_admin(db_session, username="admin")
    business_admin_id = await seed_admin(
        db_session, username=f"business-role-{uuid4().hex}"
    )
    business_role = Role(
        name=f"业务组织权限-{uuid4().hex}",
        permissions={"permissions": ["org.read", "distributor.read"]},
    )
    db_session.add(business_role)
    await db_session.flush()
    await db_session.execute(
        admin_account_roles.insert().values(
            admin_account_id=business_admin_id,
            role_id=business_role.id,
        )
    )
    await db_session.commit()

    await seed_system_admin_role(db_session)
    await seed_system_admin_role(db_session)

    system_roles = (
        await db_session.scalars(select(Role).where(Role.is_system.is_(True)))
    ).all()
    assert len(system_roles) == 1
    system_role = system_roles[0]
    permissions = set(system_role.permissions["permissions"])
    assert {key for key in permissions if key.startswith("mall.")} == EXPECTED_MALL_PERMISSIONS
    assert permissions == set(_ALL_PERMISSIONS["permissions"])

    contract = json.loads((FEATURE / "contracts/openapi.json").read_text())
    required_by_contract = {
        operation["x-permission"]
        for methods in contract["paths"].values()
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
        and operation.get("x-actor-policy") == "admin"
        and operation.get("x-permission")
    }
    assert required_by_contract.issubset(permissions)

    assigned_system_role_ids = set(
        await db_session.scalars(
            select(admin_account_roles.c.admin_account_id).where(
                admin_account_roles.c.role_id == system_role.id
            )
        )
    )
    assert assigned_system_role_ids == {system_admin_id}

    unchanged_business_role = await db_session.get(Role, business_role.id)
    assert unchanged_business_role.permissions == {
        "permissions": ["org.read", "distributor.read"]
    }
    business_links = await db_session.scalar(
        select(func.count())
        .select_from(admin_account_roles)
        .where(
            admin_account_roles.c.admin_account_id == business_admin_id,
            admin_account_roles.c.role_id == business_role.id,
        )
    )
    assert business_links == 1
    assert await db_session.scalar(
        select(func.count()).select_from(AdminAccount).where(AdminAccount.id == system_admin_id)
    ) == 1

