"""Contract tests for Article public and admin endpoints (US9)."""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import admin_auth_headers, seed_article  # noqa: F401


# ============================================================================
# GET /api/v1/articles -- Public list (published only)
# ============================================================================
class TestPublicListArticles:
    async def test_returns_only_published_articles(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await seed_article(
            db_session, title="Pub1", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_article(db_session, title="Draft1", status="draft")
        await seed_article(db_session, title="Unpub1", status="unpublished")

        resp = await client.get("/api/v1/articles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        items = data["data"]["items"]
        titles = {item["title"] for item in items}
        assert "Pub1" in titles
        assert "Draft1" not in titles
        assert "Unpub1" not in titles

    async def test_keyword_search_filters_by_title(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await seed_article(
            db_session, title="Alpha Beta", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_article(
            db_session, title="Gamma Delta", status="published",
            published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get("/api/v1/articles", params={"keyword": "Alpha"})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Alpha Beta"

    async def test_keyword_search_filters_by_summary(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await seed_article(
            db_session, title="T1", summary="unique keyword here",
            status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_article(
            db_session, title="T2", summary="other stuff", status="published",
            published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/articles", params={"keyword": "unique keyword"}
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["title"] == "T1"

    async def test_category_filter(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await seed_article(
            db_session, title="Cat A", category="policy", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_article(
            db_session, title="Cat B", category="product", status="published",
            published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/articles", params={"category": "policy"}
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Cat A"

    async def test_cursor_pagination_returns_next_cursor(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        for i in range(5):
            await seed_article(
                db_session, title=f"Article {i}", status="published",
                published_at=datetime(2026, 7, i + 1, tzinfo=timezone.utc),
            )

        resp = await client.get("/api/v1/articles", params={"limit": 3})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 3
        assert data["hasMore"] is True
        assert data["nextCursor"] is not None

        resp2 = await client.get(
            "/api/v1/articles",
            params={"cursor": data["nextCursor"], "limit": 3},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()["data"]
        assert len(data2["items"]) == 2
        assert data2["hasMore"] is False

    async def test_empty_list_returns_zero_items(self, client: AsyncClient):
        resp = await client.get("/api/v1/articles")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["hasMore"] is False
        assert data["nextCursor"] is None


# ============================================================================
# GET /api/v1/articles/{id} -- Public detail
# ============================================================================
class TestPublicArticleDetail:
    async def test_published_article_returns_detail(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        art_id = await seed_article(
            db_session, title="Detail Test", content="<p>Rich content</p>",
            summary="Summary text", status="published",
            published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(f"/api/v1/articles/{art_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        article = data["data"]
        assert article["title"] == "Detail Test"
        assert article["content"] == "<p>Rich content</p>"
        assert article["summary"] == "Summary text"
        assert article["status"] == "published"

    async def test_published_article_increments_view_count(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        art_id = await seed_article(
            db_session, title="View Count", status="published",
            published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp1 = await client.get(f"/api/v1/articles/{art_id}")
        assert resp1.status_code == 200
        vc1 = resp1.json()["data"]["viewCount"]

        resp2 = await client.get(f"/api/v1/articles/{art_id}")
        assert resp2.status_code == 200
        vc2 = resp2.json()["data"]["viewCount"]
        assert vc2 == vc1 + 1

    async def test_draft_article_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        art_id = await seed_article(db_session, title="Draft", status="draft")
        resp = await client.get(f"/api/v1/articles/{art_id}")
        assert resp.status_code == 404

    async def test_unpublished_article_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        art_id = await seed_article(
            db_session, title="Unpub", status="unpublished"
        )
        resp = await client.get(f"/api/v1/articles/{art_id}")
        assert resp.status_code == 404

    async def test_nonexistent_article_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/v1/articles/99999")
        assert resp.status_code == 404


# ============================================================================
# GET /api/v1/admin/articles -- Admin list
# ============================================================================
class TestAdminListArticles:
    async def test_admin_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        resp = await client.get("/api/v1/admin/articles")
        assert resp.status_code in (401, 403)

    async def test_admin_lists_all_statuses(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        await seed_article(db_session, title="Draft", status="draft")
        await seed_article(
            db_session, title="Pub", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_article(db_session, title="Unpub", status="unpublished")

        resp = await client.get(
            "/api/v1/admin/articles", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        titles = {item["title"] for item in items}
        assert "Draft" in titles
        assert "Pub" in titles
        assert "Unpub" in titles

    async def test_admin_filter_by_status(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        await seed_article(db_session, title="Draft", status="draft")
        await seed_article(
            db_session, title="Pub", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/admin/articles",
            params={"status": "draft"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Draft"

    async def test_admin_keyword_search(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        await seed_article(
            db_session, title="Alpha", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_article(
            db_session, title="Beta", status="published",
            published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/admin/articles",
            params={"keyword": "Alpha"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Alpha"

    async def test_admin_cursor_pagination(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        for i in range(5):
            await seed_article(
                db_session, title=f"Art {i}", status="published",
                published_at=datetime(2026, 7, i + 1, tzinfo=timezone.utc),
            )

        resp = await client.get(
            "/api/v1/admin/articles",
            params={"limit": 3},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 3
        assert data["hasMore"] is True
        assert data["nextCursor"] is not None


# ============================================================================
# POST /api/v1/admin/articles -- Create article
# ============================================================================
class TestCreateArticle:
    async def test_create_article_with_minimal_fields(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        payload = {"title": "New Article", "content": "<p>Body</p>"}
        resp = await client.post(
            "/api/v1/admin/articles", json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["title"] == "New Article"
        assert data["data"]["status"] == "draft"
        assert "articleId" in data["data"]

    async def test_create_article_with_all_fields(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        payload = {
            "title": "Full Article",
            "summary": "A comprehensive summary",
            "content": "<p>Rich content with <b>bold</b></p>",
            "coverImageUrl": "https://oss.example.com/cover.jpg",
            "category": "policy",
            "tags": ["tag1", "tag2", "Q3"],
        }
        resp = await client.post(
            "/api/v1/admin/articles", json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "Full Article"
        assert data["status"] == "draft"

    async def test_create_article_requires_admin_auth(self, client: AsyncClient):
        payload = {"title": "No Auth"}
        resp = await client.post("/api/v1/admin/articles", json=payload)
        assert resp.status_code in (401, 403)

    async def test_create_article_missing_title_fails(
        self, client: AsyncClient, admin_auth_headers: dict,
    ):
        payload = {"content": "<p>Missing title</p>"}
        resp = await client.post(
            "/api/v1/admin/articles", json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422

    async def test_create_article_content_too_long(
        self, client: AsyncClient, admin_auth_headers: dict,
    ):
        payload = {"title": "Long Content", "content": "x" * 100001}
        resp = await client.post(
            "/api/v1/admin/articles", json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422


# ============================================================================
# PUT /api/v1/admin/articles/{id} -- Update article
# ============================================================================
class TestUpdateArticle:
    async def test_update_draft_article(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="Original", content="<p>Old</p>",
            status="draft", version=1,
        )
        payload = {
            "title": "Updated Title", "summary": "New summary", "version": 1,
        }
        resp = await client.put(
            f"/api/v1/admin/articles/{art_id}", json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "Updated Title"
        assert data["status"] == "draft"

    async def test_update_with_version_conflict(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="Conflict", status="draft", version=3,
        )
        payload = {"title": "Stale Update", "version": 1}
        resp = await client.put(
            f"/api/v1/admin/articles/{art_id}", json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409

    async def test_update_nonexistent_article_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict,
    ):
        payload = {"title": "Ghost", "version": 1}
        resp = await client.put(
            "/api/v1/admin/articles/99999", json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    async def test_update_partial_fields(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="Original", summary="Old summary",
            content="<p>Body</p>", status="draft", version=1,
        )
        payload = {"summary": "New summary only", "version": 1}
        resp = await client.put(
            f"/api/v1/admin/articles/{art_id}", json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        # Verify title was preserved
        resp2 = await client.get(
            "/api/v1/admin/articles",
            params={"keyword": "Original"},
            headers=admin_auth_headers,
        )
        items = resp2.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["summary"] == "New summary only"
        assert items[0]["title"] == "Original"


# ============================================================================
# POST /api/v1/admin/articles/{id}/publish -- Publish article
# ============================================================================
class TestPublishArticle:
    async def test_publish_draft_transitions_to_published(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="To Publish", status="draft",
        )
        resp = await client.post(
            f"/api/v1/admin/articles/{art_id}/publish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "published"
        assert data["publishedAt"] is not None

    async def test_publish_unpublished_transitions_to_published(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="Re-pub", status="unpublished",
        )
        resp = await client.post(
            f"/api/v1/admin/articles/{art_id}/publish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "published"

    async def test_publish_already_published_returns_error(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="Already Pub", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        resp = await client.post(
            f"/api/v1/admin/articles/{art_id}/publish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400

    async def test_publish_nonexistent_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict,
    ):
        resp = await client.post(
            "/api/v1/admin/articles/99999/publish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    async def test_publish_requires_admin_auth(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        art_id = await seed_article(
            db_session, title="No Auth Pub", status="draft",
        )
        resp = await client.post(
            f"/api/v1/admin/articles/{art_id}/publish",
        )
        assert resp.status_code in (401, 403)


# ============================================================================
# POST /api/v1/admin/articles/{id}/unpublish -- Unpublish article
# ============================================================================
class TestUnpublishArticle:
    async def test_unpublish_published_transitions_to_unpublished(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="To Unpub", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        resp = await client.post(
            f"/api/v1/admin/articles/{art_id}/unpublish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "unpublished"

    async def test_unpublish_draft_returns_error(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="Draft Unpub", status="draft",
        )
        resp = await client.post(
            f"/api/v1/admin/articles/{art_id}/unpublish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400

    async def test_unpublish_removes_from_public_list(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        art_id = await seed_article(
            db_session, title="Hide Me", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        # Verify it is publicly visible
        resp1 = await client.get("/api/v1/articles")
        assert any(
            item["title"] == "Hide Me"
            for item in resp1.json()["data"]["items"]
        )

        # Unpublish
        await client.post(
            f"/api/v1/admin/articles/{art_id}/unpublish",
            headers=admin_auth_headers,
        )

        # Verify it is hidden from public
        resp2 = await client.get("/api/v1/articles")
        assert not any(
            item["title"] == "Hide Me"
            for item in resp2.json()["data"]["items"]
        )

    async def test_unpublish_nonexistent_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict,
    ):
        resp = await client.post(
            "/api/v1/admin/articles/99999/unpublish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    async def test_unpublish_requires_admin_auth(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        art_id = await seed_article(
            db_session, title="No Auth Unpub", status="published",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        resp = await client.post(
            f"/api/v1/admin/articles/{art_id}/unpublish",
        )
        assert resp.status_code in (401, 403)
