"""Admin sync management endpoints.

Provides manual retry triggers and sync status monitoring.
All endpoints require admin authentication.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import ConflictException, NotFoundException
from ..deps import get_admin_user
from ...services.sync_service import get_sync_service

router = APIRouter(prefix="/admin/sync", tags=["admin-sync"])


# =========================================================================
# POST /admin/sync/retry-binduser
# =========================================================================
@router.post("/retry-binduser")
async def retry_bind_user(
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Manually trigger a retry of the getBindUser polling.

    Returns 409 if a sync is already in progress.
    """
    svc = get_sync_service()
    try:
        result = await svc.retry_bind_users(db)
        return _build_response(0, "success", result)
    except Exception as e:
        if "already" in str(e).lower():
            raise ConflictException(message=str(e))
        raise


# =========================================================================
# POST /admin/sync/retry-bill/{user_id}
# =========================================================================
@router.post("/retry-bill/{user_id}")
async def retry_bill(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Manually retry bill fetch for a specific Rutai user.

    Returns 404 if the user is not found.
    """
    svc = get_sync_service()
    try:
        result = await svc.retry_user_bill(db, user_id)
        return _build_response(0, "success", result)
    except Exception as e:
        if "not found" in str(e).lower():
            raise NotFoundException(message=str(e))
        raise


# =========================================================================
# GET /admin/sync/status
# =========================================================================
@router.get("/status")
async def sync_status(
    _current_admin: dict = Depends(get_admin_user),
):
    """Return current sync polling status, last success time, failure count,
    and circuit breaker state.
    """
    svc = get_sync_service()
    result = await svc.get_sync_status()
    return _build_response(0, "success", result)
