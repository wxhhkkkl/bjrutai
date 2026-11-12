"""Operator upload -> publish -> browse -> off-sale/restock -> archive acceptance.

The object store is an explicit in-memory test double, never a live COS claim.
"""

import pytest
from sqlalchemy import select

from src.models.mall_catalog import MallSku, MallStockMovement
from src.models.role import Role
from src.models.user import admin_account_roles
from tests.conftest import auth_header, make_access_token, seed_admin


@pytest.mark.asyncio
async def test_operator_catalog_flow_uses_verified_images_and_keeps_history(client, db_session):
    from src.api.v1.mall_files import get_mall_store
    from src.main import app
    from src.services.mall_settings_service import get_mall_settings

    class Store:
        async def issue_upload_ticket(self, **kwargs):
            return {"uploadToken": "https://storage.invalid/staging"}

        async def head(self, key):
            return {"mime": "image/jpeg", "size": 32, "sha256": "a" * 64}

        async def finalize(self, source_key, destination_key):
            assert source_key.startswith("mall/product_image/")
            assert destination_key.startswith("mall/verified/")

    app.dependency_overrides[get_mall_store] = lambda: Store()
    admin_id = await seed_admin(db_session)
    role = Role(
        name="商城故事验收",
        permissions={
            "permissions": [
                "mall.products.read",
                "mall.products.write",
                "mall.stock.read",
                "mall.stock.write",
                "mall.files.read",
                "mall.files.write",
            ]
        },
    )
    db_session.add(role)
    await db_session.flush()
    await db_session.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    settings = await get_mall_settings(db_session)
    settings.policy_versions = {"policy": "test-policy-v1"}
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=admin_id, user_type="admin"))
    root = "/api/v1/admin/mall"

    async def write(path, body=None, method="post"):
        headers["Idempotency-Key"] = f"catalog-flow-step-{write.sequence:04d}"
        write.sequence += 1
        result = await getattr(client, method)(root + path, headers=headers, json=body)
        assert result.status_code == 200, result.text
        return result.json()["data"]

    write.sequence = 1
    category = await write("/categories", {"name": "日常食品", "status": "enabled"})
    ticket = await write(
        "/files/upload-ticket",
        {
            "purpose": "product_image",
            "fileName": "cover.jpg",
            "contentType": "image/jpeg",
            "fileSize": 32,
            "sha256": "a" * 64,
        },
    )
    await write(f'/files/{ticket["fileId"]}/verify')
    product = await write(
        "/products",
        {
            "name": "谷物",
            "categoryId": category["id"],
            "coverFileId": ticket["fileId"],
            "description": "真实说明",
            "sort": 5,
            "skus": [{"skuCode": "FLOW-1", "priceCent": 2990, "initialStock": 2}],
        },
    )
    product = await write(
        f'/products/{product["id"]}/status',
        {
            "expectedVersion": product["version"],
            "targetStatus": "on_sale",
        },
    )
    visible = (await client.get("/api/v1/mall/products?q=谷物")).json()["data"]
    assert visible["items"][0]["skus"][0]["priceCent"] == 2990
    assert "coverFileId" not in visible["items"][0]
    product = await write(
        f'/products/{product["id"]}/status',
        {
            "expectedVersion": product["version"],
            "targetStatus": "off_sale",
        },
    )
    sku = product["skus"][0]
    await write(
        f'/skus/{sku["id"]}/stock-adjustments',
        {
            "expectedVersion": sku["version"],
            "deltaAvailableQuantity": 3,
            "reason": "补货验收",
        },
    )
    assert (await client.get("/api/v1/mall/products")).json()["data"]["total"] == 0
    assert (await client.get(f'/api/v1/mall/products/{product["id"]}')).status_code == 404
    await write(
        f'/products/{product["id"]}/status',
        {
            "expectedVersion": product["version"],
            "targetStatus": "archived",
        },
    )
    saved = await db_session.get(MallSku, int(sku["id"]), populate_existing=True)
    assert saved.status == "archived" and saved.available_qty == 5
    history = (
        await db_session.scalars(
            select(MallStockMovement).where(MallStockMovement.sku_id == saved.id)
        )
    ).all()
    assert len(history) == 2 and sum(event.available_delta for event in history) == 5
