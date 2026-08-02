"""Admin distributor management endpoints (US3/US4)."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...schemas.distributor import (
    DistributorCreate,
    DistributorRoleUpdate,
    DistributorUpdate,
    ResetPassword,
)
from ...services import distributor_service

router = APIRouter(prefix="/admin", tags=["admin-distributors"])


def _operator_id(payload: dict) -> Optional[int]:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


@router.get("/orgs/{org_id}/distributors")
async def list_distributors(
    org_id: int,
    include_subtree: bool = Query(False, alias="includeSubtree"),
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("distributor.read")),
):
    """List distributors under an org (optionally the whole subtree)."""
    result = await distributor_service.list_distributors(
        db, org_id, include_subtree=include_subtree, role=role,
        status=status, keyword=keyword, limit=limit, offset=offset,
    )
    return _build_response(0, "success", result)


@router.post("/orgs/{org_id}/distributors")
async def create_distributor(
    org_id: int,
    body: DistributorCreate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("distributor.write")),
):
    """Create a distributor account within an org."""
    result = await distributor_service.create_distributor(
        db, org_id, body, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.put("/distributors/{distributor_id}")
async def update_distributor(
    distributor_id: int,
    body: DistributorUpdate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("distributor.write")),
):
    """Adjust a distributor's org and/or status."""
    result = await distributor_service.update_distributor(
        db, distributor_id, body, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.post("/distributors/{distributor_id}/reset-password")
async def reset_password(
    distributor_id: int,
    body: ResetPassword,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("distributor.write")),
):
    """Reset a distributor's login credential."""
    await distributor_service.reset_password(db, distributor_id, body, operator_id=_operator_id(admin))
    return _build_response(0, "success", None)


@router.put("/distributors/{distributor_id}/role")
async def set_role(
    distributor_id: int,
    body: DistributorRoleUpdate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org_admin.write")),
):
    """Set or revoke org-admin role for a distributor (US4)."""
    result = await distributor_service.set_role(
        db, distributor_id, body, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)
