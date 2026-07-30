"""Feedback endpoints (T174).

POST /feedback-files/upload-token – upload token for feedback screenshot
POST /feedbacks                  – submit feedback
GET  /feedbacks                  – list feedback records
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.exceptions import BadRequestException
from ...integrations.cos_client import COSClient, get_cos_client
from ...models.audit import AuditLog

router = APIRouter(prefix="/feedbacks", tags=["feedbacks"])
feedback_files_router = APIRouter(prefix="/feedback-files", tags=["feedback-files"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────
class UploadTokenRequest(BaseModel):
    fileName: str = Field(..., min_length=1, max_length=255)
    contentType: str = Field(..., min_length=1)
    fileSize: int = Field(..., gt=0, le=10 * 1024 * 1024)


class FeedbackCreateRequest(BaseModel):
    type: str = Field(..., description="bug, feature, suggestion, other")
    content: str = Field(..., min_length=1, max_length=5000)
    imageFiles: Optional[list[str]] = Field(None, description="List of COS file keys")
    contactAllowed: bool = False


# ──────────────────────────────────────────────────────────────────
# POST /feedback-files/upload-token
# ──────────────────────────────────────────────────────────────────
@feedback_files_router.post("/upload-token")
async def get_feedback_file_upload_token(
    body: UploadTokenRequest,
    payload: dict = Depends(get_current_user),
) -> dict:
    """Generate a COS pre-signed upload URL for feedback screenshot."""
    user_id = int(payload["sub"])
    cos: COSClient = get_cos_client()

    try:
        upload_info = cos.generate_upload_token(
            user_id=user_id,
            file_name=body.fileName,
            content_type=body.contentType,
            file_size=body.fileSize,
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc))

    return _ok(upload_info)


# ──────────────────────────────────────────────────────────────────
# POST /feedbacks
# ──────────────────────────────────────────────────────────────────
@router.post("")
async def submit_feedback(
    body: FeedbackCreateRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Submit user feedback. Stored as an audit log entry for traceability."""
    user_id = int(payload["sub"])

    valid_types = {"bug", "feature", "suggestion", "other"}
    if body.type not in valid_types:
        raise BadRequestException(
            message=f"Invalid feedback type: {body.type}. Valid: {', '.join(valid_types)}"
        )

    audit = AuditLog(
        user_id=user_id,
        action="feedback_submit",
        entity_type=f"feedback_{body.type}",
        entity_id=uuid.uuid4().hex[:12],
        detail={
            "type": body.type,
            "content": body.content,
            "imageFiles": body.imageFiles or [],
            "contactAllowed": body.contactAllowed,
        },
    )
    db.add(audit)
    await db.commit()
    await db.refresh(audit)

    return _ok({
        "id": audit.entity_id,
        "type": body.type,
        "content": body.content,
        "status": "submitted",
        "submittedAt": audit.created_at.isoformat() if audit.created_at else None,
    })


# ──────────────────────────────────────────────────────────────────
# GET /feedbacks
# ──────────────────────────────────────────────────────────────────
@router.get("")
async def list_feedbacks(
    status: Optional[str] = Query(None, description="submitted, processing, resolved"),
    cursor: Optional[str] = Query(None),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """List feedback records for the current user."""
    user_id = int(payload["sub"])

    query = (
        select(AuditLog)
        .where(
            AuditLog.user_id == user_id,
            AuditLog.action == "feedback_submit",
        )
        .order_by(desc(AuditLog.id))
    )

    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.where(AuditLog.id < cursor_id)
        except (ValueError, TypeError):
            pass

    query = query.limit(pageSize + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > pageSize
    items = rows[:pageSize]
    next_cursor = str(items[-1].id) if has_more and items else None

    data_items = []
    for row in items:
        detail = row.detail or {}
        data_items.append({
            "id": row.entity_id or str(row.id),
            "type": detail.get("type", "unknown"),
            "content": detail.get("content", ""),
            "status": "submitted",
            "contactAllowed": detail.get("contactAllowed", False),
            "createdAt": row.created_at.isoformat() if row.created_at else None,
        })

    return _ok({
        "items": data_items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    })
