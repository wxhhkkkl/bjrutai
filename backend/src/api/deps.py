"""Shared FastAPI dependencies for API v1.

Provides DB session, current-user extraction, and RBAC guards.
"""

from typing import AsyncGenerator, Callable

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db as _get_db
from ..core.exceptions import ForbiddenException, UnauthorizedException
from ..core.security import verify_token

# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async generator yielding a database session (rolls back on error)."""
    async for session in _get_db():
        yield session


# ---------------------------------------------------------------------------
# Bearer-token extraction
# ---------------------------------------------------------------------------
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI dependency: extract and validate the JWT, return payload dict.

    The returned dict contains at minimum ``sub`` (user_id) and ``user_type``.
    Raises ``UnauthorizedException`` when the token is missing, malformed, or expired.
    """
    if credentials is None:
        raise UnauthorizedException(message="登录已过期，请重新登录")

    token = credentials.credentials
    try:
        payload = verify_token(token)
    except Exception as exc:
        msg = str(exc).lower()
        if "expired" in msg or "exp" in msg:
            raise UnauthorizedException(message="登录已过期，请重新登录")
        raise UnauthorizedException(message="登录凭证无效，请重新登录")

    if payload.get("type") != "access":
        raise UnauthorizedException(message="登录凭证无效，请重新登录")

    return payload


# ---------------------------------------------------------------------------
# RBAC: require specific roles
# ---------------------------------------------------------------------------
def require_role(*roles: str) -> Callable:
    """FastAPI dependency factory: enforces that the current user has one of *roles*.

    Usage::

        @router.get("/admin/dashboard")
        async def dashboard(user=Depends(require_role("admin", "ops"))):
            ...
    """

    async def _dependency(
        payload: dict = Depends(get_current_user),
    ) -> dict:
        user_type = payload.get("user_type", "")
        if user_type not in roles:
            raise ForbiddenException(message="无权执行此操作")
        return payload

    return _dependency


# ---------------------------------------------------------------------------
# Admin-only dependency
# ---------------------------------------------------------------------------
async def get_admin_user(
    payload: dict = Depends(require_role("admin")),
) -> dict:
    """Dependency that ensures the caller is an admin."""
    return payload


async def require_active_distributor(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Require an active organization member in an active organization."""
    from ..models.distributor import Distributor, DistributorStatus
    from ..models.organization import Organization, OrgStatus
    from ..models.user import ActivationStatus, User

    user_id = int(payload["sub"])
    result = await db.execute(
        select(Distributor, User, Organization)
        .join(User, User.id == Distributor.user_id)
        .join(Organization, Organization.id == Distributor.org_id)
        .where(Distributor.user_id == user_id)
    )
    row = result.first()
    if row is None:
        raise ForbiddenException(message="成为客户顾问后才能使用客户和消费功能")

    distributor, user, organization = row
    if (
        distributor.status != DistributorStatus.ACTIVE
        or user.activation_status != ActivationStatus.ACTIVE
        or organization.status != OrgStatus.ACTIVE
    ):
        raise ForbiddenException(message="当前组织人员账号已停用")
    return distributor


async def require_active_distributor_or_admin(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Allow a backend admin or require an active mini-program business member."""
    if payload.get("user_type") == "admin":
        return payload
    return await require_active_distributor(payload, db)


async def require_org_admin(
    distributor=Depends(require_active_distributor),
):
    """Require the current organization member to be its organization admin."""
    from ..models.distributor import OrgRole

    if distributor.org_role != OrgRole.ADMIN:
        raise ForbiddenException(message="只有组织管理员可以发展客户顾问")
    return distributor


# ---------------------------------------------------------------------------
# RBAC: require specific permission
# ---------------------------------------------------------------------------
def require_permission(permission_key: str) -> Callable:
    """FastAPI dependency factory: enforce the caller has a specific permission.

    Permissions are embedded in the JWT access token at login time.
    The system admin (with full permissions) always passes.

    Usage::

        @router.get("/admin/accounts")
        async def list_accounts(user=Depends(require_permission("accounts.read"))):
            ...
    """

    async def _dependency(
        payload: dict = Depends(get_current_user),
    ) -> dict:
        permissions: list[str] = payload.get("permissions", [])
        if permission_key not in permissions:
            raise ForbiddenException(message=f"缺少权限: {permission_key}")
        return payload

    return _dependency
