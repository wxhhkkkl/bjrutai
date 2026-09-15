"""Public article endpoints (US9).

Public endpoints return only published articles. No authentication required.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import NotFoundException
from ...models.category import ArticleCategory
from ...schemas.article import ArticleListResponse
from ...services.article_service import get_detail, list_public

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("/categories")
async def list_article_categories(
    db: AsyncSession = Depends(get_db),
):
    """List the managed article categories used by the public article filter."""
    result = await db.execute(
        select(ArticleCategory).order_by(ArticleCategory.sort_order, ArticleCategory.id)
    )
    categories = result.scalars().all()
    return _build_response(0, "success", {
        "items": [{"id": str(category.id), "name": category.name} for category in categories]
    })


@router.get("")
async def list_articles(
    category: str | None = Query(None, max_length=50, description="Category filter"),
    keyword: str | None = Query(None, max_length=100, description="Search title or summary"),
    cursor: str | None = Query(None, max_length=256, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
):
    """List published articles. Supports category filter, keyword search, and cursor pagination."""
    result = await list_public(
        db, category=category, keyword=keyword, cursor=cursor, page_size=limit
    )
    return _build_response(0, "success", result)


@router.get("/{article_id}")
async def get_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a published article by ID. Increments view count."""
    result = await get_detail(db, article_id, public_only=True)
    return _build_response(0, "success", result)
