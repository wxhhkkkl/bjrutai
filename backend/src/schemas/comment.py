"""Pydantic contracts for mini-program and admin comment APIs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


CommentStatus = Literal["pending", "visible", "hidden", "rejected", "deleted"]
ModerationStatus = Literal["pending", "passed", "flagged", "rejected", "error"]
CommentActionType = Literal[
    "approve",
    "reject",
    "hide",
    "restore",
    "pin",
    "unpin",
    "delete",
]


class CommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("评论内容不能为空")
        return value


class CommentListItem(BaseModel):
    commentId: str
    displayName: str
    avatarUrl: str | None = None
    content: str
    isPinned: bool
    likeCount: int = Field(ge=0)
    liked: bool
    createdAt: datetime


class CommentPage(BaseModel):
    items: list[CommentListItem]
    nextCursor: str | None = None
    hasMore: bool
    total: int = Field(ge=0)


class CommentLikeResult(BaseModel):
    commentId: str
    liked: bool
    likeCount: int = Field(ge=0)


class AdminCommentActionRequest(BaseModel):
    action: CommentActionType
    expectedVersion: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class AdminCommentListItem(BaseModel):
    commentId: str
    articleId: str
    articleTitle: str
    displayName: str
    contentPreview: str
    status: CommentStatus
    moderationStatus: ModerationStatus
    moderationCategory: str | None = None
    isPinned: bool
    likeCount: int = Field(ge=0)
    createdAt: datetime
    updatedAt: datetime
    version: int = Field(ge=1)
