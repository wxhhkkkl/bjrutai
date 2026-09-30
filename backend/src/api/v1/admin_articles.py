"""Admin article management endpoints (US9).

All endpoints require admin authentication.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import ForbiddenException
from ...schemas.article import (
    ArticleCreate,
    ArticleCreateResponse,
    ArticlePublishResponse,
    ArticleUnpublishResponse,
    ArticleUpdate,
    ArticleUpdateResponse,
)
from ...services.article_service import (
    create_article,
    delete_article,
    get_admin_detail,
    list_admin,
    publish_article,
    unpublish_article,
    update_article,
)
from ..deps import get_admin_user, require_permission

router = APIRouter(prefix="/admin/articles", tags=["admin-articles"])


@router.get("")
async def admin_list_articles(
    status: str | None = Query(
        None, pattern="^(draft|published|unpublished)$", description="Filter by status"
    ),
    category: str | None = Query(None, max_length=50, description="Filter by category"),
    keyword: str | None = Query(None, max_length=100, description="Search title"),
    cursor: str | None = Query(None, max_length=256, description="Pagination cursor"),
    page: int | None = Query(None, ge=1, description="Page number for numbered pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """List admin articles with filters and either numbered or cursor pagination."""
    result = await list_admin(
        db,
        status=status,
        category=category,
        keyword=keyword,
        cursor=cursor,
        page=page,
        page_size=limit,
    )
    return _build_response(0, "success", result)


@router.post("")
async def admin_create_article(
    data: ArticleCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(get_admin_user),
):
    """Create a new article. New articles start in draft status."""
    author_name = current_admin.get("sub", "admin")
    if data.videoId is not None and "articles.write" not in current_admin.get("permissions", []):
        raise ForbiddenException(message="缺少权限: articles.write")
    article = await create_article(
        db, data, author_name=author_name, admin_id=int(current_admin["sub"])
    )
    return _build_response(
        0,
        "success",
        {
            "articleId": str(article.id),
            "title": article.title,
            "status": article.status.value,
            "statusLabel": "Draft",
            "createdAt": article.created_at.isoformat() if article.created_at else None,
        },
    )


@router.put("/{article_id}")
async def admin_update_article(
    article_id: int,
    data: ArticleUpdate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Update an article. Uses optimistic locking via the version field."""
    if "videoId" in data.model_fields_set and "articles.write" not in _current_admin.get(
        "permissions", []
    ):
        existing = await get_admin_detail(db, article_id)
        if existing.video_id != (int(data.videoId) if data.videoId else None):
            raise ForbiddenException(message="缺少权限: articles.write")
    article = await update_article(db, article_id, data, admin_id=int(_current_admin["sub"]))
    return _build_response(
        0,
        "success",
        {
            "articleId": str(article.id),
            "title": article.title,
            "status": article.status.value,
            "statusLabel": _status_label(article.status),
            "updatedAt": article.updated_at.isoformat() if article.updated_at else None,
        },
    )


@router.post("/{article_id}/publish")
async def admin_publish_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Publish an article. Transitions from draft or unpublished to published."""
    article = await publish_article(db, article_id)
    return _build_response(
        0,
        "success",
        {
            "articleId": str(article.id),
            "status": article.status.value,
            "statusLabel": "Published",
            "publishedAt": article.published_at.isoformat() if article.published_at else None,
        },
    )


@router.post("/{article_id}/unpublish")
async def admin_unpublish_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Unpublish an article. Transitions from published to unpublished."""
    article = await unpublish_article(db, article_id)
    return _build_response(
        0,
        "success",
        {
            "articleId": str(article.id),
            "status": article.status.value,
            "statusLabel": "Unpublished",
            "unpublishedAt": article.updated_at.isoformat() if article.updated_at else None,
        },
    )


@router.delete("/{article_id}")
async def admin_delete_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    _perm: dict = Depends(require_permission("articles.write")),
):
    """Permanently delete an unpublished article and all of its comments."""
    result = await delete_article(db, article_id)
    return _build_response(0, "success", result)


def _status_label(status) -> str:
    from ...models.article import ArticleStatus

    labels = {
        ArticleStatus.DRAFT: "Draft",
        ArticleStatus.PUBLISHED: "Published",
        ArticleStatus.UNPUBLISHED: "Unpublished",
    }
    return labels.get(status, status.value)
