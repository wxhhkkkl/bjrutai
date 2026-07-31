"""Integration tests for system admin role seeding.

TDD: These tests are written FIRST and expected to FAIL until
the seed_service is implemented.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import seed_admin as _seed_admin


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────
async def _count_roles(db: AsyncSession) -> int:
    from src.models.role import Role

    result = await db.execute(select(Role))
    return len(result.scalars().all())


async def _get_system_role(db: AsyncSession):
    from src.models.role import Role

    result = await db.execute(select(Role).where(Role.is_system == True))
    return result.scalars().first()


# ────────────────────────────────────────────────────────────────
# T015: Seed creates system admin role when none exists
# ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_seed_creates_system_admin_role(db_session: AsyncSession):
    """First run: no system role → seed creates it."""
    from src.services.seed_service import seed_system_admin_role

    # Ensure DB is empty
    count_before = await _count_roles(db_session)
    assert count_before == 0

    await seed_system_admin_role(db_session)

    system_role = await _get_system_role(db_session)
    assert system_role is not None
    assert system_role.name == "系统管理员"
    assert system_role.is_system is True
    assert isinstance(system_role.permissions, dict)
    perms = system_role.permissions.get("permissions", [])
    assert len(perms) >= 20  # At least 20 permissions


# ────────────────────────────────────────────────────────────────
# T016: Seed is idempotent (second run does not duplicate)
# ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session: AsyncSession):
    """Running seed twice should not create duplicate roles."""
    from src.services.seed_service import seed_system_admin_role

    # First run
    await seed_system_admin_role(db_session)
    count_1 = await _count_roles(db_session)

    # Second run
    await seed_system_admin_role(db_session)
    count_2 = await _count_roles(db_session)

    assert count_1 == count_2
    assert count_1 == 1  # Only the system admin role


# ────────────────────────────────────────────────────────────────
# T017: Seed assigns system admin role to admin account
# ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_seed_assigns_role_to_admin(db_session: AsyncSession):
    """Seed should link the existing admin account to the system role."""
    from src.services.seed_service import seed_system_admin_role
    from src.models.user import admin_account_roles
    from sqlalchemy import func

    # Create admin account
    admin_id = await _seed_admin(db_session, username="admin")

    # Run seed
    await seed_system_admin_role(db_session)

    # Verify admin is linked to system role
    system_role = await _get_system_role(db_session)
    assert system_role is not None

    result = await db_session.execute(
        select(func.count())
        .select_from(admin_account_roles)
        .where(
            admin_account_roles.c.admin_account_id == admin_id,
            admin_account_roles.c.role_id == system_role.id,
        )
    )
    count = result.scalar()
    assert count == 1
