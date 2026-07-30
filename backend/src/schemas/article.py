"""Pydantic schemas for Article requests and responses."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class ArticleCreate(BaseModel):
    """Schema for creating a new article (admin only)."""

    title: str = Field(..., min_length=2, max_length=200, description="Article title")
    summary: Optional[str] = Field(None, max_length=500, description="Article summary/excerpt")
    content: Optional[str] = Field(
        None, max_length=100_000, description="Article body (HTML)"
    )
    coverImageUrl: Optional[str] = Field(
        None, max_length=2048, alias="coverImageUrl", description="Cover image URL"
    )
    category: Optional[str] = Field(None, max_length=50, description="Category")
    tags: Optional[list[str]] = Field(
        None, max_length=20, description="Tags (max 20 items, each max 30 chars)"
    )

    class Config:
        populate_by_name = True


class ArticleUpdate(BaseModel):
    """Schema for updating an existing article (admin only)."""

    title: Optional[str] = Field(None, min_length=2, max_length=200, description="Article title")
    summary: Optional[str] = Field(None, max_length=500, description="Article summary/excerpt")
    content: Optional[str] = Field(
        None, max_length=100_000, description="Article body (HTML)"
    )
    coverImageUrl: Optional[str] = Field(
        None, max_length=2048, alias="coverImageUrl", description="Cover image URL"
    )
    category: Optional[str] = Field(None, max_length=50, description="Category")
    tags: Optional[list[str]] = Field(
        None, max_length=20, description="Tags (max 20 items, each max 30 chars)"
    )
    version: int = Field(..., ge=1, description="Current version for optimistic locking")

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class ArticleResponse(BaseModel):
    """Public / detail response for a single article."""

    articleId: str
    title: str
    summary: Optional[str] = None
    content: Optional[str] = None
    coverImageUrl: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    author: Optional[str] = None
    viewCount: int = 0
    status: str
    publishedAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    version: Optional[int] = None

    class Config:
        from_attributes = True


class ArticleListResponse(BaseModel):
    """Cursor-paginated list of articles."""

    items: list[ArticleResponse]
    nextCursor: Optional[str] = None
    hasMore: bool = False


# ---------------------------------------------------------------------------
# Admin-specific response (includes version for optimistic locking)
# ---------------------------------------------------------------------------
class AdminArticleItem(BaseModel):
    """Single article item in admin listing."""

    articleId: str
    title: str
    summary: Optional[str] = None
    category: Optional[str] = None
    status: str
    statusLabel: str
    author: Optional[str] = None
    viewCount: int = 0
    publishedAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    version: int = 1

    class Config:
        from_attributes = True


class AdminArticleListResponse(BaseModel):
    """Cursor-paginated admin article list."""

    items: list[AdminArticleItem]
    nextCursor: Optional[str] = None
    hasMore: bool = False


class ArticleCreateResponse(BaseModel):
    """Response after creating an article."""

    articleId: str
    title: str
    status: str
    statusLabel: str
    createdAt: Optional[datetime] = None


class ArticleUpdateResponse(BaseModel):
    """Response after updating an article."""

    articleId: str
    title: str
    status: str
    statusLabel: str
    updatedAt: Optional[datetime] = None


class ArticlePublishResponse(BaseModel):
    """Response after publishing an article."""

    articleId: str
    status: str
    statusLabel: str
    publishedAt: Optional[datetime] = None


class ArticleUnpublishResponse(BaseModel):
    """Response after unpublishing an article."""

    articleId: str
    status: str
    statusLabel: str
    unpublishedAt: Optional[datetime] = None
