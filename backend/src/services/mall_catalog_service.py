"""Catalog lifecycle and explicit stock events, with no order-history rewrites."""

import re

from sqlalchemy import select

from ..core.exceptions import ConflictException, NotFoundException, ValidationException
from ..models.mall_base import utc_now
from ..models.mall_catalog import MallCategory, MallProduct, MallSku, MallStockMovement
from ..models.mall_operations import MallFile, MallSettings
from .mall_settings_service import get_mall_settings

_INLINE_PRODUCT_IMAGE_RE = re.compile(
    r"""<img\b[^>]*\balt=["']mall-file-id:([1-9][0-9]*)["'][^>]*>""",
    re.IGNORECASE,
)


def inline_product_image_ids(description):
    matches = _INLINE_PRODUCT_IMAGE_RE.findall(description or "")
    return list(dict.fromkeys(int(value) for value in matches))


async def _catalog_lock(db):
    # One small store: serialize tree/publish edits to prevent hierarchy phantoms.
    await get_mall_settings(db)
    await db.execute(
        select(MallSettings)
        .where(MallSettings.id == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _get(db, model, identity, lock=False):
    statement = select(model).where(model.id == identity).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    result = (await db.execute(statement)).scalar_one_or_none()
    if result is None:
        raise NotFoundException(message="商城记录不存在")
    return result


async def save_category(db, data, *, category_id=None, expected_version=None):
    await _catalog_lock(db)
    category = await _get(db, MallCategory, category_id, True) if category_id else None
    if category and expected_version is not None and category.version != expected_version:
        raise ConflictException(message="分类版本已变化")
    if data.parent_id is not None:
        raise ValidationException(message="仅支持一级分类，不能设置父分类")
    parent_id = None
    duplicate = await db.scalar(
        select(MallCategory.id)
        .where(
            MallCategory.name == data.name,
            MallCategory.parent_id == parent_id,
            MallCategory.id != (category_id or 0),
        )
        .with_for_update()
    )
    if duplicate:
        raise ConflictException(message="分类名称已存在")
    if category and data.status == "disabled":
        children = (
            await db.scalars(
                select(MallCategory.id)
                .where(MallCategory.parent_id == category.id)
                .with_for_update()
            )
        ).all()
        if await db.scalar(
            select(MallProduct.id)
            .where(
                MallProduct.category_id.in_([category.id, *children]),
                MallProduct.status == "on_sale",
            )
            .limit(1)
            .with_for_update()
        ):
            raise ConflictException(message="请先迁移或下架分类内的在售商品")
    if category is None:
        category = MallCategory()
        db.add(category)
    else:
        category.version += 1
    category.name, category.parent_id = data.name, parent_id
    category.sort, category.status = data.sort, data.status
    await db.flush()
    return category


async def _image(db, identity, lock=False):
    file = await _get(db, MallFile, identity, lock)
    if (
        file.purpose != "product_image"
        or file.status not in {"verified", "bound"}
        or file.expires_at > utc_now()
    ):
        raise ValidationException(message="商品图片尚未核验或仍可被上传覆盖")
    return file


async def product_skus(db, identity, *, lock=False):
    query = select(MallSku).where(MallSku.product_id == identity).order_by(MallSku.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return (await db.scalars(query)).all()


def _validate_delivery(settings, method, template_id):
    if method == "express" and not template_id:
        raise ValidationException(message="快递发货需要选择运费模板")
    if template_id and (
        method != "express"
        or (template_id != "default" and not any(
            item["id"] == template_id for item in settings.freight_templates or []
        ))
    ):
        raise ValidationException(message="所选运费模板无效")


async def _publishable(db, product):
    if not product.category_id:
        raise ValidationException(message="请先选择商品分类")
    if not product.cover_file_id:
        raise ValidationException(message="请先上传商品主图")
    if not (product.description or "").strip():
        raise ValidationException(message="请先填写商品详情或插入详情图片并保存")
    category = await _get(db, MallCategory, product.category_id, True)
    if category.status != "enabled":
        raise ValidationException(message="商品分类已停用")
    if (
        category.parent_id
        and (await _get(db, MallCategory, category.parent_id, True)).status != "enabled"
    ):
        raise ValidationException(message="商品父分类已停用")
    await _image(db, product.cover_file_id, True)
    skus = [sku for sku in await product_skus(db, product.id, lock=True) if sku.status == "active"]
    if not skus or any(s.sale_price_cent <= 0 or s.available_qty < 0 for s in skus):
        raise ValidationException(message="发布需有效规格、正售价和非负库存")
    settings = await get_mall_settings(db)
    _validate_delivery(settings, product.delivery_method, product.freight_template_id)
    if product.product_type == "virtual" and product.delivery_method != "virtual":
        raise ValidationException(message="虚拟商品请使用虚拟配送方式")
    if product.product_type != "virtual" and product.delivery_method != "express":
        if product.delivery_method == "pickup":
            raise ValidationException(message="当前商城暂不支持用户自提")
        raise ValidationException(message="实物商品需要配置快递配送和运费模板")
    if not settings.policy_versions.get("policy"):
        raise ValidationException(message="请先配置配送售后规则版本")


async def save_product(db, data, *, actor, product_id=None, expected_version=None):
    await _catalog_lock(db)
    product = await _get(db, MallProduct, product_id, True) if product_id else None
    if product and (product.status == "archived" or product.version != expected_version):
        raise ConflictException(message="商品已归档或版本已变化")
    existing = (
        {s.id: s for s in await product_skus(db, product_id, lock=True)} if product_id else {}
    )
    fields = data.model_fields_set
    updates = {field: getattr(data, field) for field in fields - {"skus"}}
    product_type_supplied = "product_type" in fields
    delivery_method_supplied = "delivery_method" in fields
    freight_template_supplied = "freight_template_id" in fields
    effective_type = (
        data.product_type
        if product_type_supplied
        else (
            "virtual"
            if delivery_method_supplied and data.delivery_method == "virtual"
            else (
                "physical"
                if delivery_method_supplied and data.delivery_method in {"express", "pickup"}
                else product.product_type if product else "physical"
            )
        )
    )
    effective_method = (
        data.delivery_method
        if delivery_method_supplied
        else product.delivery_method if product else None
    )
    effective_template = (
        data.freight_template_id
        if freight_template_supplied
        else product.freight_template_id if product else None
    )

    if product_type_supplied and not delivery_method_supplied:
        if effective_type == "virtual":
            effective_method = "virtual"
            effective_template = None
            updates["delivery_method"] = effective_method
            updates["freight_template_id"] = None
        elif effective_method == "virtual":
            effective_method = None
            effective_template = None
            updates["delivery_method"] = None
            updates["freight_template_id"] = None
    elif delivery_method_supplied and not product_type_supplied:
        if effective_method == "virtual":
            updates["product_type"] = "virtual"
        elif effective_method in {"express", "pickup"}:
            updates["product_type"] = "physical"

    if effective_type == "virtual" and effective_method in {"express", "pickup"}:
        raise ValidationException(message="虚拟商品不能选择快递或自提配送")
    if effective_type == "physical" and effective_method == "virtual":
        raise ValidationException(message="实物商品不能选择虚拟配送方式")
    if (
        (product_type_supplied or delivery_method_supplied)
        and effective_method != "express"
        and not freight_template_supplied
        and effective_template
    ):
        effective_template = None
        updates["freight_template_id"] = None

    if {"product_type", "delivery_method", "freight_template_id"} & fields:
        _validate_delivery(
            await get_mall_settings(db),
            effective_method,
            effective_template,
        )
    proposed = data.skus
    if proposed is not None:
        codes, combinations, dimensions, identities = set(), set(), None, set()
        supplied_ids = {int(s.id) for s in proposed if s.id}
        omitted = [
            s for s in existing.values() if s.id not in supplied_ids and s.status == "active"
        ]
        if len(omitted) + len(proposed) > 20:
            raise ValidationException(message="一个商品最多20个有效规格")
        for saved in omitted:
            codes.add(saved.sku_code)
            combinations.add(tuple(sorted(saved.options.items())))
            dimensions = tuple(sorted(saved.options))
        for sku in proposed:
            previous = existing.get(int(sku.id)) if sku.id else None
            options = (
                dict(previous.options)
                if previous and "options" not in sku.model_fields_set
                else {o.name: o.value for o in sku.options}
            )
            if "options" in sku.model_fields_set and len(options) != len(sku.options):
                raise ValidationException(message="规格维度不能重复")
            keys, combo = tuple(sorted(options)), tuple(sorted(options.items()))
            if (
                sku.sku_code in codes
                or combo in combinations
                or (dimensions is not None and keys != dimensions)
            ):
                raise ValidationException(message="规格编码、组合需唯一且维度一致")
            codes.add(sku.sku_code)
            combinations.add(combo)
            dimensions = keys
            if sku.id:
                identity = int(sku.id)
                if identity not in existing or identity in identities:
                    raise ValidationException(message="规格不属于本商品或重复引用")
                identities.add(identity)
                if sku.initial_stock is not None:
                    raise ValidationException(message="已有规格库存只能通过补货盘点调整")
                if existing[identity].status == "archived":
                    raise ValidationException(message="已归档规格不可恢复")
            conflict = await db.scalar(
                select(MallSku.id)
                .where(
                    MallSku.sku_code == sku.sku_code, MallSku.id != (int(sku.id) if sku.id else 0)
                )
                .with_for_update()
            )
            if conflict:
                raise ConflictException(message="规格编码已使用")
    for name in ("category_id", "cover_file_id"):
        value = getattr(data, name)
        if name in data.model_fields_set and value:
            if name == "category_id":
                await _get(db, MallCategory, int(value), True)
            else:
                await _image(db, int(value), True)
    for file_id in data.gallery_file_ids:
        if not file_id.isdecimal() or int(file_id) < 1:
            raise ValidationException(message="商品图片ID不合法")
        await _image(db, int(file_id), True)
    if "description" in data.model_fields_set:
        for file_id in inline_product_image_ids(data.description):
            await _image(db, file_id, True)
    if product is None:
        product = MallProduct(name=data.name, status="draft")
        db.add(product)
        await db.flush()
    else:
        product.version += 1
    for field, value in updates.items():
        if field in {"category_id", "cover_file_id"}:
            value = int(value) if value else None
        setattr(product, field, value)
    if proposed is not None:
        # Omitted existing rows are retained, never deleted out of old orders.
        for value in proposed:
            is_new = value.id is None
            sku = existing[int(value.id)] if value.id else MallSku(product_id=product.id)
            sku.sku_code, sku.sale_price_cent = value.sku_code, value.price_cent
            if is_new or "market_price_cent" in value.model_fields_set:
                sku.market_price_cent = value.market_price_cent
            if "barcode" in value.model_fields_set:
                sku.barcode = (value.barcode or "").strip() or None
            if is_new or "cost_price_cent" in value.model_fields_set:
                sku.cost_price_cent = value.cost_price_cent
            if is_new or "options" in value.model_fields_set:
                sku.options = {o.name: o.value for o in value.options}
            if is_new or "warning_quantity" in value.model_fields_set:
                sku.warning_qty = value.warning_quantity
            if is_new:
                sku.available_qty = value.initial_stock or 0
                db.add(sku)
                await db.flush()
                db.add(
                    MallStockMovement(
                        sku_id=sku.id,
                        event_key=f"initial:{sku.id}",
                        kind="initial",
                        available_delta=sku.available_qty,
                        reserved_delta=0,
                        before={"available": 0, "reserved": 0},
                        after={"available": sku.available_qty, "reserved": 0},
                        actor_type=actor.actor_type,
                        actor_id=actor.actor_id,
                        reason="初始库存",
                    )
                )
            else:
                sku.version += 1
    await db.flush()
    if product.status == "on_sale":
        await _publishable(db, product)
    image_ids = ([product.cover_file_id] if product.cover_file_id else []) + list(
        product.gallery_file_ids
    ) + inline_product_image_ids(product.description)
    for identity in image_ids:
        image = await _image(db, int(identity), True)
        if image.status == "verified":
            image.status = "bound"
            image.version += 1
    await db.flush()
    return product


async def set_product_status(db, product_id, status, *, expected_version):
    await _catalog_lock(db)
    product = await _get(db, MallProduct, product_id, True)
    if product.version != expected_version or product.status == "archived":
        raise ConflictException(message="商品已归档或版本已变化")
    if status not in {"on_sale", "off_sale", "archived"}:
        raise ValidationException(message="商品状态不合法")
    if status == "on_sale":
        await _publishable(db, product)
    if status == "archived":
        for sku in await product_skus(db, product.id, lock=True):
            sku.status = "archived"
            sku.version += 1
    product.status, product.version = status, product.version + 1
    await db.flush()
    return product


async def adjust_stock(db, sku_id, *, expected_version, delta, reason, actor, event_key):
    sku = await _get(db, MallSku, sku_id, True)
    existing = await db.scalar(
        select(MallStockMovement.id).where(
            MallStockMovement.sku_id == sku_id, MallStockMovement.event_key == event_key
        )
    )
    if existing:
        return sku
    if sku.version != expected_version or sku.status != "active":
        raise ConflictException(message="库存版本已变化或规格已归档")
    if (
        not reason.strip()
        or not isinstance(delta, int)
        or isinstance(delta, bool)
        or not 0 <= sku.available_qty + delta <= 2147483647
    ):
        raise ValidationException(message="库存调整后不能为负或超限，且须填写原因")
    before = {"available": sku.available_qty, "reserved": sku.reserved_qty}
    sku.available_qty += delta
    sku.version += 1
    db.add(
        MallStockMovement(
            sku_id=sku.id,
            event_key=event_key,
            kind="adjustment",
            available_delta=delta,
            reserved_delta=0,
            before=before,
            after={"available": sku.available_qty, "reserved": sku.reserved_qty},
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            reason=reason,
        )
    )
    await db.flush()
    return sku
