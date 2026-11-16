"""Catalog rules protect classification, historical SKUs and reserved stock."""

import pytest
from sqlalchemy import select

from src.api.mall_deps import MallActor
from src.core.exceptions import ConflictException, ValidationException
from src.models.mall_catalog import MallSku, MallStockMovement

ACTOR = MallActor("admin", 1, frozenset({"mall.products.write", "mall.stock.write"}))


@pytest.mark.asyncio
async def test_categories_only_allow_one_level(db_session):
    from src.schemas.mall_catalog import CategoryWrite
    from src.services.mall_catalog_service import save_category

    root = await save_category(db_session, CategoryWrite(name="食品", status="enabled"))
    assert root.parent_id is None
    with pytest.raises(ValidationException, match="仅支持一级分类"):
        await save_category(
            db_session, CategoryWrite(name="谷物", parentId=str(root.id), status="enabled")
        )
    another = await save_category(db_session, CategoryWrite(name="其他", status="enabled"))
    with pytest.raises(ValidationException, match="仅支持一级分类"):
        await save_category(
            db_session,
            CategoryWrite(name="食品", parentId=str(another.id), status="enabled"),
            category_id=root.id,
        )
    with pytest.raises(ConflictException, match="分类名称已存在"):
        await save_category(db_session, CategoryWrite(name="食品", status="enabled"))


@pytest.mark.asyncio
async def test_editing_legacy_child_promotes_it_without_replacing_its_id(db_session):
    from src.models.mall_catalog import MallCategory
    from src.schemas.mall_catalog import CategoryWrite
    from src.services.mall_catalog_service import save_category

    root = await save_category(db_session, CategoryWrite(name="食品", status="enabled"))
    child = MallCategory(name="谷物", parent_id=root.id, sort=0, status="enabled")
    db_session.add(child)
    await db_session.flush()
    identity, version = child.id, child.version
    updated = await save_category(
        db_session, CategoryWrite(name="谷物", status="enabled"),
        category_id=identity, expected_version=version,
    )
    assert updated.id == identity
    assert updated.parent_id is None
    assert updated.version == version + 1


@pytest.mark.asyncio
async def test_draft_can_be_incomplete_and_publish_requires_real_information(db_session):
    from src.schemas.mall_catalog import ProductWrite
    from src.services.mall_catalog_service import save_product, set_product_status

    product = await save_product(db_session, ProductWrite(name="真实商品"), actor=ACTOR)
    assert product.status == "draft"
    with pytest.raises(ValidationException):
        await set_product_status(
            db_session, product.id, "on_sale", expected_version=product.version
        )


@pytest.mark.asyncio
async def test_listed_product_cannot_be_edited_until_off_sale(db_session):
    from src.schemas.mall_catalog import ProductWrite
    from src.services.mall_catalog_service import save_product

    product = await save_product(db_session, ProductWrite(name="在售商品"), actor=ACTOR)
    product.status = "on_sale"
    await db_session.flush()
    with pytest.raises(ConflictException, match="上架状态的商品不允许编辑"):
        await save_product(
            db_session,
            ProductWrite(name="改名"),
            actor=ACTOR,
            product_id=product.id,
            expected_version=product.version,
        )
    product.status = "off_sale"
    await db_session.flush()
    version = product.version
    edited = await save_product(
        db_session,
        ProductWrite(name="改名"),
        actor=ACTOR,
        product_id=product.id,
        expected_version=version,
    )
    assert edited.name == "改名" and edited.version == version + 1


@pytest.mark.asyncio
async def test_price_edit_never_overwrites_reserved_stock_and_adjustment_is_audited(db_session):
    from src.schemas.mall_catalog import ProductWrite
    from src.services.mall_catalog_service import adjust_stock, save_product

    product = await save_product(
        db_session,
        ProductWrite(
            name="测试",
            skus=[
                {
                    "skuCode": "SKU-001",
                    "priceCent": 100,
                    "initialStock": 10,
                }
            ],
        ),
        actor=ACTOR,
    )
    sku = (
        await db_session.execute(select(MallSku).where(MallSku.product_id == product.id))
    ).scalar_one()
    sku.reserved_qty = 2
    await db_session.flush()
    await save_product(
        db_session,
        ProductWrite(
            name="测试",
            skus=[
                {
                    "id": str(sku.id),
                    "skuCode": "SKU-001",
                    "priceCent": 120,
                }
            ],
        ),
        actor=ACTOR,
        product_id=product.id,
        expected_version=product.version,
    )
    assert sku.available_qty == 10 and sku.reserved_qty == 2
    with pytest.raises(ValidationException):
        await save_product(
            db_session,
            ProductWrite(
                name="测试",
                skus=[
                    {
                        "id": str(sku.id),
                        "skuCode": "SKU-001",
                        "priceCent": 120,
                        "initialStock": 0,
                    }
                ],
            ),
            actor=ACTOR,
            product_id=product.id,
            expected_version=product.version,
        )
    await adjust_stock(
        db_session,
        sku.id,
        expected_version=sku.version,
        delta=-6,
        reason="盘点",
        actor=ACTOR,
        event_key="count-001",
    )
    assert sku.available_qty == 4 and sku.reserved_qty == 2
    with pytest.raises(ValidationException):
        await adjust_stock(
            db_session,
            sku.id,
            expected_version=sku.version,
            delta=-5,
            reason="盘点",
            actor=ACTOR,
            event_key="count-002",
        )
    events = (
        (
            await db_session.execute(
                select(MallStockMovement).where(MallStockMovement.sku_id == sku.id)
            )
        )
        .scalars()
        .all()
    )
    assert [event.kind for event in events] == ["initial", "adjustment"]
    assert events[-1].before["available"] == 10 and events[-1].after["available"] == 4


@pytest.mark.asyncio
async def test_archive_preserves_skus_and_stock(db_session):
    from src.schemas.mall_catalog import ProductWrite
    from src.services.mall_catalog_service import save_product, set_product_status

    original = await save_product(
        db_session,
        ProductWrite(
            name="原商品",
            skus=[
                {
                    "skuCode": "ORIGINAL",
                    "priceCent": 100,
                    "initialStock": 7,
                }
            ],
        ),
        actor=ACTOR,
    )
    rows = (await db_session.execute(select(MallSku).order_by(MallSku.id))).scalars().all()
    assert len(rows) == 1 and rows[0].available_qty == 7
    await set_product_status(db_session, original.id, "archived", expected_version=original.version)
    assert rows[0].status == "archived" and rows[0].available_qty == 7
    with pytest.raises(ConflictException):
        await set_product_status(
            db_session, original.id, "on_sale", expected_version=original.version
        )


def test_sku_contract_rejects_overflow_dimensions_float_prices_and_excluded_fields():
    from pydantic import ValidationError

    from src.schemas.mall_catalog import ProductWrite

    for body in [
        {"name": "测试", "brandId": "1"},
        {"name": "测试", "skus": [{"skuCode": "x", "priceCent": 1.1}]},
        {
            "name": "测试",
            "skus": [
                {
                    "skuCode": "x",
                    "priceCent": 1,
                    "options": [{"name": str(i), "value": "a"} for i in range(3)],
                }
            ],
        },
    ]:
        with pytest.raises(ValidationError):
            ProductWrite.model_validate(body)


@pytest.mark.asyncio
async def test_partial_sku_edit_cannot_create_a_duplicate_default_combination(db_session):
    from src.schemas.mall_catalog import ProductWrite
    from src.services.mall_catalog_service import save_product

    product = await save_product(
        db_session,
        ProductWrite(
            name="单规格",
            skus=[
                {
                    "skuCode": "DEFAULT-1",
                    "priceCent": 100,
                }
            ],
        ),
        actor=ACTOR,
    )
    with pytest.raises(ValidationException):
        await save_product(
            db_session,
            ProductWrite(
                name="单规格",
                skus=[
                    {
                        "skuCode": "DEFAULT-2",
                        "priceCent": 200,
                    }
                ],
            ),
            actor=ACTOR,
            product_id=product.id,
            expected_version=product.version,
        )


@pytest.mark.asyncio
async def test_multi_sku_partial_price_edit_preserves_options_warning_and_trade_snapshot(
    db_session,
):
    from src.schemas.mall_catalog import ProductWrite
    from src.services.mall_catalog_service import save_product
    from src.models.mall_trade import MallOrder, MallOrderItem
    from src.models.mall_base import utc_now
    from tests.conftest import seed_user

    product = await save_product(
        db_session,
        ProductWrite(
            name="多规格",
            skus=[
                {
                    "skuCode": "SMALL",
                    "priceCent": 100,
                    "warningQuantity": 5,
                    "options": [{"name": "包装", "value": "小盒"}],
                },
                {
                    "skuCode": "LARGE",
                    "priceCent": 200,
                    "options": [{"name": "包装", "value": "大盒"}],
                },
            ],
        ),
        actor=ACTOR,
    )
    sku = (await db_session.scalars(select(MallSku).where(MallSku.sku_code == "SMALL"))).one()
    buyer = await seed_user(db_session, user_type="personal")
    order = MallOrder(
        order_no="historical-catalog",
        buyer_user_id=buyer,
        goods_amount_cent=100,
        payable_amount_cent=100,
        expires_at=utc_now(),
    )
    db_session.add(order)
    await db_session.flush()
    item = MallOrderItem(
        order_id=order.id,
        sku_id=sku.id,
        product_id=product.id,
        product_snapshot={"name": "多规格", "options": {"包装": "小盒"}},
        unit_price_cent=100,
        quantity=1,
        line_amount_cent=100,
    )
    db_session.add(item)
    await db_session.flush()
    await save_product(
        db_session,
        ProductWrite(
            name="改名",
            skus=[
                {
                    "id": str(sku.id),
                    "skuCode": "SMALL",
                    "priceCent": 150,
                }
            ],
        ),
        actor=ACTOR,
        product_id=product.id,
        expected_version=product.version,
    )
    assert sku.options == {"包装": "小盒"} and sku.warning_qty == 5
    await db_session.refresh(item)
    assert item.unit_price_cent == 100 and item.product_snapshot["name"] == "多规格"
