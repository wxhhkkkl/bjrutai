"""Integration test: full article lifecycle (US9).

Covers: create -> edit -> publish -> public view -> unpublish -> verify hidden.
"""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import admin_auth_headers, seed_article  # noqa: F401


class TestArticleLifecycle:
    """End-to-end test covering the full article lifecycle."""

    async def test_full_lifecycle(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        # ---- Step 1: Create article (draft by default) ----
        create_payload = {
            "title": "Lifecycle Test Article",
            "summary": "Initial summary",
            "content": "<p>Initial content</p>",
            "category": "policy",
            "tags": ["test", "lifecycle"],
        }
        resp = await client.post(
            "/api/v1/admin/articles",
            json=create_payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        created = resp.json()["data"]
        article_id = created["articleId"]
        assert created["title"] == "Lifecycle Test Article"
        assert created["status"] == "draft"

        # ---- Step 2: Verify draft is NOT visible publicly ----
        resp = await client.get("/api/v1/articles")
        assert not any(
            item.get("articleId") == article_id
            for item in resp.json()["data"]["items"]
        )

        # ---- Step 2b: Verify draft detail returns 404 publicly ----
        resp = await client.get(f"/api/v1/articles/{article_id}")
        assert resp.status_code == 404

        # ---- Step 3: Edit the article (update title and summary) ----
        # First get current version from admin detail via admin list
        resp = await client.get(
            "/api/v1/admin/articles",
            params={"keyword": "Lifecycle Test Article"},
            headers=admin_auth_headers,
        )
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        current_version = items[0]["version"]

        update_payload = {
            "title": "Lifecycle Test Article (Revised)",
            "summary": "Updated summary after edit",
            "version": current_version,
        }
        resp = await client.put(
            f"/api/v1/admin/articles/{article_id}",
            json=update_payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        updated = resp.json()["data"]
        assert updated["title"] == "Lifecycle Test Article (Revised)"
        assert updated["status"] == "draft"

        # ---- Step 4: Publish the article ----
        resp = await client.post(
            f"/api/v1/admin/articles/{article_id}/publish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        published = resp.json()["data"]
        assert published["status"] == "published"
        assert published["publishedAt"] is not None

        # ---- Step 5: Verify article IS visible publicly now ----
        resp = await client.get("/api/v1/articles")
        pub_items = resp.json()["data"]["items"]
        matching = [
            item for item in pub_items
            if item.get("articleId") == article_id
        ]
        assert len(matching) == 1
        assert matching[0]["title"] == "Lifecycle Test Article (Revised)"

        # ---- Step 6: View detail publicly and verify view count ----
        resp = await client.get(f"/api/v1/articles/{article_id}")
        assert resp.status_code == 200
        detail = resp.json()["data"]
        assert detail["title"] == "Lifecycle Test Article (Revised)"
        assert detail["content"] == "<p>Initial content</p>"
        assert detail["viewCount"] >= 1

        # ---- Step 7: Unpublish the article ----
        resp = await client.post(
            f"/api/v1/admin/articles/{article_id}/unpublish",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        unpublished = resp.json()["data"]
        assert unpublished["status"] == "unpublished"

        # ---- Step 8: Verify article is HIDDEN publicly ----
        resp = await client.get("/api/v1/articles")
        assert not any(
            item.get("articleId") == article_id
            for item in resp.json()["data"]["items"]
        )

        # Detail should also return 404
        resp = await client.get(f"/api/v1/articles/{article_id}")
        assert resp.status_code == 404

        # ---- Step 9: Admin can still see it ----
        resp = await client.get(
            "/api/v1/admin/articles",
            params={"status": "unpublished"},
            headers=admin_auth_headers,
        )
        items = resp.json()["data"]["items"]
        assert any(
            item.get("articleId") == article_id for item in items
        )

    async def test_version_increments_on_update(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        """Each successful update increments the version number."""
        art_id = await seed_article(
            db_session, title="Version Test", status="draft", version=1,
        )

        # Update once
        resp = await client.put(
            f"/api/v1/admin/articles/{art_id}",
            json={"title": "V2", "version": 1},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200

        # Update again with new version
        resp = await client.put(
            f"/api/v1/admin/articles/{art_id}",
            json={"title": "V3", "version": 2},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200

        # Verify version has incremented
        resp = await client.get(
            "/api/v1/admin/articles",
            params={"keyword": "V3"},
            headers=admin_auth_headers,
        )
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["version"] == 3

    async def test_concurrent_edit_conflict(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        """Simulate two editors racing: second edit with stale version fails."""
        art_id = await seed_article(
            db_session, title="Race Condition", status="draft", version=1,
        )

        # First edit succeeds (version 1 -> 2)
        resp1 = await client.put(
            f"/api/v1/admin/articles/{art_id}",
            json={"title": "Edit by User A", "version": 1},
            headers=admin_auth_headers,
        )
        assert resp1.status_code == 200

        # Second edit with stale version 1 fails
        resp2 = await client.put(
            f"/api/v1/admin/articles/{art_id}",
            json={"title": "Edit by User B (stale)", "version": 1},
            headers=admin_auth_headers,
        )
        assert resp2.status_code == 409

        # But edit with correct version 2 succeeds
        resp3 = await client.put(
            f"/api/v1/admin/articles/{art_id}",
            json={"title": "Edit by User B (fresh)", "version": 2},
            headers=admin_auth_headers,
        )
        assert resp3.status_code == 200
