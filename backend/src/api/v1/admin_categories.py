"""Article category CRUD endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import ConflictException, NotFoundException
from ...api.deps import get_admin_user, require_permission
from ...models.article import Article
from ...models.category import ArticleCategory

router = APIRouter(prefix="/admin/categories", tags=["admin-categories"])


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    sort_order: int = Field(0)


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    sort_order: int | None = None


@router.get("")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _perm: dict = Depends(require_permission("articles.read")),
) -> dict:
    result = await db.execute(
        select(ArticleCategory).order_by(ArticleCategory.sort_order)
    )
    categories = result.scalars().all()
    items = [{"id": str(c.id), "name": c.name, "sort_order": c.sort_order,
              "created_at": c.created_at.isoformat() if c.created_at else None}
             for c in categories]
    return _build_response(0, "success", {"items": items})


@router.post("")
async def create_category(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _perm: dict = Depends(require_permission("articles.write")),
) -> dict:
    existing = await db.execute(
        select(ArticleCategory).where(ArticleCategory.name == body.name))
    if existing.scalars().first():
        raise ConflictException(message="分类名称已存在", code=40901)

    cat = ArticleCategory(name=body.name, sort_order=body.sort_order)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return _build_response(0, "success", {"id": str(cat.id), "name": cat.name})


@router.put("/{category_id}")
async def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _perm: dict = Depends(require_permission("articles.write")),
) -> dict:
    result = await db.execute(
        select(ArticleCategory).where(ArticleCategory.id == category_id))
    cat = result.scalars().first()
    if cat is None:
        raise NotFoundException(message="分类不存在")

    if body.name is not None:
        existing = await db.execute(
            select(ArticleCategory).where(ArticleCategory.name == body.name))
        if existing.scalars().first() and body.name != cat.name:
            raise ConflictException(message="分类名称已存在", code=40901)
        cat.name = body.name
    if body.sort_order is not None:
        cat.sort_order = body.sort_order

    db.add(cat)
    await db.commit()
    return _build_response(0, "success", {"id": str(cat.id), "name": cat.name})


@router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _perm: dict = Depends(require_permission("articles.write")),
) -> dict:
    result = await db.execute(
        select(ArticleCategory).where(ArticleCategory.id == category_id))
    cat = result.scalars().first()
    if cat is None:
        raise NotFoundException(message="分类不存在")

    # Check if articles reference this category
    usage = await db.execute(
        select(func.count()).select_from(Article).where(
            Article.category_id == category_id))
    count = usage.scalar() or 0
    if count > 0:
        raise ConflictException(
            message=f"该分类下有 {count} 篇文章，无法删除", code=40902)

    await db.delete(cat)
    await db.commit()
    return _build_response(0, "success", None)
