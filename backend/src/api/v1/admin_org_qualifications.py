"""Admin organization qualification endpoints (US2).

List/upload require ``org.read`` / ``org.write``; review requires
``qualifications.write`` (复用资质审核权限).
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...integrations.cos_client import get_cos_client
from ...schemas.org_qualification import (
    OrgQualificationCreate,
    OrgQualificationReview,
)
from ...services import org_qualification_service

router = APIRouter(prefix="/admin", tags=["admin-org-qualifications"])


class QualUploadTokenRequest(BaseModel):
    fileName: str = Field(..., min_length=1, max_length=255)
    contentType: str = Field(..., min_length=1, max_length=100)
    fileSize: int = Field(..., ge=1)


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


@router.post("/org-qualifications/upload-token")
async def upload_qualification_token(
    body: QualUploadTokenRequest,
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("org.write")),
):
    """Generate a pre-signed COS upload URL for an org qualification file."""
    from ...core.exceptions import BadRequestException

    client = get_cos_client()
    try:
        result = client.generate_upload_token(
            user_id=_operator_id(admin) or 0,
            file_name=body.fileName,
            content_type=body.contentType,
            file_size=body.fileSize,
            key_prefix="qualifications/",
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc))
    return _build_response(0, "success", result)


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
