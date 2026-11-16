"""Two operators cannot both decrement the same last unit."""

import asyncio

from sqlalchemy import select

from src.api.mall_deps import MallActor
from src.core.exceptions import ConflictException, ValidationException
from src.models.mall_catalog import MallSku, MallStockMovement
from src.schemas.mall_catalog import ProductWrite
from src.services.mall_catalog_service import adjust_stock, save_product


async def test_category_write_rechecks_current_parent_after_an_old_snapshot(mall_mysql_sessions):
    from src.models.mall_catalog import MallCategory
    from src.schemas.mall_catalog import CategoryWrite
    from src.services.mall_catalog_service import save_category

    async with mall_mysql_sessions() as setup:
        parent = await save_category(setup, CategoryWrite(name="并发分类", status="enabled"))
        identity = parent.id
        await setup.commit()
    async with mall_mysql_sessions() as stale:
        assert (
            await stale.scalar(select(MallCategory.status).where(MallCategory.id == identity))
            == "enabled"
        )
        async with mall_mysql_sessions() as change:
            await save_category(
                change, CategoryWrite(name="并发分类", status="disabled"), category_id=identity
            )
            await change.commit()
        try:
            await save_category(
                stale, CategoryWrite(name="不应启用", status="enabled", parentId=str(identity))
            )
        except ValidationException:
            await stale.rollback()
        else:
            await stale.rollback()
            raise AssertionError("disabled parent accepted using a stale snapshot")


async def test_concurrent_stock_edits_use_one_version_and_one_movement(mall_mysql_sessions):
    actor = MallActor("admin", 999, frozenset())
    async with mall_mysql_sessions() as setup:
        product = await save_product(
            setup,
            ProductWrite(
                name="并发库存",
                skus=[
                    {
                        "skuCode": "MYSQL-LAST-UNIT",
                        "priceCent": 100,
                        "initialStock": 1,
                    }
                ],
            ),
            actor=actor,
        )
        sku = (await setup.scalars(select(MallSku).where(MallSku.product_id == product.id))).one()
        sku_id, version = sku.id, sku.version
        await setup.commit()

    async def decrement(number):
        async with mall_mysql_sessions() as session:
            try:
                await adjust_stock(
                    session,
                    sku_id,
                    expected_version=version,
                    delta=-1,
                    reason="并发盘点",
                    actor=actor,
                    event_key=f"mysql-count-{number}",
                )
                await session.commit()
                return True
            except ConflictException:
                await session.rollback()
                return False

    result = await asyncio.wait_for(asyncio.gather(decrement(1), decrement(2)), timeout=10)
    assert sum(result) == 1
    async with mall_mysql_sessions() as reader:
        assert (await reader.get(MallSku, sku_id)).available_qty == 0
        moves = (
            await reader.scalars(
                select(MallStockMovement).where(
                    MallStockMovement.sku_id == sku_id, MallStockMovement.kind == "adjustment"
                )
            )
        ).all()
        assert len(moves) == 1 and moves[0].available_delta == -1
