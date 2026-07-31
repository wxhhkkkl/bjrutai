"""Contract tests for article category CRUD."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import assert_response_envelope, make_access_token, seed_admin


def _admin_auth() -> dict:
    token = make_access_token(user_id=1, user_type="admin",
                              permissions=["articles.read", "articles.write"])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_category_crud_flow(db_session: AsyncSession, client: AsyncClient):
    """Full CRUD: create → list → update → delete → delete-protected."""
    await seed_admin(db_session, username="admin")

    # Create
    resp = await client.post("/api/v1/admin/categories",
                             json={"name": "政策解读", "sort_order": 1},
                             headers=_admin_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert_response_envelope(data)
    cat_id = data["data"]["id"]

    # List
    resp = await client.get("/api/v1/admin/categories", headers=_admin_auth())
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["name"] == "政策解读"

    # Update
    resp = await client.put(f"/api/v1/admin/categories/{cat_id}",
                            json={"name": "政策法规", "sort_order": 2},
                            headers=_admin_auth())
    assert resp.status_code == 200

    # Create an article referencing this category via ORM
    from src.models.article import Article, ArticleStatus
    article = Article(title="测试文章", content="内容", category_id=int(cat_id),
                      status=ArticleStatus.DRAFT, version=1)
    db_session.add(article)
    await db_session.commit()

    # Delete should fail (article exists)
    resp = await client.delete(f"/api/v1/admin/categories/{cat_id}",
                              headers=_admin_auth())
    assert resp.status_code == 409

    # Clean article, delete should succeed
    await db_session.delete(article)
    await db_session.commit()
    resp = await client.delete(f"/api/v1/admin/categories/{cat_id}",
                              headers=_admin_auth())
    assert resp.status_code == 200
