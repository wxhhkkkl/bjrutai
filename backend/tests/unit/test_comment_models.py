"""RED tests for the foundational article-comment persistence contract."""

import pytest
from sqlalchemy import UniqueConstraint


@pytest.mark.asyncio
async def test_comment_models_expose_state_and_count_defaults(db_session):
    from src.models.article_comment import ArticleComment

    comment = ArticleComment(
        article_id=1,
        user_id=1,
        display_name_snapshot="评论用户",
        content="测试评论",
    )
    db_session.add(comment)
    await db_session.flush()
    assert comment.status == "pending"
    assert comment.moderation_status == "pending"
    assert comment.is_pinned is False
    assert comment.like_count == 0
    assert comment.version == 1


def test_comment_like_has_database_level_user_uniqueness():
    from src.models.comment_like import CommentLike

    unique_sets = {
        tuple(constraint.columns.keys())
        for constraint in CommentLike.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("comment_id", "user_id") in unique_sets


def test_comment_action_keeps_business_timeline_without_comment_body():
    from src.models.comment_action import CommentAction

    assert "reason" in CommentAction.__table__.columns
    assert "content" not in CommentAction.__table__.columns
