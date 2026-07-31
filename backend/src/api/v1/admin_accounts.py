"""Admin account and role management endpoints (T177-T178).

GET    /admin/accounts          – list admin accounts
POST   /admin/accounts          – create account with role assignment
PUT    /admin/accounts/{id}     – update account
POST   /admin/accounts/{id}/disable – disable account
POST   /admin/accounts/{id}/enable  – re-enable
GET    /admin/roles             – list roles
POST   /admin/roles             – create role with permissions
PUT    /admin/roles/{id}        – update role
DELETE /admin/roles/{id}        – delete unused role
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException, ConflictException, NotFoundException
from ...core.security import get_password_hash
from ...api.deps import get_admin_user, require_permission
from ...models.role import Role
from ...models.user import AdminAccount, AdminStatus, admin_account_roles

admin_accounts_router = APIRouter(prefix="/admin/accounts", tags=["admin-accounts"])
admin_roles_router = APIRouter(prefix="/admin/roles", tags=["admin-roles"])


# ──────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────
class AdminAccountCreate(BaseModel):
    username: str = Field(..., min_length=4, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    roleIds: list[int] = Field(default_factory=list)


class AdminAccountUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=4, max_length=64)
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    roleIds: Optional[list[int]] = None


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    permissions: dict = Field(default_factory=dict)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    permissions: Optional[dict] = None


# =============================================================================
# Admin Accounts endpoints
# =============================================================================


@admin_accounts_router.get("")
async def list_admin_accounts(
    status: Optional[str] = Query(None, description="active, disabled, locked"),
    cursor: Optional[str] = Query(None),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("accounts.read")),
) -> dict:
    """List all admin accounts with their assigned roles."""
    query = select(AdminAccount)

    if status:
        try:
            st = getattr(AdminStatus, status.upper())
            query = query.where(AdminAccount.status == st)
        except (AttributeError, KeyError):
            pass

    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.where(AdminAccount.id < cursor_id)
        except (ValueError, TypeError):
            pass

    query = query.order_by(desc(AdminAccount.id)).limit(pageSize + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > pageSize
    items = rows[:pageSize]
    next_cursor = str(items[-1].id) if has_more and items else None

    data_items = []
    for acc in items:
        # Fetch roles for this account
        role_result = await db.execute(
            select(Role).join(
                admin_account_roles, admin_account_roles.c.role_id == Role.id
            ).where(admin_account_roles.c.admin_account_id == acc.id)
        )
        roles = role_result.scalars().all()
        role_items = [{"id": r.id, "name": r.name} for r in roles]

        data_items.append({
            "id": str(acc.id),
            "username": acc.username,
            "status": acc.status.value if hasattr(acc.status, "value") else str(acc.status),
            "roles": role_items,
            "createdAt": acc.created_at.isoformat() if acc.created_at else None,
            "updatedAt": acc.updated_at.isoformat() if acc.updated_at else None,
        })

    return _build_response(0, "success", {
        "items": data_items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    })


@admin_accounts_router.post("")
async def create_admin_account(
    body: AdminAccountCreate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("accounts.write")),
) -> dict:
    """Create a new admin account with role assignments."""
    # Check uniqueness
    existing = await db.execute(
        select(AdminAccount).where(AdminAccount.username == body.username)
    )
    if existing.scalars().first():
        raise ConflictException(message="Username already exists", code=40901)

    account = AdminAccount(
        username=body.username,
        password_hash=get_password_hash(body.password),
        status=AdminStatus.ACTIVE,
    )
    db.add(account)
    await db.flush()

    # Assign roles
    if body.roleIds:
        for role_id in body.roleIds:
            role_result = await db.execute(select(Role).where(Role.id == role_id))
            if role_result.scalars().first():
                await db.execute(
                    admin_account_roles.insert().values(
                        admin_account_id=account.id, role_id=role_id
                    )
                )

    await db.commit()
    await db.refresh(account)

    return _build_response(0, "success", {
        "id": str(account.id),
        "username": account.username,
        "status": account.status.value,
        "createdAt": account.created_at.isoformat() if account.created_at else None,
    })


@admin_accounts_router.put("/{account_id}")
async def update_admin_account(
    account_id: int,
    body: AdminAccountUpdate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("accounts.write")),
) -> dict:
    """Update an admin account's username, password, or role assignments."""
    result = await db.execute(select(AdminAccount).where(AdminAccount.id == account_id))
    account = result.scalars().first()
    if account is None:
        raise NotFoundException(message="Admin account not found")

    if body.username is not None and body.username != account.username:
        # Check uniqueness
        existing = await db.execute(
            select(AdminAccount).where(AdminAccount.username == body.username)
        )
        if existing.scalars().first():
            raise ConflictException(message="Username already exists", code=40901)
        account.username = body.username

    if body.password is not None:
        account.password_hash = get_password_hash(body.password)

    if body.roleIds is not None:
        # Remove existing roles
        await db.execute(
            admin_account_roles.delete().where(
                admin_account_roles.c.admin_account_id == account_id
            )
        )
        # Add new roles
        for role_id in body.roleIds:
            role_result = await db.execute(select(Role).where(Role.id == role_id))
            if role_result.scalars().first():
                await db.execute(
                    admin_account_roles.insert().values(
                        admin_account_id=account_id, role_id=role_id
                    )
                )

    db.add(account)
    await db.commit()
    await db.refresh(account)

    return _build_response(0, "success", {
        "id": str(account.id),
        "username": account.username,
        "updatedAt": account.updated_at.isoformat() if account.updated_at else None,
    })


@admin_accounts_router.post("/{account_id}/disable")
async def disable_admin_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("accounts.write")),
) -> dict:
    """Disable an admin account."""
    result = await db.execute(select(AdminAccount).where(AdminAccount.id == account_id))
    account = result.scalars().first()
    if account is None:
        raise NotFoundException(message="Admin account not found")

    # T011: Default admin cannot be disabled
    if account.username == "admin":
        raise BadRequestException(
            message="默认管理员账户不可禁用", code=40303
        )

    account.status = AdminStatus.DISABLED
    db.add(account)
    await db.commit()

    return _build_response(0, "success", {
        "id": str(account.id),
        "status": "disabled",
    })


@admin_accounts_router.post("/{account_id}/enable")
async def enable_admin_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("accounts.write")),
) -> dict:
    """Re-enable a disabled admin account."""
    result = await db.execute(select(AdminAccount).where(AdminAccount.id == account_id))
    account = result.scalars().first()
    if account is None:
        raise NotFoundException(message="Admin account not found")

    account.status = AdminStatus.ACTIVE
    db.add(account)
    await db.commit()

    return _build_response(0, "success", {
        "id": str(account.id),
        "status": "active",
    })


# =============================================================================
# Admin Roles endpoints
# =============================================================================


@admin_roles_router.get("")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("roles.read")),
) -> dict:
    """List all roles with their permissions."""
    result = await db.execute(select(Role).order_by(Role.id))
    roles = result.scalars().all()

    items = []
    for r in roles:
        items.append({
            "id": str(r.id),
            "name": r.name,
            "permissions": r.permissions,
            "is_system": r.is_system,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        })

    return _build_response(0, "success", {"items": items})


@admin_roles_router.post("")
async def create_role(
    body: RoleCreate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("roles.write")),
) -> dict:
    """Create a new role with permissions."""
    # Check uniqueness
    existing = await db.execute(select(Role).where(Role.name == body.name))
    if existing.scalars().first():
        raise ConflictException(message="Role name already exists", code=40901)

    role = Role(name=body.name, permissions=body.permissions)
    db.add(role)
    await db.commit()
    await db.refresh(role)

    return _build_response(0, "success", {
        "id": str(role.id),
        "name": role.name,
        "permissions": role.permissions,
        "createdAt": role.created_at.isoformat() if role.created_at else None,
    })


@admin_roles_router.put("/{role_id}")
async def update_role(
    role_id: int,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("roles.write")),
) -> dict:
    """Update a role's name or permissions."""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalars().first()
    if role is None:
        raise NotFoundException(message="Role not found")

    if body.name is not None:
        # T009: System role name cannot be changed
        if role.is_system:
            raise BadRequestException(
                message="系统管理员角色名称不可修改", code=40302
            )
        # Check uniqueness if name changed
        if body.name != role.name:
            existing = await db.execute(select(Role).where(Role.name == body.name))
            if existing.scalars().first():
                raise ConflictException(message="Role name already exists", code=40901)
        role.name = body.name

    if body.permissions is not None:
        role.permissions = body.permissions

    db.add(role)
    await db.commit()
    await db.refresh(role)

    return _build_response(0, "success", {
        "id": str(role.id),
        "name": role.name,
        "permissions": role.permissions,
    })


@admin_roles_router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("roles.write")),
) -> dict:
    """Delete a role that is not assigned to any account."""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalars().first()
    if role is None:
        raise NotFoundException(message="Role not found")

    # T006: System roles cannot be deleted
    if role.is_system:
        raise BadRequestException(
            message="系统管理员角色不可删除", code=40301
        )

    # Check if role is in use
    usage_result = await db.execute(
        select(func.count()).select_from(admin_account_roles).where(
            admin_account_roles.c.role_id == role_id
        )
    )
    usage_count = usage_result.scalar() or 0
    if usage_count > 0:
        raise ConflictException(
            message=f"Role is assigned to {usage_count} account(s). Remove assignments first.",
            code=40902,
        )

    await db.delete(role)
    await db.commit()

    return _build_response(0, "success", None)
