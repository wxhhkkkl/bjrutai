"""RBAC-protected comment management APIs for the admin application."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db, require_permission
from ...core.error_handler import _build_response
from ...schemas.comment import AdminCommentActionRequest
from ...services.comment_service import (
    get_admin_comment_detail,
    list_admin_comments,
    update_admin_comment,
)
router = APIRouter(prefix="/admin/comments", tags=["admin-comments"])


@router.get("")
async def list_comments(
    articleId: int | None = Query(None, ge=1),
    status: str | None = Query(None),
    keyword: str | None = Query(None, max_length=100),
    createdFrom: datetime | None = Query(None),
    createdTo: datetime | None = Query(None),
    cursor: str | None = Query(None, max_length=512),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_permission("comments.read")),
):
    result = await list_admin_comments(
        db,
        article_id=articleId,
        status=status,
        keyword=keyword,
        created_from=createdFrom,
        created_to=createdTo,
        cursor=cursor,
        limit=limit,
    )
    return _build_response(0, "success", result)


@router.get("/{comment_id}")
async def get_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_permission("comments.read")),
):
    result = await get_admin_comment_detail(db, comment_id=comment_id)
    return _build_response(0, "success", result)


@router.patch("/{comment_id}")
async def update_comment(
    comment_id: int,
    body: AdminCommentActionRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_permission("comments.write")),
):
    result = await update_admin_comment(
        db,
        comment_id=comment_id,
        action=body.action,
        expected_version=body.expectedVersion,
        admin_id=int(admin["sub"]),
        reason=body.reason,
    )
    return _build_response(0, "success", result)
