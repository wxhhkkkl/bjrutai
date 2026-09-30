"""Claim orphaned application-owned media before deleting anything in VOD."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from ..models.article import Article
from ..models.article_video import ArticleVideo, VideoStatus

logger = logging.getLogger(__name__)


async def cleanup_orphan_videos(session_factory, cloud, *, now: datetime | None = None):
    current = now or datetime.utcnow()
    cutoff = current - timedelta(days=7)
    retry_cutoff = current - timedelta(minutes=15)
    async with session_factory() as db:
        ids = list(
            (
                await db.scalars(
                    select(ArticleVideo.id)
                    .where(
                        ArticleVideo.unbound_at <= cutoff,
                        ArticleVideo.status != VideoStatus.DELETED,
                        ~select(Article.id).where(Article.video_id == ArticleVideo.id).exists(),
                    )
                    .order_by(ArticleVideo.id)
                    .limit(100)
                )
            ).all()
        )
    deleted = 0
    for video_id in ids:
        # Article binding takes the same video-row lock and rejects DELETING.
        # Commit the claim before the slow cloud call, so no DB lock is held then.
        async with session_factory() as db:
            video = await db.scalar(
                select(ArticleVideo).where(ArticleVideo.id == video_id).with_for_update()
            )
            if (
                video is None
                or video.status == VideoStatus.DELETED
                or video.unbound_at is None
                or video.unbound_at > cutoff
                or (video.status == VideoStatus.DELETING and video.updated_at > retry_cutoff)
                or await db.scalar(select(Article.id).where(Article.video_id == video_id))
            ):
                continue
            if not video.file_id:
                video.status = VideoStatus.DELETED
                video.updated_at = current
                await db.commit()
                continue
            if not video.ownership_verified:
                continue
            video.status = VideoStatus.DELETING
            video.updated_at = current
            file_id, sub_app_id = video.file_id, video.vod_sub_app_id
            await db.commit()
        try:
            await cloud.delete_media(file_id, sub_app_id)
        except Exception:
            logger.warning("Article video cloud cleanup deferred: video_id=%s", video_id)
            continue
        async with session_factory() as db:
            video = await db.scalar(
                select(ArticleVideo).where(ArticleVideo.id == video_id).with_for_update()
            )
            if video and video.status == VideoStatus.DELETING:
                video.status = VideoStatus.DELETED
                video.cloud_deleted_at = current
                video.playback_url = None
                video.poster_url = None
                await db.commit()
                deleted += 1
    return deleted


async def article_video_cleanup_job():
    from ..core.config import get_settings
    from ..core.database import async_session
    from .tencent_vod import TencentVod, ensure_configured

    settings = get_settings()
    if not settings.vod_cleanup_enabled:
        return
    try:
        ensure_configured(settings)
        count = await cleanup_orphan_videos(async_session, TencentVod(settings))
        if count:
            logger.info("Article video cloud cleanup completed: count=%s", count)
    except Exception:
        logger.warning("Article video cleanup unavailable; retry on next scheduled run")
