"""Admin organization tree management endpoints (US1).

All endpoints require admin auth; write operations require ``org.write``,
read operations require ``org.read``.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...schemas.organization import (
    OrgCreate,
    OrgMigrateRequest,
    OrgUpdate,
)
from ...services import organization_service

router = APIRouter(prefix="/admin/orgs", tags=["admin-orgs"])


def _operator_id(payload: dict) -> Optional[int]:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


@router.get("")
async def get_full_tree(
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.read")),
):
    """Return the full organization tree."""
    result = await organization_service.get_tree(db)
    return _build_response(0, "success", result)


@router.get("/{org_id}")
async def get_subtree(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.read")),
):
    """Return the subtree rooted at the given org."""
    result = await organization_service.get_subtree(db, org_id)
    return _build_response(0, "success", result)


@router.post("")
async def create_org(
    body: OrgCreate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.write")),
):
    """Create a new organization node."""
    node = await organization_service.create_org(db, body, operator_id=_operator_id(admin))
    return _build_response(0, "success", organization_service._org_to_dict(node))


@router.put("/{org_id}")
async def update_org(
    org_id: int,
    body: OrgUpdate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.write")),
):
    """Update an organization node (name/type/sort/status)."""
    node = await organization_service.update_org(db, org_id, body, operator_id=_operator_id(admin))
    return _build_response(0, "success", organization_service._org_to_dict(node))


@router.delete("/{org_id}")
async def delete_org(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.write")),
):
    """Delete an org (rejected if it has children or distributors)."""
    await organization_service.delete_org(db, org_id, operator_id=_operator_id(admin))
    return _build_response(0, "success", None)


@router.post("/{org_id}/migrate")
async def migrate_branch(
    org_id: int,
    body: OrgMigrateRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.write")),
):
    """Migrate an org subtree under a new parent."""
    result = await organization_service.migrate_branch(db, org_id, body, operator_id=_operator_id(admin))
    return _build_response(0, "success", result)


@router.get("/{org_id}/history")
async def get_history(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.read")),
):
    """Return operation history for an org."""
    result = await organization_service.get_history(db, org_id)
    return _build_response(0, "success", {"items": result})
