"""RED tests for the seven-day deleted-comment retention boundary."""

from datetime import timedelta

import pytest


@pytest.mark.asyncio
async def test_cleanup_keeps_deleted_rows_for_seven_days_and_purges_on_day_eight(
    db_session, comment_clock
):
    from src.models.article_comment import ArticleComment
    from src.services.comment_service import purge_expired_deleted_comments

    comment = ArticleComment(
        article_id=1,
        display_name_snapshot="评论用户",
        content="待清理评论",
        status="deleted",
        deleted_at=comment_clock.now() - timedelta(days=6, hours=23),
    )
    db_session.add(comment)
    await db_session.flush()

    deleted_count = await purge_expired_deleted_comments(
        db_session,
        now=comment_clock.now(),
        batch_size=100,
    )
    assert deleted_count == 0
    assert comment.content == "待清理评论"

    comment.deleted_at = comment_clock.now() - timedelta(days=8)
    await db_session.flush()
    deleted_count = await purge_expired_deleted_comments(
        db_session,
        now=comment_clock.now(),
        batch_size=100,
    )
    assert deleted_count == 1
    assert comment.content is None
    assert comment.moderation_reason is None
