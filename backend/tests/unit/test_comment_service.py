"""US1 RED tests for comment domain operations."""

import pytest


@pytest.mark.asyncio
async def test_create_comment_snapshots_identity_and_applies_defaults(
    db_session, published_article, comment_user
):
    from src.services.comment_service import create_comment

    comment = await create_comment(
        db_session,
        article_id=published_article,
        user_id=comment_user,
        content="文章很实用。😊",
        idempotency_key="service-comment-001",
    )

    assert comment.article_id == published_article
    assert comment.user_id == comment_user
    assert comment.display_name_snapshot == "评论用户"
    assert comment.avatar_url_snapshot == "https://example.com/comment-user.png"
    assert comment.like_count == 0
    assert comment.version == 1
    assert comment.status in {"visible", "pending"}


@pytest.mark.asyncio
async def test_create_comment_reuses_identical_idempotency_and_rejects_changed_payload(
    db_session, published_article, comment_user
):
    from src.core.exceptions import ConflictException
    from src.services.comment_service import create_comment

    first = await create_comment(
        db_session,
        article_id=published_article,
        user_id=comment_user,
        content="第一次评论",
        idempotency_key="service-comment-002",
    )
    replay = await create_comment(
        db_session,
        article_id=published_article,
        user_id=comment_user,
        content="第一次评论",
        idempotency_key="service-comment-002",
    )
    assert replay.id == first.id

    with pytest.raises(ConflictException) as exc_info:
        await create_comment(
            db_session,
            article_id=published_article,
            user_id=comment_user,
            content="不同正文",
            idempotency_key="service-comment-002",
        )
    assert exc_info.value.code == 40911


@pytest.mark.asyncio
async def test_create_comment_enforces_three_submissions_per_minute(
    db_session, published_article, comment_user, comment_clock
):
    from src.core.exceptions import BadRequestException
    from src.services.comment_service import create_comment

    for index in range(3):
        await create_comment(
            db_session,
            article_id=published_article,
            user_id=comment_user,
            content=f"第{index + 1}条评论",
            idempotency_key=f"service-rate-{index}",
            now=comment_clock.now(),
        )

    with pytest.raises(BadRequestException, match="每分钟最多提交 3 条"):
        await create_comment(
            db_session,
            article_id=published_article,
            user_id=comment_user,
            content="第4条评论",
            idempotency_key="service-rate-4",
            now=comment_clock.now(),
        )

    comment_clock.advance(minutes=1, seconds=1)
    await create_comment(
        db_session,
        article_id=published_article,
        user_id=comment_user,
        content="窗口已恢复",
        idempotency_key="service-rate-5",
        now=comment_clock.now(),
    )


@pytest.mark.asyncio
async def test_like_and_unlike_keep_relationship_and_count_idempotent(
    db_session, published_article, comment_user
):
    from src.models.article_comment import ArticleComment
    from src.models.comment_like import CommentLike
    from src.services.comment_service import like_comment, unlike_comment

    comment = ArticleComment(
        article_id=published_article,
        user_id=comment_user,
        display_name_snapshot="评论用户",
        content="服务点赞评论",
        status="visible",
        moderation_status="passed",
    )
    db_session.add(comment)
    await db_session.flush()

    first = await like_comment(
        db_session, article_id=published_article, comment_id=comment.id, user_id=comment_user
    )
    replay = await like_comment(
        db_session, article_id=published_article, comment_id=comment.id, user_id=comment_user
    )
    assert first == replay == {"commentId": str(comment.id), "liked": True, "likeCount": 1}

    removed = await unlike_comment(
        db_session, article_id=published_article, comment_id=comment.id, user_id=comment_user
    )
    repeated = await unlike_comment(
        db_session, article_id=published_article, comment_id=comment.id, user_id=comment_user
    )
    assert removed == repeated == {"commentId": str(comment.id), "liked": False, "likeCount": 0}
    assert (await db_session.execute(
        __import__("sqlalchemy").select(CommentLike).where(CommentLike.comment_id == comment.id)
    )).scalars().all() == []


@pytest.mark.asyncio
async def test_like_rejects_hidden_comment(db_session, published_article, comment_user):
    from src.core.exceptions import NotFoundException
    from src.models.article_comment import ArticleComment
    from src.services.comment_service import like_comment

    comment = ArticleComment(
        article_id=published_article,
        user_id=comment_user,
        display_name_snapshot="评论用户",
        content="隐藏评论",
        status="hidden",
        moderation_status="passed",
    )
    db_session.add(comment)
    await db_session.flush()

    with pytest.raises(NotFoundException):
        await like_comment(
            db_session, article_id=published_article, comment_id=comment.id, user_id=comment_user
        )
