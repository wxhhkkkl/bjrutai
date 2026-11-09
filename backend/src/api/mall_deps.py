"""Live, mall-only authorization and privacy guards.

Existing application endpoints keep their legacy JWT dependencies unchanged.
Every new mall endpoint must use this module so revocation and role changes
take effect without waiting for an old access token to expire.
"""

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import ForbiddenException, UnauthorizedException
from ..models.role import Role
from ..models.user import ActivationStatus, AdminAccount, AdminStatus, User, admin_account_roles
from .deps import get_current_user, get_db


@dataclass(frozen=True)
class MallActor:
    """Authenticated mall actor with live database authorization."""

    actor_type: str
    actor_id: int
    permissions: frozenset[str]


def _payload_id(payload: dict) -> int:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedException(message="登录凭证无效，请重新登录") from exc


async def require_mall_buyer(payload: dict, db: AsyncSession) -> MallActor:
    """Allow an active mini-program user, regardless of business membership."""
    if payload.get("user_type") == "admin":
        raise ForbiddenException(message="后台账号不能作为小程序买家")

    user = await db.get(User, _payload_id(payload), populate_existing=True)
    if user is None:
        raise UnauthorizedException(message="用户不存在，请重新登录")
    if user.activation_status != ActivationStatus.ACTIVE:
        raise ForbiddenException(message="当前买家账号已停用")
    return MallActor(actor_type="user", actor_id=user.id, permissions=frozenset())


async def get_mall_buyer(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MallActor:
    """FastAPI dependency version of :func:`require_mall_buyer`."""
    return await require_mall_buyer(payload, db)


async def _live_admin_permissions(
    db: AsyncSession, admin_id: int, *, current=False
) -> frozenset[str]:
    query = (
        select(Role)
        .join(admin_account_roles, admin_account_roles.c.role_id == Role.id)
        .where(admin_account_roles.c.admin_account_id == admin_id)
    )
    if current:
        query = query.with_for_update(read=True).execution_options(populate_existing=True)
    roles = (await db.execute(query)).scalars().all()
    values: set[str] = set()
    for role in roles:
        permissions = role.permissions
        if isinstance(permissions, dict):
            permissions = permissions.get("permissions", [])
        if isinstance(permissions, list):
            values.update(value for value in permissions if isinstance(value, str))
    return frozenset(values)


async def require_mall_admin_permission(
    payload: dict,
    db: AsyncSession,
    permission: str,
    *,
    current: bool = False,
) -> MallActor:
    """Require a live enabled backend account and a live role permission."""
    if payload.get("user_type") != "admin":
        raise ForbiddenException(message="仅后台管理员可执行此商城操作")

    if current:
        account = await db.scalar(
            select(AdminAccount)
            .where(AdminAccount.id == _payload_id(payload))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    else:
        account = await db.get(AdminAccount, _payload_id(payload), populate_existing=True)
    if account is None:
        raise UnauthorizedException(message="后台账号不存在，请重新登录")
    if account.status != AdminStatus.ACTIVE:
        raise ForbiddenException(message="当前后台账号已停用")

    permissions = await _live_admin_permissions(db, account.id, current=current)
    if permission not in permissions:
        raise ForbiddenException(message=f"缺少商城权限: {permission}")
    return MallActor(actor_type="admin", actor_id=account.id, permissions=permissions)


def require_mall_admin(permission: str) -> Callable:
    """Build a FastAPI dependency that rechecks the permission per request."""

    async def dependency(
        payload: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> MallActor:
        return await require_mall_admin_permission(payload, db, permission)

    return dependency


def require_mall_admin_any(*permissions: str) -> Callable:
    """Build a live admin dependency that accepts any one of several permissions."""
    required = frozenset(permission for permission in permissions if permission)
    if not required:
        raise ValueError("at least one mall permission is required")

    async def dependency(
        payload: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> MallActor:
        if payload.get("user_type") != "admin":
            raise ForbiddenException(message="仅后台管理员可执行此商城操作")

        account = await db.get(AdminAccount, _payload_id(payload), populate_existing=True)
        if account is None:
            raise UnauthorizedException(message="后台账号不存在，请重新登录")
        if account.status != AdminStatus.ACTIVE:
            raise ForbiddenException(message="当前后台账号已停用")

        live_permissions = await _live_admin_permissions(db, account.id)
        if live_permissions.isdisjoint(required):
            raise ForbiddenException(message="缺少商城工作台权限")
        return MallActor(actor_type="admin", actor_id=account.id, permissions=live_permissions)

    return dependency


def require_mall_object_owner(actor: MallActor, owner_user_id: int) -> None:
    """Fail closed unless the actor is the buyer that owns this object."""
    if actor.actor_type != "user" or actor.actor_id != owner_user_id:
        raise ForbiddenException(message="只能访问本人商城资料")


def require_raw_data_delivery(*, raw_data_enabled: bool = False) -> None:
    """Keep original recipient/invoice data delivery off until governance allows it."""
    if not raw_data_enabled:
        raise ForbiddenException(message="原文资料交付当前未获授权")
