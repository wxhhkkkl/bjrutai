"""Shared article-comment domain operations.

The public/admin request handlers are added in the user-story phases.  The
retention operation lives here so both the scheduled job and integration tests
use the same transactional behavior.
"""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from ..models.article import Article, ArticleStatus
from ..models.article_comment import ArticleComment
from ..models.audit import AuditLog
from ..models.comment_action import CommentAction
from ..models.comment_like import CommentLike
from ..models.user import ActivationStatus, AdminAccount, User
from .comment_moderation import moderate_content, validate_comment_text


def _encode_cursor(comment: ArticleComment) -> str:
    payload = {
        "pinned": 1 if comment.is_pinned else 0,
        "createdAt": comment.created_at.isoformat(),
        "id": comment.id,
    }
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(cursor + padding).decode())
        return {
            "pinned": int(value["pinned"]),
            "createdAt": datetime.fromisoformat(value["createdAt"]),
            "id": int(value["id"]),
        }
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise BadRequestException(message="评论分页游标无效")


async def _get_published_article(db: AsyncSession, article_id: int) -> Article:
    article = (
        await db.execute(select(Article).where(Article.id == article_id))
    ).scalar_one_or_none()
    if article is None or article.status != ArticleStatus.PUBLISHED:
        raise NotFoundException(message="Article not found")
    return article


async def _get_active_user(db: AsyncSession, user_id: int) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise NotFoundException(message="User not found")
    if user.activation_status != ActivationStatus.ACTIVE:
        raise ForbiddenException(message="当前账号不可发表评论")
    return user


async def create_comment(
    db: AsyncSession,
    *,
    article_id: int,
    user_id: int,
    content: str,
    idempotency_key: str,
    now: datetime | None = None,
) -> ArticleComment:
    """Create or replay one comment submission."""

    if not idempotency_key or len(idempotency_key) > 128:
        raise BadRequestException(message="缺少有效的 Idempotency-Key")
    article = await _get_published_article(db, article_id)
    user = await _get_active_user(db, user_id)
    clean_content = validate_comment_text(content)
    current_time = now or datetime.now(timezone.utc)
    fingerprint = hashlib.sha256(clean_content.encode("utf-8")).hexdigest()

    existing = (
        await db.execute(
            select(ArticleComment).where(
                ArticleComment.user_id == user_id,
                ArticleComment.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.submission_fingerprint != fingerprint or existing.article_id != article_id:
            raise ConflictException(
                code=40911,
                message="Idempotency-Key 已用于其他评论",
            )
        return existing

    window_start = current_time - timedelta(minutes=1)
    recent_count = (
        await db.execute(
            select(func.count(ArticleComment.id)).where(
                ArticleComment.user_id == user_id,
                ArticleComment.created_at >= window_start,
                ArticleComment.created_at <= current_time,
                ArticleComment.status != "deleted",
            )
        )
    ).scalar_one()
    if recent_count >= 3:
        raise BadRequestException(message="每分钟最多提交 3 条评论")

    moderation = moderate_content(clean_content)
    comment = ArticleComment(
        article_id=article.id,
        user_id=user.id,
        display_name_snapshot=(user.name or "儒泰用户").strip() or "儒泰用户",
        avatar_url_snapshot=user.avatar_url,
        content=clean_content,
        status="visible" if moderation.status == "passed" else "pending",
        moderation_status=moderation.status,
        moderation_category=moderation.category,
        moderation_rule_version=moderation.rule_version,
        moderation_checked_at=current_time,
        moderation_reason=moderation.reason,
        is_pinned=False,
        like_count=0,
        version=1,
        idempotency_key=idempotency_key,
        submission_fingerprint=fingerprint,
        created_at=current_time,
        updated_at=current_time,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)
    return comment


async def list_visible_comments(
    db: AsyncSession,
    *,
    article_id: int,
    user_id: int,
    cursor: str | None = None,
    limit: int = 20,
) -> dict:
    """List only visible comments with a stable opaque cursor."""

    await _get_published_article(db, article_id)
    limit = max(1, min(limit, 50))
    decoded = _decode_cursor(cursor)
    stmt = (
        select(ArticleComment, CommentLike.id)
        .outerjoin(
            CommentLike,
            and_(CommentLike.comment_id == ArticleComment.id, CommentLike.user_id == user_id),
        )
        .where(
            ArticleComment.article_id == article_id,
            ArticleComment.status == "visible",
        )
    )
    if decoded:
        cursor_created = decoded["createdAt"]
        cursor_pinned = decoded["pinned"]
        cursor_id = decoded["id"]
        stmt = stmt.where(
            or_(
                (ArticleComment.is_pinned.cast(Integer) < cursor_pinned),
                and_(
                    ArticleComment.is_pinned.cast(Integer) == cursor_pinned,
                    ArticleComment.created_at < cursor_created,
                ),
                and_(
                    ArticleComment.is_pinned.cast(Integer) == cursor_pinned,
                    ArticleComment.created_at == cursor_created,
                    ArticleComment.id < cursor_id,
                ),
            )
        )
    stmt = stmt.order_by(
        ArticleComment.is_pinned.desc(),
        ArticleComment.created_at.desc(),
        ArticleComment.id.desc(),
    ).limit(limit + 1)
    rows = list((await db.execute(stmt)).all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    items = [
        {
            "commentId": str(comment.id),
            "displayName": comment.display_name_snapshot,
            "avatarUrl": comment.avatar_url_snapshot,
            "content": comment.content or "",
            "isPinned": bool(comment.is_pinned),
            "likeCount": max(0, comment.like_count),
            "liked": like_id is not None,
            "createdAt": comment.created_at.isoformat(),
        }
        for comment, like_id in rows
    ]
    total = (
        await db.execute(
            select(func.count(ArticleComment.id)).where(
                ArticleComment.article_id == article_id,
                ArticleComment.status == "visible",
            )
        )
    ).scalar_one()
    return {
        "items": items,
        "nextCursor": _encode_cursor(rows[-1][0]) if has_more and rows else None,
        "hasMore": has_more,
        "total": total,
    }


async def _get_visible_comment(
    db: AsyncSession, *, article_id: int, comment_id: int
) -> ArticleComment:
    await _get_published_article(db, article_id)
    comment = (
        await db.execute(
            select(ArticleComment).where(
                ArticleComment.id == comment_id,
                ArticleComment.article_id == article_id,
                ArticleComment.status == "visible",
            )
        )
    ).scalar_one_or_none()
    if comment is None:
        raise NotFoundException(message="Comment not found")
    return comment


async def like_comment(
    db: AsyncSession, *, article_id: int, comment_id: int, user_id: int
) -> dict:
    """Create one like relation and return the server-authoritative count."""

    await _get_active_user(db, user_id)
    comment = await _get_visible_comment(db, article_id=article_id, comment_id=comment_id)
    existing = (
        await db.execute(
            select(CommentLike).where(
                CommentLike.comment_id == comment.id,
                CommentLike.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(CommentLike(comment_id=comment.id, user_id=user_id))
        comment.like_count = max(0, comment.like_count) + 1
        comment.updated_at = datetime.now(timezone.utc)
        await db.flush()
    return {
        "commentId": str(comment.id),
        "liked": True,
        "likeCount": max(0, comment.like_count),
    }


async def unlike_comment(
    db: AsyncSession, *, article_id: int, comment_id: int, user_id: int
) -> dict:
    """Remove one like relation and keep the aggregate count non-negative."""

    await _get_active_user(db, user_id)
    comment = await _get_visible_comment(db, article_id=article_id, comment_id=comment_id)
    existing = (
        await db.execute(
            select(CommentLike).where(
                CommentLike.comment_id == comment.id,
                CommentLike.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        comment.like_count = max(0, comment.like_count - 1)
        comment.updated_at = datetime.now(timezone.utc)
        await db.flush()
    return {
        "commentId": str(comment.id),
        "liked": False,
        "likeCount": max(0, comment.like_count),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _admin_preview(comment: ArticleComment) -> str:
    return (comment.content or "内容已清理")[:100]


async def list_admin_comments(
    db: AsyncSession,
    *,
    article_id: int | None = None,
    status: str | None = None,
    keyword: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict:
    """List comments for the management console using the same stable cursor."""

    if status and status not in {"pending", "visible", "hidden", "rejected", "deleted"}:
        raise BadRequestException(message="评论状态无效")
    if created_from and created_to and created_to < created_from:
        raise BadRequestException(message="结束时间不得早于开始时间")
    limit = max(1, min(limit, 100))
    stmt = select(ArticleComment, Article.title).join(Article, Article.id == ArticleComment.article_id)
    if article_id is not None:
        stmt = stmt.where(ArticleComment.article_id == article_id)
    if status:
        stmt = stmt.where(ArticleComment.status == status)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(ArticleComment.content.ilike(pattern), ArticleComment.display_name_snapshot.ilike(pattern))
        )
    if created_from:
        stmt = stmt.where(ArticleComment.created_at >= created_from)
    if created_to:
        stmt = stmt.where(ArticleComment.created_at <= created_to)
    decoded = _decode_cursor(cursor)
    if decoded:
        cursor_created = decoded["createdAt"]
        cursor_pinned = decoded["pinned"]
        cursor_id = decoded["id"]
        stmt = stmt.where(
            or_(
                ArticleComment.is_pinned.cast(Integer) < cursor_pinned,
                and_(
                    ArticleComment.is_pinned.cast(Integer) == cursor_pinned,
                    ArticleComment.created_at < cursor_created,
                ),
                and_(
                    ArticleComment.is_pinned.cast(Integer) == cursor_pinned,
                    ArticleComment.created_at == cursor_created,
                    ArticleComment.id < cursor_id,
                ),
            )
        )
    rows = list(
        (
            await db.execute(
                stmt.order_by(
                    ArticleComment.is_pinned.desc(),
                    ArticleComment.created_at.desc(),
                    ArticleComment.id.desc(),
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    count_stmt = select(func.count(ArticleComment.id)).select_from(ArticleComment)
    if article_id is not None:
        count_stmt = count_stmt.where(ArticleComment.article_id == article_id)
    if status:
        count_stmt = count_stmt.where(ArticleComment.status == status)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        count_stmt = count_stmt.where(
            or_(ArticleComment.content.ilike(pattern), ArticleComment.display_name_snapshot.ilike(pattern))
        )
    if created_from:
        count_stmt = count_stmt.where(ArticleComment.created_at >= created_from)
    if created_to:
        count_stmt = count_stmt.where(ArticleComment.created_at <= created_to)
    total = (await db.execute(count_stmt)).scalar_one()
    return {
        "items": [
            {
                "commentId": str(comment.id),
                "articleId": str(comment.article_id),
                "articleTitle": title,
                "displayName": comment.display_name_snapshot,
                "contentPreview": _admin_preview(comment),
                "status": comment.status,
                "moderationStatus": comment.moderation_status,
                "moderationCategory": comment.moderation_category,
                "isPinned": bool(comment.is_pinned),
                "likeCount": max(0, comment.like_count),
                "createdAt": _iso(comment.created_at),
                "updatedAt": _iso(comment.updated_at),
                "version": comment.version,
            }
            for comment, title in rows
        ],
        "nextCursor": _encode_cursor(rows[-1][0]) if has_more and rows else None,
        "hasMore": has_more,
        "total": int(total or 0),
    }


async def _get_admin_comment(db: AsyncSession, comment_id: int) -> ArticleComment:
    comment = (
        await db.execute(select(ArticleComment).where(ArticleComment.id == comment_id))
    ).scalar_one_or_none()
    if comment is None:
        raise NotFoundException(message="评论不存在")
    return comment


async def get_admin_comment_detail(db: AsyncSession, *, comment_id: int) -> dict:
    comment = await _get_admin_comment(db, comment_id)
    article = (
        await db.execute(select(Article).where(Article.id == comment.article_id))
    ).scalar_one_or_none()
    actions = (
        await db.execute(
            select(CommentAction)
            .where(CommentAction.comment_id == comment.id)
            .order_by(CommentAction.created_at, CommentAction.id)
        )
    ).scalars().all()
    return {
        "commentId": str(comment.id),
        "articleId": str(comment.article_id),
        "articleTitle": article.title if article else "",
        "displayName": comment.display_name_snapshot,
        "avatarUrl": comment.avatar_url_snapshot,
        "content": comment.content if comment.content is not None else "内容已清理",
        "status": comment.status,
        "moderationStatus": comment.moderation_status,
        "moderationCategory": comment.moderation_category,
        "moderationRuleVersion": comment.moderation_rule_version,
        "moderationCheckedAt": _iso(comment.moderation_checked_at),
        "moderationReason": comment.moderation_reason,
        "isPinned": bool(comment.is_pinned),
        "likeCount": max(0, comment.like_count),
        "version": comment.version,
        "createdAt": _iso(comment.created_at),
        "updatedAt": _iso(comment.updated_at),
        "actions": [
            {
                "actionId": str(action.id),
                "actionType": action.action_type,
                "operatorName": action.operator_name_snapshot,
                "fromStatus": action.from_status,
                "toStatus": action.to_status,
                "reason": action.reason,
                "createdAt": _iso(action.created_at),
            }
            for action in actions
        ],
    }


async def update_admin_comment(
    db: AsyncSession,
    *,
    comment_id: int,
    action: str,
    expected_version: int,
    admin_id: int,
    reason: str | None = None,
) -> dict:
    """Apply one auditable state action using optimistic locking."""

    comment = await _get_admin_comment(db, comment_id)
    if comment.version != expected_version:
        raise ConflictException(
            code=40910,
            message="评论已被其他管理员更新，请刷新后重试",
            detail={"currentVersion": comment.version},
        )
    if action in {"reject", "hide", "delete"} and not (reason or "").strip():
        raise BadRequestException(message="该操作必须填写原因")
    if comment.status == "deleted" and action != "delete":
        raise BadRequestException(message="已删除评论不能恢复或再次处置")

    admin = (
        await db.execute(select(AdminAccount).where(AdminAccount.id == admin_id))
    ).scalar_one_or_none()
    operator_name = admin.username if admin else "管理员"
    previous = comment.status
    now = datetime.now(timezone.utc)

    if action == "approve":
        if previous not in {"pending", "rejected", "hidden"}:
            raise BadRequestException(message="当前状态不能审核通过")
        comment.status = "visible"
        comment.moderation_status = "passed"
        comment.hidden_at = None
    elif action == "reject":
        if previous != "pending":
            raise BadRequestException(message="只有待审核评论可以拒绝")
        comment.status = "rejected"
        comment.moderation_status = "rejected"
    elif action == "hide":
        if previous != "visible":
            raise BadRequestException(message="只有已发布评论可以下架")
        comment.status = "hidden"
        comment.hidden_at = now
    elif action == "restore":
        if previous != "hidden":
            raise BadRequestException(message="只有已下架评论可以恢复")
        comment.status = "visible"
        comment.hidden_at = None
    elif action == "pin":
        if previous != "visible":
            raise BadRequestException(message="只有已发布评论可以置顶")
        old_pinned = (
            await db.execute(
                select(ArticleComment).where(
                    ArticleComment.article_id == comment.article_id,
                    ArticleComment.is_pinned.is_(True),
                    ArticleComment.id != comment.id,
                )
            )
        ).scalars().all()
        for old in old_pinned:
            old.is_pinned = False
            old.version += 1
            old.updated_at = now
            db.add(
                CommentAction(
                    comment_id=old.id,
                    operator_admin_id=admin_id,
                    operator_name_snapshot=operator_name,
                    action_type="unpin",
                    from_status=old.status,
                    to_status=old.status,
                    reason="同文章置顶替换",
                    version_before=old.version - 1,
                    version_after=old.version,
                    created_at=now,
                )
            )
        comment.is_pinned = True
    elif action == "unpin":
        comment.is_pinned = False
    elif action == "delete":
        if previous == "deleted":
            return await get_admin_comment_detail(db, comment_id=comment.id)
        comment.status = "deleted"
        comment.deleted_at = now
        comment.hidden_at = None
        comment.is_pinned = False
        comment.like_count = 0
        await db.execute(delete(CommentLike).where(CommentLike.comment_id == comment.id))
    else:
        raise BadRequestException(message="不支持的评论操作")

    comment.version += 1
    comment.updated_at = now
    if action in {"reject", "hide", "delete"}:
        comment.is_pinned = False
    db.add(
        CommentAction(
            comment_id=comment.id,
            operator_admin_id=admin_id,
            operator_name_snapshot=operator_name,
            action_type=action,
            from_status=previous,
            to_status=comment.status,
            reason=(reason or "").strip() or None,
            moderation_rule_version=comment.moderation_rule_version,
            version_before=comment.version - 1,
            version_after=comment.version,
            created_at=now,
        )
    )
    db.add(
        AuditLog(
            user_id=None,
            action=f"comment_{action}",
            entity_type="article_comment",
            entity_id=str(comment.id),
            detail={
                "commentId": comment.id,
                "articleId": comment.article_id,
                "adminAccountId": admin_id,
                "action": action,
                "fromStatus": previous,
                "toStatus": comment.status,
                "version": comment.version,
                "reasonLength": len((reason or "").strip()),
            },
        )
    )
    await db.flush()
    return await get_admin_comment_detail(db, comment_id=comment.id)


async def purge_expired_deleted_comments(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = 500,
) -> int:
    """Clear business comment data after the seven-day deletion window.

    Security ``AuditLog`` rows are intentionally not touched here.  The
    function only clears body/moderation/idempotency data and deletes the
    queryable business action/like rows for already-soft-deleted comments.
    """

    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=7)
    result = await db.execute(
        select(ArticleComment.id)
        .where(
            ArticleComment.status == "deleted",
            ArticleComment.deleted_at.is_not(None),
            ArticleComment.deleted_at <= cutoff,
        )
        .order_by(ArticleComment.id)
        .limit(batch_size)
    )
    comment_ids = [row[0] for row in result.all()]
    if not comment_ids:
        return 0

    await db.execute(delete(CommentLike).where(CommentLike.comment_id.in_(comment_ids)))
    await db.execute(CommentAction.__table__.delete().where(CommentAction.comment_id.in_(comment_ids)))
    update_result = await db.execute(
        update(ArticleComment)
        .where(ArticleComment.id.in_(comment_ids))
        .values(
            content=None,
            moderation_status="pending",
            moderation_category=None,
            moderation_rule_version=None,
            moderation_checked_at=None,
            moderation_reason=None,
            idempotency_key=None,
            submission_fingerprint=None,
            like_count=0,
            updated_at=current_time,
        )
    )
    await db.flush()
    return int(update_result.rowcount or 0)
