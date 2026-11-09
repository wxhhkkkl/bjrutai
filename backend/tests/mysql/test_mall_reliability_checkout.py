"""Checkout selections use live InnoDB reads and per-buyer serialization."""

import asyncio

import pytest
from sqlalchemy import func, select, update

from src.core.config import get_settings
from src.core.exceptions import ConflictException
from src.models.consent import ConsentRecord
from src.models.mall_catalog import MallCategory, MallSku
from src.models.mall_operations import MallSettings
from src.models.mall_trade import MallAddress, MallCartItem
from src.schemas.mall_checkout import AddressWrite, BuyItem, QuoteRequest
from src.services.mall_address_service import save_address
from src.services.mall_cart_service import add_cart_item
from src.services.mall_checkout_service import quote_order, validate_quote
from tests.mall_checkout_fixtures import ADDRESS, checkout_seed


async def test_two_default_addresses_and_same_sku_adds_serialize_per_buyer(mall_mysql_sessions):
    async with mall_mysql_sessions() as setup:
        actor, _, _, skus = await checkout_seed(setup)
        sku_id = skus[0].id
        await setup.commit()

    async def edit(number):
        async with mall_mysql_sessions() as db:
            await save_address(db, actor, AddressWrite(**ADDRESS, isDefault=True))
            await add_cart_item(db, actor, BuyItem(skuId=str(sku_id), quantity=number))
            await db.commit()

    await asyncio.wait_for(asyncio.gather(edit(1), edit(2)), timeout=15)
    async with mall_mysql_sessions() as reader:
        defaults = await reader.scalar(
            select(func.count())
            .select_from(MallAddress)
            .where(MallAddress.user_id == actor.actor_id, MallAddress.is_default.is_(True))
        )
        rows = (
            await reader.scalars(
                select(MallCartItem).where(
                    MallCartItem.user_id == actor.actor_id, MallCartItem.sku_id == sku_id
                )
            )
        ).all()
        assert defaults == 1 and len(rows) == 1 and rows[0].quantity == 3
        sku = await reader.get(MallSku, sku_id)
        assert sku.available_qty == 10 and sku.reserved_qty == 0


@pytest.mark.parametrize(
    "change_kind", ["price", "category", "address", "blocked", "consent", "policy"]
)
async def test_quote_validation_must_not_accept_old_repeatable_read_facts(
    mall_mysql_sessions, monkeypatch, change_kind
):
    monkeypatch.setattr(get_settings(), "mall_enabled", True)
    monkeypatch.setattr(get_settings(), "mall_purchase_enabled", True)
    async with mall_mysql_sessions() as setup:
        actor, _, product, skus = await checkout_seed(setup)
        address = await save_address(setup, actor, AddressWrite(**ADDRESS))
        sku_id, category_id = skus[0].id, product.category_id
        address_id, consent_id = address.id, address.consent_record_id
        quote = await quote_order(
            setup,
            actor,
            QuoteRequest(
                addressId=str(address.id),
                items=[
                    {"skuId": str(sku_id), "quantity": 1},
                ],
            ),
        )
        await setup.commit()
    async with mall_mysql_sessions() as stale:
        assert (
            await stale.scalar(select(MallSku.sale_price_cent).where(MallSku.id == sku_id)) == 10000
        )
        async with mall_mysql_sessions() as change:
            if change_kind == "price":
                await change.execute(
                    update(MallSku)
                    .where(MallSku.id == sku_id)
                    .values(sale_price_cent=10001, version=MallSku.version + 1)
                )
            elif change_kind == "category":
                await change.execute(
                    update(MallCategory)
                    .where(MallCategory.id == category_id)
                    .values(status="disabled")
                )
            elif change_kind == "address":
                await change.execute(
                    update(MallAddress)
                    .where(MallAddress.id == address_id)
                    .values(address_line="新的虚构地址", version=MallAddress.version + 1)
                )
            elif change_kind == "blocked":
                await change.execute(
                    update(MallSettings)
                    .where(MallSettings.id == 1)
                    .values(blocked_regions=["110000"])
                )
            elif change_kind == "consent":
                await change.execute(
                    update(ConsentRecord)
                    .where(ConsentRecord.id == consent_id)
                    .values(status="revoked")
                )
            else:
                await change.execute(
                    update(MallSettings)
                    .where(MallSettings.id == 1)
                    .values(freight_cent=1100, version=MallSettings.version + 1)
                )
            await change.commit()
        with pytest.raises(ConflictException):
            await validate_quote(stale, actor, quote["quoteToken"])
        await stale.rollback()
