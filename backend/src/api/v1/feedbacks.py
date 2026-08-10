"""Authenticated mini-program feedback APIs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.error_handler import _build_response
from ...integrations.cos_client import COSClient, get_cos_client
from ...schemas.feedback import FeedbackCreateRequest, FeedbackUploadTokenRequest
from ...services.feedback_service import (
    create_feedback,
    list_current_feedbacks,
    serialize_submission,
)

router = APIRouter(prefix="/feedbacks", tags=["feedbacks"])
feedback_files_router = APIRouter(prefix="/feedback-files", tags=["feedback-files"])


@feedback_files_router.post("/upload-token")
async def get_feedback_file_upload_token(
    body: FeedbackUploadTokenRequest,
    payload: dict = Depends(get_current_user),
) -> dict:
    """Issue a screenshot-only COS PUT token for the current user."""
    cos: COSClient = get_cos_client()
    try:
        token = cos.generate_feedback_upload_token(
            user_id=int(payload["sub"]),
            file_name=body.fileName,
            content_type=body.contentType,
            file_size=body.fileSize,
        )
    except ValueError as exc:
        from ...core.exceptions import BadRequestException

        raise BadRequestException(message=str(exc))
    return _build_response(0, "success", token)


@router.post("")
async def submit_feedback(
    body: FeedbackCreateRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    feedback = await create_feedback(
        db,
        user_id=int(payload["sub"]),
        data=body,
        idempotency_key=idempotency_key or "",
        cos=get_cos_client(),
    )
    return _build_response(0, "success", serialize_submission(feedback))


@router.get("")
async def list_feedbacks(
    status: str | None = Query(None),
    cursor: str | None = Query(None),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    result = await list_current_feedbacks(
        db, user_id=int(payload["sub"]), status=status, cursor=cursor, page_size=pageSize
    )
    return _build_response(0, "success", result)
