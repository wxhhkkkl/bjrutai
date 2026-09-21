"""Authenticated article comment and like APIs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.error_handler import _build_response
from ...schemas.comment import CommentCreateRequest
from ...services.comment_service import (
    create_comment,
    like_comment,
    list_visible_comments,
    unlike_comment,
)

router = APIRouter(prefix="/articles", tags=["article-comments"])


@router.get("/{article_id}/comments")
async def list_article_comments(
    article_id: int,
    cursor: str | None = Query(None, max_length=512),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    result = await list_visible_comments(
        db,
        article_id=article_id,
        user_id=int(payload["sub"]),
        cursor=cursor,
        limit=limit,
    )
    return _build_response(0, "success", result)


@router.post("/{article_id}/comments")
async def create_article_comment(
    article_id: int,
    body: CommentCreateRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    comment = await create_comment(
        db,
        article_id=article_id,
        user_id=int(payload["sub"]),
        content=body.content,
        idempotency_key=idempotency_key or "",
    )
    if comment.status == "visible":
        return _build_response(
            0,
            "评论已发布",
            {
                "commentId": str(comment.id),
                "status": comment.status,
                "moderationStatus": comment.moderation_status,
            },
        )
    return _build_response(
        0,
        "评论已提交，审核通过后展示",
        {
            "commentId": str(comment.id),
            "status": comment.status,
            "moderationStatus": "flagged",
        },
    )


@router.post("/{article_id}/comments/{comment_id}/like")
async def like_article_comment(
    article_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    result = await like_comment(
        db,
        article_id=article_id,
        comment_id=comment_id,
        user_id=int(payload["sub"]),
    )
    return _build_response(0, "success", result)


@router.delete("/{article_id}/comments/{comment_id}/like")
async def unlike_article_comment(
    article_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    result = await unlike_comment(
        db,
        article_id=article_id,
        comment_id=comment_id,
        user_id=int(payload["sub"]),
    )
    return _build_response(0, "success", result)
