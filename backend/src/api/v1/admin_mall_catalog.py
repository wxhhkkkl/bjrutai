"""Catalog mutations commit their command, audit and domain changes atomically."""

import hashlib

from fastapi import APIRouter, Depends, File, Header, Path, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException, ConflictException
from ...models.mall_catalog import MallCategory, MallProduct, MallStockMovement
from ...models.mall_base import utc_now
from ...models.mall_operations import MallFile
from ...schemas.mall_catalog import (
    CategoryPatch,
    CategoryWrite,
    ProductPatch,
    ProductWrite,
    StatusChange,
    StockAdjustment,
)
from ...services import mall_catalog_query_service as queries
from ...services import mall_catalog_service as catalog
from ...services.mall_audit_service import record_mall_admin_audit
from ...services.mall_command_service import complete_mall_command, reserve_mall_command
from ...services.image_upload_service import upload_image_via_cos
from ...integrations.cos_client import MallCOSStore, get_cos_client

router = APIRouter(prefix="/admin/mall", tags=["admin-mall-catalog"])
read_products = require_mall_admin("mall.products.read")
write_products = require_mall_admin("mall.products.write")
write_stock = require_mall_admin("mall.stock.write")
read_stock = require_mall_admin("mall.stock.read")


@router.post("/products/images", operation_id="uploadAdminMallProductImage")
async def upload_product_image(
    file: UploadFile = File(...),
    actor: MallActor = Depends(write_products),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read(5 * 1024 * 1024 + 1)
    content_type = file.content_type or "application/octet-stream"
    if content_type not in {"image/jpeg", "image/png"}:
        raise BadRequestException(message="仅支持 JPG 或 PNG 图片")
    if not content or len(content) > 5 * 1024 * 1024:
        raise BadRequestException(message="图片大小不能超过 5 MB")
    try:
        token = await upload_image_via_cos(
            content,
            file_name=file.filename or "product-image.jpg",
            content_type=content_type,
            user_id=actor.actor_id,
            key_prefix="mall/product_image/admin/",
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc)) from exc

    image = MallFile(
        object_key=token["fileId"],
        purpose="product_image",
        owner_actor_type="admin",
        owner_actor_id=actor.actor_id,
        mime=content_type,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        status="verified",
        expires_at=utc_now(),
    )
    try:
        db.add(image)
        await db.flush()
        await record_mall_admin_audit(
            db,
            actor=actor,
            action="uploadMallProductImage",
            entity_type="mall_file",
            entity_id=str(image.id),
            detail={"purpose": "product_image", "size": len(content)},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    preview_url = await MallCOSStore(
        get_cos_client(), outbound_enabled=True
    ).sign_get(image.object_key, expires_seconds=300)
    return _build_response(
        0,
        "success",
        {"id": str(image.id), "status": image.status, "previewUrl": preview_url},
    )


async def mutate(db, actor, action, key, body, entity_type, model, apply):
    try:
        intent = await reserve_mall_command(db, actor=actor, action=action, key=key, payload=body)
        if intent.created:
            entity = await apply(intent.command.id)
            await record_mall_admin_audit(
                db,
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity.id),
                detail={"version": entity.version},
            )
            await complete_mall_command(db, intent, entity_type=entity_type, entity_id=entity.id)
        else:
            if intent.command.status != "completed":
                raise ConflictException(message="原操作仍在处理中")
            entity = await catalog._get(db, model, intent.command.entity_id)
        await db.commit()
        if model is MallCategory:
            result = queries.serialize_category(entity)
        elif model is MallProduct:
            result = await queries.serialize_product(db, entity, admin=True, include_cost=True)
        else:
            result = queries.serialize_movement(entity)
        return _build_response(0, "success", result)
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(message="商品编码、分类名称或库存事件已存在") from exc
    except Exception:
        await db.rollback()
        raise


@router.get("/categories", operation_id="listAdminMallCategorys")
async def categories(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(read_products),
    db: AsyncSession = Depends(get_db),
):
    return _build_response(
        0, "success", await queries.list_categories(db, cursor=cursor, page_size=page_size)
    )


@router.post("/categories", operation_id="createAdminMallCategory")
async def create_category(
    body: CategoryWrite,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_products),
    db: AsyncSession = Depends(get_db),
):
    async def apply(_command_id):
        return await catalog.save_category(db, body)

    return await mutate(
        db,
        actor,
        "createAdminMallCategory",
        key,
        body.model_dump(mode="json"),
        "mall_category",
        MallCategory,
        apply,
    )


@router.patch("/categories/{categoryId}", operation_id="updateAdminMallCategory")
async def update_category(
    body: CategoryPatch,
    category_id: int = Path(alias="categoryId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_products),
    db: AsyncSession = Depends(get_db),
):
    async def apply(_command_id):
        return await catalog.save_category(
            db, body.category, category_id=category_id, expected_version=body.expected_version
        )

    return await mutate(
        db,
        actor,
        "updateAdminMallCategory",
        key,
        {**body.model_dump(mode="json"), "categoryId": category_id},
        "mall_category",
        MallCategory,
        apply,
    )


@router.get("/freight-template-options")
async def freight_template_options(
    _actor: MallActor = Depends(read_products),
    db: AsyncSession = Depends(get_db),
):
    from ...services.mall_settings_service import get_mall_settings

    settings = await get_mall_settings(db)
    options = [{"id": "default", "name": "默认运费"}]
    options.extend({"id": item["id"], "name": item["name"]} for item in settings.freight_templates or [])
    await db.commit()
    return _build_response(0, "success", options)


@router.get("/products", operation_id="listAdminMallProducts")
async def products(
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    q: str | None = Query(None, max_length=128),
    category_id: int | None = Query(None, alias="categoryId", gt=0),
    actor: MallActor = Depends(read_products),
    db: AsyncSession = Depends(get_db),
):
    return _build_response(
        0,
        "success",
        await queries.list_products(
            db, cursor=cursor, page_size=page_size, q=q, category_id=category_id
        ),
    )


@router.get("/products/{productId}", operation_id="getAdminMallProduct")
async def product(
    product_id: int = Path(alias="productId", gt=0),
    actor: MallActor = Depends(read_products),
    db: AsyncSession = Depends(get_db),
):
    return _build_response(
        0,
        "success",
        await queries.serialize_product(
            db,
            await queries.get_product(db, product_id),
            admin=True,
            include_cost="mall.products.write" in actor.permissions,
        ),
    )


@router.post("/products", operation_id="createAdminMallProduct")
async def create_product(
    body: ProductWrite,
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_products),
    db: AsyncSession = Depends(get_db),
):
    async def apply(_command_id):
        return await catalog.save_product(db, body, actor=actor)

    return await mutate(
        db,
        actor,
        "createAdminMallProduct",
        key,
        body.model_dump(mode="json"),
        "mall_product",
        MallProduct,
        apply,
    )


@router.patch("/products/{productId}", operation_id="updateAdminMallProduct")
async def update_product(
    body: ProductPatch,
    product_id: int = Path(alias="productId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_products),
    db: AsyncSession = Depends(get_db),
):
    async def apply(_command_id):
        return await catalog.save_product(
            db,
            body.product,
            actor=actor,
            product_id=product_id,
            expected_version=body.expected_version,
        )

    return await mutate(
        db,
        actor,
        "updateAdminMallProduct",
        key,
        {**body.model_dump(mode="json"), "productId": product_id},
        "mall_product",
        MallProduct,
        apply,
    )


@router.post("/products/{productId}/status", operation_id="setMallProductStatus")
async def status(
    body: StatusChange,
    product_id: int = Path(alias="productId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_products),
    db: AsyncSession = Depends(get_db),
):
    async def apply(_command_id):
        return await catalog.set_product_status(
            db, product_id, body.target_status, expected_version=body.expected_version
        )

    return await mutate(
        db,
        actor,
        "setMallProductStatus",
        key,
        {**body.model_dump(mode="json"), "productId": product_id},
        "mall_product",
        MallProduct,
        apply,
    )


@router.post("/skus/{skuId}/stock-adjustments", operation_id="adjustMallStock")
async def stock(
    body: StockAdjustment,
    sku_id: int = Path(alias="skuId", gt=0),
    key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(write_stock),
    db: AsyncSession = Depends(get_db),
):
    async def apply(command_id):
        event_key = f"catalog-command:{command_id}"
        await catalog.adjust_stock(
            db,
            sku_id,
            expected_version=body.expected_version,
            delta=body.delta_available_quantity,
            reason=body.reason,
            actor=actor,
            event_key=event_key,
        )
        return (
            await db.execute(
                select(MallStockMovement).where(
                    MallStockMovement.sku_id == sku_id, MallStockMovement.event_key == event_key
                )
            )
        ).scalar_one()

    return await mutate(
        db,
        actor,
        "adjustMallStock",
        key,
        {**body.model_dump(mode="json"), "skuId": sku_id},
        "mall_stock_movement",
        MallStockMovement,
        apply,
    )


@router.get("/skus/{skuId}/stock-movements", operation_id="listMallStockMovements")
async def movements(
    sku_id: int = Path(alias="skuId", gt=0),
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    actor: MallActor = Depends(read_stock),
    db: AsyncSession = Depends(get_db),
):
    return _build_response(
        0,
        "success",
        await queries.list_stock_movements(db, sku_id, cursor=cursor, page_size=page_size),
    )
