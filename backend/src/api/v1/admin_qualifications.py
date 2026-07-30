"""Admin qualification review endpoints (US2).

All endpoints require admin authentication.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ..deps import get_admin_user
from ...schemas.qualification import ReviewRequest, get_status_label
from ...services import qualification_service

router = APIRouter(prefix="/admin/qualifications", tags=["admin-qualifications"])


# ──────────────────────────────────────────────────────────────────
# GET /admin/qualifications
# ──────────────────────────────────────────────────────────────────
@router.get("")
async def list_qualifications(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Admin: list qualification records. Defaults to 'reviewing' status."""
    result = await qualification_service.list_pending(db, status_filter=status)
    return _build_response(0, "success", result)


# ──────────────────────────────────────────────────────────────────
# POST /admin/qualifications/{id}/review
# ──────────────────────────────────────────────────────────────────
@router.post("/{qualification_id}/review")
async def review_qualification(
    qualification_id: int,
    data: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(get_admin_user),
):
    """Admin: approve or reject a qualification record.

    Approving activates the promoter, enabling promotion code generation.
    """
    admin_id = int(current_admin["sub"])
    qual = await qualification_service.admin_review(db, qualification_id, data, admin_id)

    return _build_response(
        0,
        "success",
        {
            "qualificationId": str(qual.id),
            "status": qual.status.value if hasattr(qual.status, "value") else str(qual.status),
            "statusLabel": get_status_label(
                qual.status.value if hasattr(qual.status, "value") else str(qual.status)
            ),
            "reviewedAt": qual.updated_at.isoformat() if qual.updated_at else None,
        },
    )
