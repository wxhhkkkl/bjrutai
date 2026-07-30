"""Qualification upload and review endpoints (US2).

Promoter-facing endpoints for uploading files and managing qualification records.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ..deps import get_current_user
from ...schemas.qualification import (
    DraftRequest,
    QualificationCreate,
    QualificationUpdate,
    UploadTokenRequest,
    get_status_label,
)
from ...services import qualification_service

router = APIRouter(tags=["qualifications"])


# ──────────────────────────────────────────────────────────────────
# POST /qualification-files/upload-token
# ──────────────────────────────────────────────────────────────────
@router.post("/qualification-files/upload-token")
async def get_upload_token(
    data: UploadTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Generate a COS pre-signed upload URL for a qualification file.

    Validates file type (JPG/PNG/PDF) and size (max 10MB).
    Returns a fileId, uploadUrl, and expiry time.
    """
    user_id = int(current_user["sub"])
    result = await qualification_service.get_upload_token(
        user_id=user_id,
        file_name=data.fileName,
        content_type=data.fileType,
        file_size=data.fileSize,
    )
    return _build_response(0, "success", result)


# ──────────────────────────────────────────────────────────────────
# POST /qualifications (submit)
# ──────────────────────────────────────────────────────────────────
@router.post("/qualifications")
async def submit_qualification(
    data: QualificationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Submit a qualification record for admin review.

    After submission, the qualification enters 'reviewing' status and
    triggers admin notification.
    """
    user_id = int(current_user["sub"])
    qualification = await qualification_service.submit_qualification(db, user_id, data)

    return _build_response(
        0,
        "success",
        {
            "qualificationId": str(qualification.id),
            "status": qualification.status.value if hasattr(qualification.status, "value") else str(qualification.status),
            "statusLabel": get_status_label(
                qualification.status.value if hasattr(qualification.status, "value") else str(qualification.status)
            ),
            "submittedAt": qualification.submitted_at.isoformat() if qualification.submitted_at else None,
        },
    )


# ──────────────────────────────────────────────────────────────────
# GET /qualifications/current
# ──────────────────────────────────────────────────────────────────
@router.get("/qualifications/current")
async def get_current_qualifications(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's qualification records.

    Returns all qualifications (draft, reviewing, approved, rejected, etc.).
    """
    user_id = int(current_user["sub"])
    result = await qualification_service.get_current(db, user_id)
    return _build_response(0, "success", result)


# ──────────────────────────────────────────────────────────────────
# PUT /qualifications/{id}
# ──────────────────────────────────────────────────────────────────
@router.put("/qualifications/{qualification_id}")
async def update_qualification(
    qualification_id: int,
    data: QualificationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update and resubmit a qualification (only rejected or draft records).

    Uses optimistic locking via the version field.
    """
    user_id = int(current_user["sub"])
    qualification = await qualification_service.update_qualification(
        db, user_id, qualification_id, data
    )

    return _build_response(
        0,
        "success",
        {
            "qualificationId": str(qualification.id),
            "status": qualification.status.value if hasattr(qualification.status, "value") else str(qualification.status),
            "statusLabel": get_status_label(
                qualification.status.value if hasattr(qualification.status, "value") else str(qualification.status)
            ),
            "submittedAt": qualification.submitted_at.isoformat() if qualification.submitted_at else None,
        },
    )


# ──────────────────────────────────────────────────────────────────
# GET /qualifications/{id}/reviews
# ──────────────────────────────────────────────────────────────────
@router.get("/qualifications/{qualification_id}/reviews")
async def get_qualification_reviews(
    qualification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the review history for a qualification record."""
    user_id = int(current_user["sub"])
    result = await qualification_service.get_reviews(db, user_id, qualification_id)
    return _build_response(0, "success", result)


# ──────────────────────────────────────────────────────────────────
# POST /qualifications/draft
# ──────────────────────────────────────────────────────────────────
@router.post("/qualifications/draft")
async def save_qualification_draft(
    data: DraftRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Save a qualification draft (does not trigger review).

    Creates or updates a draft. All fields are optional.
    """
    user_id = int(current_user["sub"])
    draft = await qualification_service.save_draft(db, user_id, data)

    return _build_response(
        0,
        "success",
        {
            "qualificationId": str(draft.id),
            "status": draft.status.value if hasattr(draft.status, "value") else str(draft.status),
            "statusLabel": get_status_label(
                draft.status.value if hasattr(draft.status, "value") else str(draft.status)
            ),
            "savedAt": draft.updated_at.isoformat() if draft.updated_at else None,
        },
    )
