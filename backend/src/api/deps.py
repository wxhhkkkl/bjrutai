"""Shared FastAPI dependencies for API v1.

Provides DB session, current-user extraction, and RBAC guards.
"""

from typing import AsyncGenerator, Callable

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
        raise UnauthorizedException(message="Token expired")

    token = credentials.credentials
    try:
        payload = verify_token(token)
    except Exception as exc:
        msg = str(exc).lower()
        if "expired" in msg or "exp" in msg:
            raise UnauthorizedException(message="Token expired")
        raise UnauthorizedException(message="Token invalid or malformed")

    if payload.get("type") != "access":
        raise UnauthorizedException(message="Token invalid or malformed")

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
            raise ForbiddenException(message="Forbidden")
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
