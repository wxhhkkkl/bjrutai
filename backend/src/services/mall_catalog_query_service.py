"""Catalog read projections, public visibility and stable cursor pagination."""

import base64
import json

from sqlalchemy import func, or_, select

from ..core.exceptions import NotFoundException, ValidationException
from ..models.mall_catalog import MallCategory, MallProduct, MallSku, MallStockMovement
from .mall_catalog_service import _get, _image, product_skus


def serialize_category(category):
    return {
        "id": str(category.id),
        "parentId": str(category.parent_id) if category.parent_id else None,
        "name": category.name,
        "sort": category.sort,
        "status": category.status,
        "version": category.version,
    }


def serialize_sku(sku, *, admin=False):
    result = {
        "id": str(sku.id),
        "skuCode": sku.sku_code,
        "options": [{"name": name, "value": value} for name, value in sku.options.items()],
        "priceCent": sku.sale_price_cent,
        "availableQuantity": sku.available_qty,
        "stockStatus": "available" if sku.available_qty > 0 else "sold_out",
        "version": sku.version,
    }
    if admin:
        result.update(reservedQuantity=sku.reserved_qty, warningQuantity=sku.warning_qty)
    return result


async def serialize_product(db, product, *, admin=False):
    result = {
        "id": str(product.id),
        "name": product.name,
        "summary": product.summary,
        "description": product.description,
        "instructions": product.instructions,
        "status": product.status,
        "version": product.version,
        "skus": [
            serialize_sku(s, admin=admin)
            for s in await product_skus(db, product.id)
            if s.status == "active"
        ],
    }
    if product.category_id:
        result["categoryId"] = str(product.category_id)
    if admin:
        result.update(
            sort=product.sort,
            coverFileId=str(product.cover_file_id) if product.cover_file_id else None,
            galleryFileIds=[str(identity) for identity in product.gallery_file_ids],
        )
    from ..core.config import get_settings
    from ..integrations.cos_client import MallCOSStore, get_cos_client

    settings = get_settings()
    if settings.mall_storage_outbound_enabled:
        store = MallCOSStore(get_cos_client(), outbound_enabled=True)
        urls = []
        for identity in ([product.cover_file_id] if product.cover_file_id else []) + list(
            product.gallery_file_ids
        ):
            file = await _image(db, int(identity))
            urls.append(await store.sign_get(file.object_key, expires_seconds=300))
        if product.cover_file_id and urls:
            result["coverUrl"] = urls.pop(0)
        result["galleryUrls"] = urls
    return result


def serialize_movement(event):
    return {
        "id": str(event.id),
        "skuId": str(event.sku_id),
        "eventKey": event.event_key,
        "kind": event.kind,
        "availableDelta": event.available_delta,
        "reservedDelta": event.reserved_delta,
        "reason": event.reason,
        "createdAt": event.created_at.isoformat() + "Z",
    }


def visible_categories():
    parent = MallCategory.__table__.alias("parent_category")
    return select(MallCategory.id).where(
        MallCategory.status == "enabled",
        or_(
            MallCategory.parent_id.is_(None),
            MallCategory.parent_id.in_(select(parent.c.id).where(parent.c.status == "enabled")),
        ),
    )


async def _page(db, query, model, key, *, mode, cursor, page_size, descending=False):
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    if cursor:
        try:
            decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            saved_mode, value, identity = decoded
            if saved_mode != mode or type(value) is not int or type(identity) is not int:
                raise ValueError()
        except (ValueError, TypeError, json.JSONDecodeError):
            raise ValidationException(message="分页游标不合法或排序条件已变化")
        query = query.where(
            or_(
                key < value if descending else key > value,
                (key == value) & (model.id < identity if descending else model.id > identity),
            )
        )
    query = query.add_columns(key.label("page_key")).order_by(
        key.desc() if descending else key.asc(), model.id.desc() if descending else model.id.asc()
    )
    rows = (await db.execute(query.limit(page_size + 1))).all()
    next_cursor = None
    if len(rows) > page_size:
        item, value = rows[page_size - 1]
        next_cursor = (
            base64.urlsafe_b64encode(json.dumps([mode, value, item.id]).encode())
            .decode()
            .rstrip("=")
        )
    return [row[0] for row in rows[:page_size]], next_cursor, total


async def list_categories(db, *, public=False, cursor=None, page_size=20):
    query = select(MallCategory)
    if public:
        query = query.where(MallCategory.id.in_(visible_categories()))
    items, next_cursor, total = await _page(
        db,
        query,
        MallCategory,
        MallCategory.sort,
        mode="categories",
        cursor=cursor,
        page_size=page_size,
    )
    return {
        "items": [serialize_category(c) for c in items],
        "nextCursor": next_cursor,
        "total": total,
    }


async def list_products(
    db, *, public=False, cursor=None, page_size=20, category_id=None, q=None, sort="default"
):
    query = select(MallProduct)
    if public:
        query = query.where(
            MallProduct.status == "on_sale", MallProduct.category_id.in_(visible_categories())
        )
    if category_id:
        query = query.where(
            or_(
                MallProduct.category_id == category_id,
                MallProduct.category_id.in_(
                    select(MallCategory.id).where(MallCategory.parent_id == category_id)
                ),
            )
        )
    if q:
        query = query.where(
            or_(
                MallProduct.name.contains(q, autoescape=True),
                MallProduct.summary.contains(q, autoescape=True),
            )
        )
    if sort not in {"default", "price_asc", "price_desc"}:
        raise ValidationException(message="商品排序不合法")
    price = (
        select(func.min(MallSku.sale_price_cent))
        .where(MallSku.product_id == MallProduct.id, MallSku.status == "active")
        .correlate(MallProduct)
        .scalar_subquery()
    )
    key = MallProduct.sort if sort == "default" else func.coalesce(price, 0)
    items, next_cursor, total = await _page(
        db,
        query,
        MallProduct,
        key,
        mode=f"products:{sort}:{category_id}:{q}",
        cursor=cursor,
        page_size=page_size,
        descending=sort == "price_desc",
    )
    return {
        "items": [await serialize_product(db, p, admin=not public) for p in items],
        "nextCursor": next_cursor,
        "total": total,
    }


async def get_product(db, product_id, *, public=False):
    product = await _get(db, MallProduct, product_id)
    if public and (
        product.status != "on_sale"
        or not await db.scalar(
            select(MallCategory.id).where(
                MallCategory.id == product.category_id, MallCategory.id.in_(visible_categories())
            )
        )
    ):
        raise NotFoundException(message="商品暂不可购买")
    return product


async def list_stock_movements(db, sku_id, *, cursor=None, page_size=20):
    await _get(db, MallSku, sku_id)
    rows, next_cursor, total = await _page(
        db,
        select(MallStockMovement).where(MallStockMovement.sku_id == sku_id),
        MallStockMovement,
        MallStockMovement.id,
        mode=f"stock:{sku_id}",
        cursor=cursor,
        page_size=page_size,
        descending=True,
    )
    return {
        "items": [serialize_movement(e) for e in rows],
        "nextCursor": next_cursor,
        "total": total,
    }
