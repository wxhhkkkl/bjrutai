"""Contract tests for public and administrator banner endpoints."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.banner import Banner, BannerActionType, BannerStatus
from tests.conftest import admin_auth_headers  # noqa: F401


async def _banner(
    db: AsyncSession,
    *,
    title: str,
    status: BannerStatus = BannerStatus.DISABLED,
    sort_order: int = 0,
    action_type: BannerActionType = BannerActionType.NONE,
    article_id: int | None = None,
) -> Banner:
    item = Banner(
        title=title,
        image_url=f"https://example.com/{title}.png",
        status=status,
        sort_order=sort_order,
        action_type=action_type,
        article_id=article_id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


class TestPublicBanners:
    async def test_returns_only_enabled_banners_in_display_order(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        await _banner(db_session, title="later", status=BannerStatus.ENABLED, sort_order=20)
        await _banner(db_session, title="hidden", status=BannerStatus.DISABLED, sort_order=0)
        first = await _banner(
            db_session,
            title="first",
            status=BannerStatus.ENABLED,
            sort_order=10,
            action_type=BannerActionType.ARTICLE,
            article_id=12,
        )

        response = await client.get("/api/v1/banners")

        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert [item["title"] for item in items] == ["first", "later"]
        assert items[0] == {
            "bannerId": str(first.id),
            "title": "first",
            "imageUrl": "https://example.com/first.png",
            "actionType": "article",
            "articleId": "12",
            "sortOrder": 10,
        }


class TestAdminBanners:
    async def test_admin_can_create_enable_update_and_delete_banner(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        create = await client.post("/api/v1/admin/banners", headers=admin_auth_headers, json={
            "title": "秋季健康活动",
            "imageUrl": "https://example.com/autumn.webp",
            "actionType": "article",
            "articleId": 8,
            "sortOrder": 3,
        })
        assert create.status_code == 200
        banner_id = create.json()["data"]["bannerId"]
        assert create.json()["data"]["status"] == "disabled"

        assert (await client.get("/api/v1/banners")).json()["data"]["items"] == []
        assert (await client.post(
            f"/api/v1/admin/banners/{banner_id}/enable", headers=admin_auth_headers
        )).status_code == 200

        public = await client.get("/api/v1/banners")
        assert public.json()["data"]["items"][0]["title"] == "秋季健康活动"

        listed = await client.get("/api/v1/admin/banners", headers=admin_auth_headers)
        item = listed.json()["data"]["items"][0]
        update = await client.put(f"/api/v1/admin/banners/{banner_id}", headers=admin_auth_headers, json={
            "title": "秋季健康服务",
            "actionType": "none",
            "sortOrder": 1,
            "version": item["version"],
        })
        assert update.status_code == 200
        assert update.json()["data"]["version"] == item["version"] + 1

        after_update = (await client.get("/api/v1/banners")).json()["data"]["items"][0]
        assert after_update["actionType"] == "none"
        assert after_update["articleId"] is None

        assert (await client.delete(
            f"/api/v1/admin/banners/{banner_id}", headers=admin_auth_headers
        )).status_code == 200
        assert (await client.get("/api/v1/banners")).json()["data"]["items"] == []

    async def test_admin_endpoints_require_administrator(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/banners")
        assert response.status_code == 401

    async def test_article_action_requires_a_positive_article_id(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        response = await client.post("/api/v1/admin/banners", headers=admin_auth_headers, json={
            "imageUrl": "https://example.com/banner.png",
            "actionType": "article",
        })
        assert response.status_code == 422
