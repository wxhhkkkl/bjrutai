"""Article service layer -- business logic for article CRUD and state transitions."""
import base64
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, ConflictException, NotFoundException
from ..models.article import Article, ArticleStatus
from ..schemas.article import ArticleCreate, ArticleUpdate

STATUS_LABELS = {
    ArticleStatus.DRAFT: "draft_label",
    ArticleStatus.PUBLISHED: "published_label",
    ArticleStatus.UNPUBLISHED: "unpublished_label",
}


def _encode_cursor(id_value: int) -> str:
    """Encode an article ID as a base64 cursor string."""
    return base64.urlsafe_b64encode(str(id_value).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int | None:
    """Decode a base64 cursor string back to an article ID."""
    if not cursor:
        return None
    try:
        # Add padding if needed
        padding = 4 - len(cursor) % 4
        if padding != 4:
            cursor += "=" * padding
        return int(base64.urlsafe_b64decode(cursor).decode())
    except Exception:
        return None


# ============================================================================
# Public-facing queries
# ============================================================================
async def list_public(
    db: AsyncSession,
    *,
    category: str | None = None,
    keyword: str | None = None,
    cursor: str | None = None,
    page_size: int = 20,
) -> dict:
    """List published articles with optional filters and cursor pagination."""
    page_size = max(1, min(page_size, 100))

    stmt = select(Article).where(Article.status == ArticleStatus.PUBLISHED)

    if category:
        stmt = stmt.where(Article.category == category)

    if keyword:
        like_pattern = f"%{keyword}%"
        stmt = stmt.where(
            (Article.title.ilike(like_pattern)) | (Article.summary.ilike(like_pattern))
        )

    # Cursor pagination: cursor is the ID of the last item from the previous page
    cursor_id = _decode_cursor(cursor)
    if cursor_id is not None:
        # Get the published_at of the cursor article for tie-breaking
        cursor_stmt = select(Article.published_at).where(Article.id == cursor_id)
        cursor_result = await db.execute(cursor_stmt)
        cursor_published_at = cursor_result.scalar()
        if cursor_published_at is not None:
            stmt = stmt.where(
                (Article.published_at < cursor_published_at)
                | (
                    (Article.published_at == cursor_published_at)
                    & (Article.id < cursor_id)
                )
            )
        else:
            stmt = stmt.where(Article.id < cursor_id)

    stmt = stmt.order_by(Article.published_at.desc(), Article.id.desc())
    stmt = stmt.limit(page_size + 1)  # fetch one extra to determine hasMore

    result = await db.execute(stmt)
    rows = list(result.scalars())

    has_more = len(rows) > page_size
    if has_more:
        rows = rows[:page_size]

    next_cursor = _encode_cursor(rows[-1].id) if rows and has_more else None

    items = [_article_to_public_item(a) for a in rows]

    return {"items": items, "nextCursor": next_cursor, "hasMore": has_more}


async def get_detail(db: AsyncSession, article_id: int, public_only: bool = True) -> dict:
    """Get a single article detail. If public_only, only published articles are visible."""
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()

    if article is None:
        raise NotFoundException(message="Article not found")

    if public_only and article.status != ArticleStatus.PUBLISHED:
        raise NotFoundException(message="Article not found")

    # Increment view count
    article.view_count += 1
    await db.flush()

    return _article_to_detail(article)


# ============================================================================
# Admin queries
# ============================================================================
async def list_admin(
    db: AsyncSession,
    *,
    status: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    cursor: str | None = None,
    page_size: int = 20,
) -> dict:
    """List all articles for admin with filters and cursor pagination."""
    page_size = max(1, min(page_size, 100))

    stmt = select(Article)

    if status:
        try:
            stmt = stmt.where(Article.status == ArticleStatus(status))
        except ValueError:
            raise BadRequestException(message=f"Invalid status: {status}")

    if category:
        stmt = stmt.where(Article.category == category)

    if keyword:
        like_pattern = f"%{keyword}%"
        stmt = stmt.where(Article.title.ilike(like_pattern))

    # Cursor pagination: sorted by updated_at desc, then id desc
    cursor_id = _decode_cursor(cursor)
    if cursor_id is not None:
        cursor_stmt = select(Article.updated_at).where(Article.id == cursor_id)
        cursor_result = await db.execute(cursor_stmt)
        cursor_updated_at = cursor_result.scalar()
        if cursor_updated_at is not None:
            stmt = stmt.where(
                (Article.updated_at < cursor_updated_at)
                | (
                    (Article.updated_at == cursor_updated_at)
                    & (Article.id < cursor_id)
                )
            )
        else:
            stmt = stmt.where(Article.id < cursor_id)

    stmt = stmt.order_by(Article.updated_at.desc(), Article.id.desc())
    stmt = stmt.limit(page_size + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars())

    has_more = len(rows) > page_size
    if has_more:
        rows = rows[:page_size]

    next_cursor = _encode_cursor(rows[-1].id) if rows and has_more else None

    items = [_article_to_admin_item(a) for a in rows]

    return {"items": items, "nextCursor": next_cursor, "hasMore": has_more}


async def get_admin_detail(db: AsyncSession, article_id: int) -> Article:
    """Get article for admin operations (any status). Raises NotFound if missing."""
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if article is None:
        raise NotFoundException(message="Article not found")
    return article


# ============================================================================
# Admin mutations
# ============================================================================
async def create_article(db: AsyncSession, data: ArticleCreate, author_name: str | None = None) -> Article:
    """Create a new article in draft status."""
    article = Article(
        title=data.title,
        summary=data.summary,
        content=data.content or "",
        cover_url=data.coverImageUrl,
        category=data.category,
        tags=data.tags,
        status=ArticleStatus.DRAFT,
        author_name=author_name,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)
    return article


async def update_article(
    db: AsyncSession, article_id: int, data: ArticleUpdate
) -> Article:
    """Update an article with optimistic locking."""
    article = await get_admin_detail(db, article_id)

    # Check version for optimistic locking
    if data.version != article.version:
        raise ConflictException(
            message="Version conflict: the article has been modified by another user",
            detail={"currentVersion": article.version, "providedVersion": data.version},
        )

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True, by_alias=False)
    # Remove version from update data (handled separately)
    update_data.pop("version", None)

    # Map schema field names to model column names
    field_mapping = {
        "coverImageUrl": "cover_url",
    }

    for key, value in update_data.items():
        db_key = field_mapping.get(key, key)
        if hasattr(article, db_key):
            setattr(article, db_key, value)

    article.version += 1
    article.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(article)
    return article


async def publish_article(db: AsyncSession, article_id: int) -> Article:
    """Publish an article (draft or unpublished -> published)."""
    article = await get_admin_detail(db, article_id)

    if article.status == ArticleStatus.PUBLISHED:
        raise BadRequestException(message="Article is already published")

    article.status = ArticleStatus.PUBLISHED
    article.published_at = datetime.now(timezone.utc)
    article.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(article)
    return article


async def unpublish_article(db: AsyncSession, article_id: int) -> Article:
    """Unpublish an article (published -> unpublished)."""
    article = await get_admin_detail(db, article_id)

    if article.status != ArticleStatus.PUBLISHED:
        raise BadRequestException(message="Article is not published")

    article.status = ArticleStatus.UNPUBLISHED
    article.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(article)
    return article


# ============================================================================
# Serialization helpers
# ============================================================================
def _status_label(status: ArticleStatus) -> str:
    """Return a human-readable label for the article status."""
    labels = {
        ArticleStatus.DRAFT: "Draft",
        ArticleStatus.PUBLISHED: "Published",
        ArticleStatus.UNPUBLISHED: "Unpublished",
    }
    return labels.get(status, status.value)


def _article_to_public_item(article: Article) -> dict:
    """Serialize an article to a public list item."""
    return {
        "articleId": str(article.id),
        "title": article.title,
        "summary": article.summary,
        "coverImageUrl": article.cover_url,
        "category": article.category,
        "author": article.author_name,
        "viewCount": article.view_count,
        "publishedAt": article.published_at.isoformat() if article.published_at else None,
    }


def _article_to_detail(article: Article) -> dict:
    """Serialize an article to full detail."""
    return {
        "articleId": str(article.id),
        "title": article.title,
        "summary": article.summary,
        "content": article.content,
        "coverImageUrl": article.cover_url,
        "category": article.category,
        "tags": article.tags or [],
        "author": article.author_name,
        "viewCount": article.view_count,
        "status": article.status.value,
        "publishedAt": article.published_at.isoformat() if article.published_at else None,
        "createdAt": article.created_at.isoformat() if article.created_at else None,
        "updatedAt": article.updated_at.isoformat() if article.updated_at else None,
    }


def _article_to_admin_item(article: Article) -> dict:
    """Serialize an article to an admin list item."""
    return {
        "articleId": str(article.id),
        "title": article.title,
        "summary": article.summary,
        "category": article.category,
        "status": article.status.value,
        "statusLabel": _status_label(article.status),
        "author": article.author_name,
        "viewCount": article.view_count,
        "publishedAt": article.published_at.isoformat() if article.published_at else None,
        "createdAt": article.created_at.isoformat() if article.created_at else None,
        "updatedAt": article.updated_at.isoformat() if article.updated_at else None,
        "version": article.version,
    }
