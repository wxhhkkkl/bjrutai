"""Unit & integration tests for role deletion/update protections.

TDD: These tests are written FIRST and expected to FAIL until
protections are implemented in admin_accounts.py.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    assert_response_envelope,
    make_access_token,
    seed_admin,
    seed_role,
)


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────
def _admin_auth(user_id: int = 1) -> dict:
    token = make_access_token(
        user_id=user_id,
        user_type="admin",
        permissions=["accounts.read", "accounts.write", "roles.read", "roles.write"],
    )
    return {"Authorization": f"Bearer {token}"}


# ────────────────────────────────────────────────────────────────
# T004: Delete system role → error
# ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_delete_system_role_returns_error(
    db_session: AsyncSession, client: AsyncClient
):
    """Deleting a role with is_system=True must return error."""
    await seed_admin(db_session, username="admin")
    role_id = await seed_role(db_session, name="系统管理员")
    # Mark as system role
    from src.models.role import Role
    from sqlalchemy import update

    await db_session.execute(
        update(Role).where(Role.id == role_id).values(is_system=True)
    )
    await db_session.commit()

    resp = await client.delete(
        f"/api/v1/admin/roles/{role_id}", headers=_admin_auth()
    )
    data = resp.json()
    assert resp.status_code == 400
    assert data.get("code") == 40301


# ────────────────────────────────────────────────────────────────
# T005: Delete assigned role → error
# ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_delete_assigned_role_returns_error(
    db_session: AsyncSession, client: AsyncClient
):
    """Deleting a role that is assigned to admin(s) must return 409."""
    admin_id = await seed_admin(db_session, username="admin")
    role_id = await seed_role(db_session, name="编辑员")

    # Assign the role to admin
    from src.models.user import admin_account_roles
    await db_session.execute(
        admin_account_roles.insert().values(
            admin_account_id=admin_id, role_id=role_id
        )
    )
    await db_session.commit()

    resp = await client.delete(
        f"/api/v1/admin/roles/{role_id}", headers=_admin_auth()
    )
    data = resp.json()
    assert resp.status_code == 409
    assert data.get("code") == 40902


# ────────────────────────────────────────────────────────────────
# T008: Update system role name → error
# ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_update_system_role_name_returns_error(
    db_session: AsyncSession, client: AsyncClient
):
    """Updating the name of a system role must be rejected."""
    await seed_admin(db_session, username="admin")
    role_id = await seed_role(db_session, name="系统管理员")
    from src.models.role import Role
    from sqlalchemy import update

    await db_session.execute(
        update(Role).where(Role.id == role_id).values(is_system=True)
    )
    await db_session.commit()

    resp = await client.put(
        f"/api/v1/admin/roles/{role_id}",
        json={"name": "超级管理员"},
        headers=_admin_auth(),
    )
    data = resp.json()
    assert resp.status_code == 400
    assert data.get("code") == 40302
