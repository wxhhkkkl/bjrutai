"""A buyer's cart is a selection, never a stock or price promise."""

from sqlalchemy import select

from ..core.exceptions import ConflictException, NotFoundException, ValidationException
from ..models.mall_catalog import MallCategory, MallProduct, MallSku
from ..models.mall_trade import MallCartItem
from .mall_address_service import lock_buyer
from .mall_catalog_query_service import _page, serialize_sku, visible_categories


async def cart_item_state(db, sku, quantity, *, current=False):
    async def read(model, identity):
        return (
            await db.execute(
                select(model)
                .where(model.id == identity)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    product = (
        await read(MallProduct, sku.product_id)
        if current
        else await db.get(MallProduct, sku.product_id, populate_existing=True)
    )
    if sku.status != "active":
        return product, "sku_archived"
    if product.status != "on_sale":
        return product, "product_unavailable"
    if current:
        category = await read(MallCategory, product.category_id)
        parent = (
            await read(MallCategory, category.parent_id)
            if category and category.parent_id
            else None
        )
        if (
            not category
            or category.status != "enabled"
            or (category.parent_id and (not parent or parent.status != "enabled"))
        ):
            return product, "category_disabled"
    elif not await db.scalar(
        select(MallProduct.id).where(
            MallProduct.id == product.id, MallProduct.category_id.in_(visible_categories())
        )
    ):
        return product, "category_disabled"
    if sku.available_qty == 0:
        return product, "sold_out"
    if sku.available_qty < quantity:
        return product, "insufficient_stock"
    return product, None


async def owned_cart_item(db, actor, identity):
    row = (
        await db.execute(
            select(MallCartItem)
            .where(
                MallCartItem.id == identity,
                MallCartItem.user_id == actor.actor_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None or actor.actor_type != "user":
        raise NotFoundException(message="购物车项不存在")
    return row


async def add_cart_item(db, actor, data):
    await lock_buyer(db, actor)
    sku = await db.get(MallSku, int(data.sku_id), populate_existing=True)
    if sku is None:
        raise NotFoundException(message="商品规格不存在")
    _, reason = await cart_item_state(db, sku, data.quantity)
    if reason in {"sku_archived", "product_unavailable", "category_disabled"}:
        raise ValidationException(message="商品当前不可加购")
    row = (
        await db.execute(
            select(MallCartItem)
            .where(
                MallCartItem.user_id == actor.actor_id,
                MallCartItem.sku_id == sku.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row:
        if row.quantity + data.quantity > 999:
            raise ValidationException(message="同一规格购物车数量最多999")
        row.quantity += data.quantity
        row.version += 1
    else:
        row = MallCartItem(user_id=actor.actor_id, sku_id=sku.id, quantity=data.quantity)
        db.add(row)
    await db.flush()
    return row


async def update_cart_item(db, actor, identity, data):
    await lock_buyer(db, actor)
    row = await owned_cart_item(db, actor, identity)
    if row.version != data.expected_version:
        raise ConflictException(message="购物车版本已变化，请刷新")
    row.quantity, row.version = data.quantity, row.version + 1
    await db.flush()
    return row


async def remove_cart_item(db, actor, identity, expected_version):
    await lock_buyer(db, actor)
    row = await owned_cart_item(db, actor, identity)
    if row.version != expected_version:
        raise ConflictException(message="购物车版本已变化，请刷新")
    await db.delete(row)
    await db.flush()


async def serialize_cart_item(db, row):
    sku = await db.get(MallSku, row.sku_id, populate_existing=True)
    product, reason = await cart_item_state(db, sku, row.quantity)
    return {
        "id": str(row.id),
        "sku": serialize_sku(sku),
        "productName": product.name,
        "quantity": row.quantity,
        "valid": reason is None,
        "invalidReason": reason,
        "version": row.version,
    }


async def list_cart(db, actor, *, cursor=None, page_size=20):
    rows, next_cursor, total = await _page(
        db,
        select(MallCartItem).where(MallCartItem.user_id == actor.actor_id),
        MallCartItem,
        MallCartItem.id,
        mode=f"cart:{actor.actor_id}",
        cursor=cursor,
        page_size=page_size,
    )
    return {
        "items": [await serialize_cart_item(db, row) for row in rows],
        "nextCursor": next_cursor,
        "total": total,
    }
