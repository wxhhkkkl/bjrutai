"""Retryable in-app notifications for resolved feedback."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import async_session
from ..models.feedback import Feedback
from ..models.notification import Notification, NotificationCategory
from ..models.user import User

logger = logging.getLogger(__name__)
_DELAYS = (60, 5 * 60, 30 * 60, 60 * 60)
_TYPE_LABELS = {"bug": "功能异常", "suggestion": "产品建议", "other": "其他"}


def _next_retry(attempts: int) -> datetime:
    seconds = (
        _DELAYS[min(max(attempts - 1, 0), len(_DELAYS) - 1)]
        if attempts <= len(_DELAYS)
        else 60 * 60
    )
    return datetime.utcnow() + timedelta(seconds=seconds)


async def attempt_feedback_notification(db: AsyncSession, feedback: Feedback) -> bool:
    """Create the single in-app notification, never raising into feedback flow."""
    try:
        if not feedback.user_id:
            raise RuntimeError("submitter is unavailable")
        user = (
            await db.execute(select(User.id).where(User.id == feedback.user_id))
        ).scalar_one_or_none()
        if user is None:
            raise RuntimeError("submitter is unavailable")
        existing = (
            await db.execute(select(Notification.id).where(Notification.feedback_id == feedback.id))
        ).scalar_one_or_none()
        if not existing:
            resolved_at = (
                feedback.resolved_at.strftime("%Y-%m-%d %H:%M") if feedback.resolved_at else ""
            )
            summary = "\n".join(
                filter(
                    None,
                    [
                        f"反馈类型：{_TYPE_LABELS.get(feedback.type, '其他')}",
                        f"处理结果：{feedback.resolution or ''}",
                        f"解决时间：{resolved_at}",
                    ],
                )
            )
            db.add(
                Notification(
                    user_id=feedback.user_id,
                    category=NotificationCategory.SYSTEM,
                    title=f"反馈 {feedback.feedback_no} 已处理",
                    summary=summary,
                    target=None,
                    feedback_id=feedback.id,
                )
            )
            await db.flush()
        feedback.notification_status = "sent"
        feedback.notification_sent_at = datetime.utcnow()
        feedback.notification_next_retry_at = None
        feedback.notification_last_error = None
        feedback.notification_attempts += 1
        return True
    except IntegrityError:
        # A concurrent retry won the unique feedback_id constraint; it is the
        # same logical notification, so converge to sent rather than duplicate.
        feedback.notification_status = "sent"
        feedback.notification_sent_at = datetime.utcnow()
        feedback.notification_next_retry_at = None
        return True
    except Exception as exc:  # noqa: BLE001 - notification must not roll back resolution
        feedback.notification_attempts += 1
        feedback.notification_status = "failed"
        feedback.notification_last_error = str(exc)[:500]
        feedback.notification_next_retry_at = _next_retry(feedback.notification_attempts)
        logger.warning("feedback notification deferred: feedback=%s", feedback.id)
        return False


async def retry_feedback_notifications() -> int:
    now = datetime.utcnow()
    async with async_session() as db:
        rows = (
            (
                await db.execute(
                    select(Feedback)
                    .where(
                        Feedback.status == "resolved",
                        Feedback.notification_status.in_(["pending", "failed"]),
                        or_(
                            Feedback.notification_next_retry_at.is_(None),
                            Feedback.notification_next_retry_at <= now,
                        ),
                    )
                    .order_by(Feedback.notification_next_retry_at, Feedback.id)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for feedback in rows:
            await attempt_feedback_notification(db, feedback)
        await db.commit()
        return len(rows)


async def retry_feedback_notifications_job() -> None:
    try:
        await retry_feedback_notifications()
    except Exception:  # pragma: no cover - scheduler resilience
        logger.exception("feedback notification retry job failed")
