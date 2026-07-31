"""Seed system admin role and assign to default admin account.

Idempotent: safely re-runnable on every startup.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.role import Role
from ..models.user import AdminAccount, admin_account_roles

logger = logging.getLogger(__name__)

# Full permission set matching manageSystem/src/constants/permissions.js
_ALL_PERMISSIONS = {
    "permissions": [
        "accounts.read", "accounts.write",
        "roles.read", "roles.write",
        "customers.read", "customers.write",
        "qualifications.read", "qualifications.write",
        "contributions.read",
        "reports.read",
        "articles.read", "articles.write",
        "promotions.read", "promotions.write",
        "notifications.read", "notifications.write",
        "hierarchy.read", "hierarchy.write",
        "sharing_rules.read", "sharing_rules.write",
        "sync.read", "sync.write",
    ]
}


async def seed_system_admin_role(db: AsyncSession) -> None:
    """Create the system admin role if it doesn't exist (idempotent).

    Also assigns the system admin role to the default admin account
    (username="admin") if not already assigned.
    """
    # ── Create system admin role ──────────────────────────────────
    result = await db.execute(
        select(Role).where(Role.is_system == True)
    )
    system_role = result.scalars().first()

    if system_role is None:
        system_role = Role(
            name="系统管理员",
            permissions=_ALL_PERMISSIONS,
            is_system=True,
        )
        db.add(system_role)
        await db.flush()
        await db.refresh(system_role)
        logger.info("Created system admin role: %s", system_role.name)

    # ── Assign to default admin ───────────────────────────────────
    admin_result = await db.execute(
        select(AdminAccount).where(AdminAccount.username == "admin")
    )
    admin = admin_result.scalars().first()

    if admin is not None:
        # Check if already assigned
        from sqlalchemy import func

        assignment = await db.execute(
            select(func.count())
            .select_from(admin_account_roles)
            .where(
                admin_account_roles.c.admin_account_id == admin.id,
                admin_account_roles.c.role_id == system_role.id,
            )
        )
        already_linked = (assignment.scalar() or 0) > 0

        if not already_linked:
            await db.execute(
                admin_account_roles.insert().values(
                    admin_account_id=admin.id,
                    role_id=system_role.id,
                )
            )
            await db.flush()
            logger.info(
                "Assigned admin '%s' to system admin role", admin.username
            )


async def seed_default_category(db: AsyncSession) -> None:
    """Create a default article category if none exists (idempotent)."""
    from ..models.category import ArticleCategory

    result = await db.execute(select(ArticleCategory).limit(1))
    if result.scalars().first() is None:
        cat = ArticleCategory(name="默认分类", sort_order=0)
        db.add(cat)
        await db.flush()
        logger.info("Created default article category: %s", cat.name)
