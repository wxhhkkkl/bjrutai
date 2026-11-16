"""Public catalog returns only real on-sale products in enabled categories."""

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...core.error_handler import _build_response
from ...services import mall_catalog_query_service as queries
from ...services.mall_settings_service import get_mall_settings

router = APIRouter(prefix="/mall", tags=["mall-catalog"])


@router.get("/categories", operation_id="listMallCategories")
async def categories(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return _build_response(
        0,
        "success",
        await queries.list_categories(db, public=True, cursor=cursor, page_size=page_size),
    )


@router.get("/products", operation_id="listMallProducts")
async def products(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    category_id: int | None = Query(None, alias="categoryId", gt=0),
    q: str | None = Query(None, max_length=128),
    sort: Literal["default", "price_asc", "price_desc"] = "default",
    db: AsyncSession = Depends(get_db),
):
    return _build_response(
        0,
        "success",
        await queries.list_products(
            db,
            public=True,
            cursor=cursor,
            page_size=page_size,
            category_id=category_id,
            q=q,
            sort=sort,
        ),
    )


@router.get("/products/{productId}", operation_id="getMallProduct")
async def product(
    product_id: int = Path(alias="productId", gt=0), db: AsyncSession = Depends(get_db)
):
    value = await queries.get_product(db, product_id, public=True)
    result = await queries.serialize_product(db, value)
    instructions = value.return_instructions.strip()
    if not instructions:
        settings = await get_mall_settings(db)
        instructions = settings.return_instructions or ""
    result["returnInstructions"] = instructions
    return _build_response(0, "success", result)
