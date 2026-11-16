import pytest


@pytest.mark.asyncio
async def test_public_catalog_does_not_require_auth_and_admin_writes_do(client):
    response = await client.get("/api/v1/mall/categories")
    assert response.status_code == 200
    assert response.json()["data"] == {"items": [], "nextCursor": None, "total": 0}
    response = await client.get("/api/v1/mall/products")
    assert response.status_code == 200 and response.json()["data"]["items"] == []
    response = await client.post(
        "/api/v1/admin/mall/products",
        json={"name": "商品"},
        headers={"Idempotency-Key": "catalog-anonymous-probe"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_create_retry_stock_retry_and_public_visibility(client, db_session):
    from datetime import timedelta

    from src.models.mall_base import utc_now
    from src.models.mall_operations import MallFile
    from src.models.role import Role
    from src.models.user import admin_account_roles
    from src.services.mall_settings_service import get_mall_settings
    from tests.conftest import auth_header, make_access_token, seed_admin

    admin_id = await seed_admin(db_session)
    role = Role(
        name="商品运营",
        permissions={
            "permissions": [
                "mall.products.read",
                "mall.products.write",
                "mall.stock.write",
                "mall.stock.read",
            ]
        },
    )
    db_session.add(role)
    await db_session.flush()
    await db_session.execute(
        admin_account_roles.insert().values(admin_account_id=admin_id, role_id=role.id)
    )
    settings = await get_mall_settings(db_session)
    settings.policy_versions = {"policy": "2026-11"}
    file = MallFile(
        object_key="mall/product/cover.jpg",
        purpose="product_image",
        owner_actor_type="admin",
        owner_actor_id=admin_id,
        mime="image/jpeg",
        size=20,
        sha256="a" * 64,
        status="verified",
        expires_at=utc_now() - timedelta(minutes=1),
    )
    db_session.add(file)
    await db_session.commit()
    headers = auth_header(make_access_token(user_id=admin_id, user_type="admin"))
    headers["Idempotency-Key"] = "catalog-category-create"
    category = await client.post(
        "/api/v1/admin/mall/categories", headers=headers, json={"name": "食品", "status": "enabled"}
    )
    assert category.status_code == 200
    category_id = category.json()["data"]["id"]
    body = {
        "name": "燕麦",
        "categoryId": category_id,
        "coverFileId": str(file.id),
        "description": "真实商品说明",
        "deliveryMethod": "express",
        "freightTemplateId": "default",
        "skus": [{"skuCode": "OAT-1", "priceCent": 1500, "initialStock": 0}],
    }
    headers["Idempotency-Key"] = "catalog-product-create"
    invalid = await client.post(
        "/api/v1/admin/mall/products", headers=headers, json={**body, "brandId": "1"}
    )
    assert invalid.status_code == 422
    first = await client.post("/api/v1/admin/mall/products", headers=headers, json=body)
    assert first.status_code == 200, first.text
    product = first.json()["data"]
    assert product["coverFileId"] == str(file.id)
    assert product["galleryFileIds"] == [] and product["sort"] == 0
    assert product["skus"][0]["reservedQuantity"] == 0
    assert product["skus"][0]["warningQuantity"] == 0
    retry = await client.post("/api/v1/admin/mall/products", headers=headers, json=body)
    assert retry.json()["data"]["id"] == product["id"]
    assert (await client.get("/api/v1/mall/products")).json()["data"]["total"] == 0
    headers["Idempotency-Key"] = "catalog-product-publish"
    published = await client.post(
        f'/api/v1/admin/mall/products/{product["id"]}/status',
        headers=headers,
        json={"expectedVersion": product["version"], "targetStatus": "on_sale"},
    )
    assert published.status_code == 200, published.text
    headers["Idempotency-Key"] = "catalog-product-edit-listed"
    listed_edit = await client.patch(
        f'/api/v1/admin/mall/products/{product["id"]}',
        headers=headers,
        json={
            "expectedVersion": published.json()["data"]["version"],
            "product": {"name": "燕麦改名"},
        },
    )
    assert listed_edit.status_code == 409
    assert "先下架" in listed_edit.json()["message"]
    public = (await client.get("/api/v1/mall/products?q=燕麦&sort=price_asc")).json()["data"]
    assert public["total"] == 1 and public["items"][0]["skus"][0]["stockStatus"] == "sold_out"
    assert "coverFileId" not in public["items"][0]
    assert "reservedQuantity" not in public["items"][0]["skus"][0]
    sku = product["skus"][0]
    headers["Idempotency-Key"] = "catalog-stock-replenish"
    change = {"expectedVersion": sku["version"], "deltaAvailableQuantity": 5, "reason": "补货"}
    url = f'/api/v1/admin/mall/skus/{sku["id"]}/stock-adjustments'
    stock = await client.post(url, headers=headers, json=change)
    assert stock.status_code == 200, stock.text
    assert (await client.post(url, headers=headers, json=change)).json()["data"][
        "id"
    ] == stock.json()["data"]["id"]
    detail = (await client.get(f'/api/v1/mall/products/{product["id"]}')).json()["data"]
    assert detail["skus"][0]["availableQuantity"] == 5
    headers["Idempotency-Key"] = "catalog-category-disable"
    assert (
        await client.patch(
            f"/api/v1/admin/mall/categories/{category_id}",
            headers=headers,
            json={"expectedVersion": 1, "category": {"name": "食品", "status": "disabled"}},
        )
    ).status_code == 409
    headers["Idempotency-Key"] = "catalog-product-archive"
    archived = await client.post(
        f'/api/v1/admin/mall/products/{product["id"]}/status',
        headers=headers,
        json={"expectedVersion": published.json()["data"]["version"], "targetStatus": "archived"},
    )
    assert archived.status_code == 200
    assert (await client.get(f'/api/v1/mall/products/{product["id"]}')).status_code == 404
    child = await client.post(
        "/api/v1/admin/mall/categories",
        headers={**headers, "Idempotency-Key": "catalog-child-rejected"},
        json={"name": "谷物", "parentId": category_id, "status": "enabled"},
    )
    assert child.status_code == 422
    assert "仅支持一级分类" in child.json()["message"]

    role.permissions = {"permissions": ["mall.products.read"]}
    await db_session.commit()
    assert (await client.post(url, headers=headers, json=change)).status_code == 403


@pytest.mark.asyncio
async def test_catalog_pagination_and_literal_search_do_not_expose_drafts(client, db_session):
    from src.models.mall_catalog import MallCategory, MallProduct, MallSku

    category = MallCategory(name="在售", status="enabled")
    db_session.add(category)
    await db_session.flush()
    for i in range(3):
        product = MallProduct(name=f"商品{i}", category_id=category.id, status="on_sale")
        db_session.add(product)
        await db_session.flush()
        db_session.add(
            MallSku(product_id=product.id, sku_code=f"PAGE-{i}", sale_price_cent=(3 - i) * 100)
        )
    await db_session.commit()
    newest = (await client.get("/api/v1/mall/products?pageSize=2")).json()["data"]
    newest_rest = (
        await client.get(
            "/api/v1/mall/products",
            params={"pageSize": 2, "cursor": newest["nextCursor"]},
        )
    ).json()["data"]
    assert [p["name"] for p in newest["items"]] == ["商品2", "商品1"]
    assert [p["name"] for p in newest_rest["items"]] == ["商品0"]
    first = (await client.get("/api/v1/mall/products?pageSize=2&sort=price_asc")).json()["data"]
    second = (
        await client.get(
            "/api/v1/mall/products",
            params={"pageSize": 2, "sort": "price_asc", "cursor": first["nextCursor"]},
        )
    ).json()["data"]
    assert first["total"] == 3 and len(second["items"]) == 1
    assert not {p["id"] for p in first["items"]}.intersection(p["id"] for p in second["items"])
    assert (await client.get("/api/v1/mall/products?q=%25")).json()["data"]["total"] == 0
    assert (await client.get("/api/v1/mall/products?cursor=invalid")).status_code == 422
