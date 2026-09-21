"""US1 RED contract tests for the authenticated article comment API."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_list_comments_requires_login(client, published_article):
    response = await client.get(f"/api/v1/articles/{published_article}/comments")

    assert response.status_code == 401
    assert response.json()["code"] == 40100


@pytest.mark.asyncio
async def test_list_comments_returns_visible_items_and_stable_cursor(
    client, db_session, published_article, comment_user, comment_user_auth_headers
):
    from src.models.article_comment import ArticleComment

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            ArticleComment(
                article_id=published_article,
                user_id=comment_user,
                display_name_snapshot="评论用户",
                content="普通评论",
                status="visible",
                moderation_status="passed",
                created_at=now - timedelta(minutes=2),
            ),
            ArticleComment(
                article_id=published_article,
                user_id=comment_user,
                display_name_snapshot="评论用户",
                content="置顶评论",
                status="visible",
                moderation_status="passed",
                is_pinned=True,
                created_at=now - timedelta(minutes=1),
            ),
            ArticleComment(
                article_id=published_article,
                user_id=comment_user,
                display_name_snapshot="评论用户",
                content="审核中不可见",
                status="pending",
                moderation_status="flagged",
                created_at=now,
            ),
        ]
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/articles/{published_article}/comments",
        params={"limit": 1},
        headers=comment_user_auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["items"][0]["content"] == "置顶评论"
    assert payload["data"]["items"][0]["isPinned"] is True
    assert payload["data"]["hasMore"] is True
    assert payload["data"]["nextCursor"]
    assert "审核中不可见" not in str(payload)
    assert "userId" not in payload["data"]["items"][0]

    next_response = await client.get(
        f"/api/v1/articles/{published_article}/comments",
        params={"limit": 1, "cursor": payload["data"]["nextCursor"]},
        headers=comment_user_auth_headers,
    )
    assert next_response.status_code == 200
    assert next_response.json()["data"]["items"][0]["content"] == "普通评论"


@pytest.mark.asyncio
async def test_list_comments_hides_unpublished_articles(client, db_session, comment_user_auth_headers):
    from tests.conftest import seed_article

    article_id = await seed_article(db_session, status="draft")
    response = await client.get(
        f"/api/v1/articles/{article_id}/comments",
        headers=comment_user_auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == 40400


@pytest.mark.asyncio
async def test_create_comment_requires_idempotency_key_and_returns_envelope(
    client, published_article, comment_user_auth_headers
):
    response = await client.post(
        f"/api/v1/articles/{published_article}/comments",
        headers=comment_user_auth_headers,
        json={"content": "这篇文章很实用。😊"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 40000


@pytest.mark.asyncio
async def test_create_comment_returns_visible_or_pending_result(
    client, published_article, comment_user_auth_headers
):
    response = await client.post(
        f"/api/v1/articles/{published_article}/comments",
        headers={**comment_user_auth_headers, "Idempotency-Key": "comment-contract-001"},
        json={"content": "这篇文章很实用。😊"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] in {"visible", "pending"}
    assert data["moderationStatus"] in {"passed", "flagged"}
    assert data["commentId"]


@pytest.mark.asyncio
async def test_create_comment_rejects_invalid_length_without_clearing_client_draft(
    client, published_article, comment_user_auth_headers
):
    response = await client.post(
        f"/api/v1/articles/{published_article}/comments",
        headers={**comment_user_auth_headers, "Idempotency-Key": "comment-contract-002"},
        json={"content": " "},
    )

    assert response.status_code in {400, 422}
    assert response.json()["code"] in {40000, 42200}


@pytest.mark.asyncio
async def test_like_and_unlike_are_idempotent_and_return_count(
    client, db_session, published_article, comment_user, comment_user_auth_headers
):
    from src.models.article_comment import ArticleComment

    comment = ArticleComment(
        article_id=published_article,
        user_id=comment_user,
        display_name_snapshot="评论用户",
        content="可点赞评论",
        status="visible",
        moderation_status="passed",
    )
    db_session.add(comment)
    await db_session.flush()

    path = f"/api/v1/articles/{published_article}/comments/{comment.id}/like"
    first = await client.post(path, headers=comment_user_auth_headers)
    second = await client.post(path, headers=comment_user_auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == {"commentId": str(comment.id), "liked": True, "likeCount": 1}
    assert second.json()["data"] == {"commentId": str(comment.id), "liked": True, "likeCount": 1}

    removed = await client.delete(path, headers=comment_user_auth_headers)
    repeated = await client.delete(path, headers=comment_user_auth_headers)
    assert removed.status_code == 200
    assert repeated.status_code == 200
    assert removed.json()["data"]["liked"] is False
    assert removed.json()["data"]["likeCount"] == 0
    assert repeated.json()["data"]["likeCount"] == 0


@pytest.mark.asyncio
async def test_like_requires_login_and_visible_comment(client, published_article):
    response = await client.post(
        f"/api/v1/articles/{published_article}/comments/1/like"
    )
    assert response.status_code == 401
