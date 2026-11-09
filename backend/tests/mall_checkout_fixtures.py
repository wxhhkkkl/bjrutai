"""Invented checkout data shared by SQLite and disposable MySQL tests."""

from uuid import uuid4

from src.api.mall_deps import MallActor
from src.models.mall_catalog import MallCategory, MallProduct, MallSku
from src.services.mall_settings_service import get_mall_settings
from tests.conftest import seed_user


async def checkout_seed(db):
    identity = uuid4().hex
    buyer = await seed_user(db, user_type="personal", openid=f"checkout-{identity}")
    actor = MallActor("user", buyer, frozenset())
    settings = await get_mall_settings(db)
    settings.enabled = settings.purchase_enabled = True
    settings.freight_mode, settings.freight_cent = "fixed", 1000
    settings.blocked_regions = []
    settings.policy_versions = {"policy": "mall-test-v1"}
    category = MallCategory(name=f"食品-{identity}", status="enabled")
    db.add(category)
    await db.flush()
    product = MallProduct(name="测试谷物", category_id=category.id, status="on_sale")
    db.add(product)
    await db.flush()
    skus = [
        MallSku(
            product_id=product.id,
            sku_code=f"{identity}-{i}",
            sale_price_cent=price,
            available_qty=10,
            options={},
        )
        for i, price in enumerate((10000, 5000))
    ]
    db.add_all(skus)
    await db.flush()
    return actor, settings, product, skus


ADDRESS = {
    "recipientName": "测试收件人",
    "phone": "13800001234",
    "regionCodes": ["110000", "110100", "110101"],
    "addressLine": "虚构路123号测试室",
    "consentVersion": "mall-test-v1",
    "consentConfirmed": True,
}
