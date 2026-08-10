"""RBAC-protected feedback management APIs for the admin application."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db, require_permission
from ...core.error_handler import _build_response
from ...integrations.cos_client import get_cos_client
from ...schemas.feedback import FeedbackAdminUpdateRequest
from ...services.feedback_service import (
    get_admin_feedback,
    list_admin_feedbacks,
    update_admin_feedback,
)
from ...tasks.feedback_tasks import attempt_feedback_notification

router = APIRouter(prefix="/admin/feedbacks", tags=["admin-feedbacks"])


@router.get("")
async def list_feedbacks(
    status: str | None = Query(None, pattern="^(submitted|processing|resolved)$"),
    type: str | None = Query(None, pattern="^(bug|suggestion|other)$"),
    keyword: str | None = Query(None, max_length=100),
    submittedFrom: datetime | None = Query(None),
    submittedTo: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_permission("feedbacks.read")),
) -> dict:
    if submittedFrom and submittedTo and submittedTo < submittedFrom:
        from ...core.exceptions import ValidationException

        raise ValidationException(message="submittedTo 不得早于 submittedFrom")
    result = await list_admin_feedbacks(
        db,
        status=status,
        type_=type,
        keyword=keyword,
        submitted_from=submittedFrom,
        submitted_to=submittedTo,
        page=page,
        page_size=pageSize,
    )
    return _build_response(0, "success", result)


@router.get("/{feedback_no}")
async def get_feedback(
    feedback_no: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_permission("feedbacks.read")),
) -> dict:
    result = await get_admin_feedback(
        db, feedback_no=feedback_no, cos=get_cos_client(), viewer_admin_id=int(admin["sub"])
    )
    return _build_response(0, "success", result)


@router.patch("/{feedback_no}")
async def update_feedback(
    feedback_no: str,
    body: FeedbackAdminUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_permission("feedbacks.write")),
) -> dict:
    feedback = await update_admin_feedback(
        db, feedback_no=feedback_no, data=body, admin_id=int(admin["sub"])
    )
    if feedback.status == "resolved" and feedback.notification_status == "pending":
        await attempt_feedback_notification(db, feedback)
    result = await get_admin_feedback(
        db,
        feedback_no=feedback.feedback_no,
        cos=get_cos_client(),
        viewer_admin_id=int(admin["sub"]),
    )
    return _build_response(0, "success", result)
