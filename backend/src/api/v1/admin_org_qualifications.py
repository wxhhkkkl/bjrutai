"""Admin organization qualification endpoints (US2).

List/upload require ``org.read`` / ``org.write``; review requires
``qualifications.write`` (复用资质审核权限).
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...schemas.org_qualification import (
    OrgQualificationCreate,
    OrgQualificationReview,
)
from ...services import org_qualification_service

router = APIRouter(prefix="/admin", tags=["admin-org-qualifications"])


def _operator_id(payload: dict) -> Optional[int]:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


@router.get("/orgs/{org_id}/qualifications")
async def list_qualifications(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.read")),
):
    """List org qualifications (latest first)."""
    result = await org_qualification_service.list_qualifications(db, org_id)
    return _build_response(0, "success", {"items": result})


@router.post("/orgs/{org_id}/qualifications")
async def create_qualification(
    org_id: int,
    body: OrgQualificationCreate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.write")),
):
    """Upload a new org qualification."""
    result = await org_qualification_service.create_qualification(
        db, org_id, body, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.post("/org-qualifications/{qualification_id}/review")
async def review_qualification(
    qualification_id: int,
    body: OrgQualificationReview,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("qualifications.write")),
):
    """Approve or reject an org qualification."""
    result = await org_qualification_service.review_qualification(
        db, qualification_id, body, reviewer_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.get("/orgs/{org_id}/qualifications/history")
async def get_history(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.read")),
):
    """Return qualification submission/review history for an org."""
    result = await org_qualification_service.get_history(db, org_id)
    return _build_response(0, "success", {"items": result})
