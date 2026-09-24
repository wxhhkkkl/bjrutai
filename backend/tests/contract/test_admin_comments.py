"""RED contract tests for comment-management permissions."""

import pytest


def test_system_admin_seed_contains_comment_permissions():
    from src.services.seed_service import _ALL_PERMISSIONS

    assert "comments.read" in _ALL_PERMISSIONS["permissions"]
    assert "comments.write" in _ALL_PERMISSIONS["permissions"]


def test_comment_management_routes_are_registered_with_separate_permissions():
    from src.main import app

    routes = {route.path: route for route in app.routes}
    assert "/api/v1/admin/comments" in routes
    assert "/api/v1/admin/comments/{comment_id}" in routes
    assert "/api/v1/articles/{article_id}/comments" in routes


@pytest.mark.asyncio
async def test_admin_can_filter_comments_and_receives_preview_only(
    client, db_session, published_article, comment_user, comment_admin_read_headers
):
    from src.models.article_comment import ArticleComment

    db_session.add(
        ArticleComment(
            article_id=published_article,
            user_id=comment_user,
            display_name_snapshot="评论用户",
            content=(
                "这是一段超过一百字的评论正文，用于验证后台列表只返回摘要而不是完整正文。"
                * 3
            ),
            status="pending",
            moderation_status="flagged",
        )
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/admin/comments",
        params={"status": "pending", "keyword": "评论正文", "limit": 20},
        headers=comment_admin_read_headers,
    )
    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["status"] == "pending"
    assert len(item["contentPreview"]) <= 100
    assert "手机" not in str(item)
    assert "userId" not in item


@pytest.mark.asyncio
async def test_admin_write_actions_pin_hide_restore_and_delete(
    client, db_session, published_article, comment_user, comment_admin_write_headers
):
    from src.models.article_comment import ArticleComment

    first = ArticleComment(
        article_id=published_article,
        user_id=comment_user,
        display_name_snapshot="评论用户",
        content="第一条评论",
        status="visible",
        moderation_status="passed",
    )
    second = ArticleComment(
        article_id=published_article,
        user_id=comment_user,
        display_name_snapshot="评论用户",
        content="第二条评论",
        status="visible",
        moderation_status="passed",
    )
    db_session.add_all([first, second])
    await db_session.flush()

    pin = await client.patch(
        f"/api/v1/admin/comments/{first.id}",
        headers=comment_admin_write_headers,
        json={"action": "pin", "expectedVersion": first.version},
    )
    assert pin.status_code == 200
    assert pin.json()["data"]["isPinned"] is True

    second_pin = await client.patch(
        f"/api/v1/admin/comments/{second.id}",
        headers=comment_admin_write_headers,
        json={"action": "pin", "expectedVersion": second.version},
    )
    assert second_pin.status_code == 200
    await db_session.refresh(first)
    assert first.is_pinned is False
    assert second_pin.json()["data"]["isPinned"] is True

    hidden = await client.patch(
        f"/api/v1/admin/comments/{second.id}",
        headers=comment_admin_write_headers,
        json={"action": "hide", "reason": "需要人工复核", "expectedVersion": 2},
    )
    assert hidden.status_code == 200
    assert hidden.json()["data"]["status"] == "hidden"

    restored = await client.patch(
        f"/api/v1/admin/comments/{second.id}",
        headers=comment_admin_write_headers,
        json={"action": "restore", "expectedVersion": 3},
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "visible"

    deleted = await client.patch(
        f"/api/v1/admin/comments/{second.id}",
        headers=comment_admin_write_headers,
        json={"action": "delete", "reason": "用户要求删除", "expectedVersion": 4},
    )
    assert deleted.status_code == 200
    assert deleted.json()["data"]["status"] == "deleted"


@pytest.mark.asyncio
async def test_admin_action_rejects_stale_version_and_missing_reason(
    client, db_session, published_article, comment_user, comment_admin_write_headers
):
    from src.models.article_comment import ArticleComment

    comment = ArticleComment(
        article_id=published_article,
        user_id=comment_user,
        display_name_snapshot="评论用户",
        content="待审核评论",
        status="pending",
        moderation_status="flagged",
    )
    db_session.add(comment)
    await db_session.flush()

    missing_reason = await client.patch(
        f"/api/v1/admin/comments/{comment.id}",
        headers=comment_admin_write_headers,
        json={"action": "reject", "expectedVersion": comment.version},
    )
    assert missing_reason.status_code == 400

    stale = await client.patch(
        f"/api/v1/admin/comments/{comment.id}",
        headers=comment_admin_write_headers,
        json={"action": "approve", "expectedVersion": 999},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == 40910


@pytest.mark.asyncio
async def test_admin_write_requires_comments_write(client, comment_admin_read_headers):
    response = await client.patch(
        "/api/v1/admin/comments/1",
        headers=comment_admin_read_headers,
        json={"action": "approve", "expectedVersion": 1},
    )
    assert response.status_code == 403
    assert response.json()["code"] == 40300
