"""Upload authorization, verified media state and transactional article binding."""

import math
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, get_settings
from ..core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ..models.article import Article, ArticleStatus
from ..models.article_video import ArticleVideo, VideoStatus
from ..schemas.article_video import MAX_VIDEO_BYTES, VideoUploadRequest
from .tencent_vod import TencentVod, create_upload_signature, trusted_https_url, unavailable


def serialize_video(video: ArticleVideo | None, *, public: bool = False):
    if video is None or (public and video.status != VideoStatus.READY):
        return None
    if public and not trusted_https_url(video.playback_url, get_settings()):
        return None
    result = {
        "playbackUrl": video.playback_url if video.status == VideoStatus.READY else None,
        "posterUrl": video.poster_url if video.status == VideoStatus.READY else None,
        "durationSeconds": video.duration_seconds,
    }
    if not public:
        messages = {
            VideoStatus.AUTHORIZED: "等待上传完成",
            VideoStatus.PROCESSING: "视频处理中",
            VideoStatus.READY: "视频已就绪",
            VideoStatus.FAILED: video.failure_message or "视频处理失败，请重新上传",
            VideoStatus.DELETING: "视频正在清理",
            VideoStatus.DELETED: "视频已清理",
        }
        result.update(
            videoId=str(video.id),
            fileName=video.file_name,
            status=video.status.value,
            message=messages[video.status],
        )
    return result


async def authorize_upload(db: AsyncSession, data: VideoUploadRequest, admin_id: int):
    session_id = str(uuid.uuid4())
    config = get_settings()
    signature, expires = create_upload_signature(config, session_id)
    video = ArticleVideo(
        upload_session_id=session_id,
        uploaded_by_admin_id=admin_id,
        file_name=data.file_name,
        content_type=data.content_type,
        declared_size_bytes=data.size_bytes,
        vod_sub_app_id=config.vod_sub_app_id,
    )
    db.add(video)
    await db.flush()
    return {
        "videoId": str(video.id),
        "status": "authorized",
        "uploadSignature": signature,
        "expiresAt": expires.isoformat(),
    }


async def get_video(
    db: AsyncSession, video_id: int, admin_id: int, *, cloud: TencentVod | None = None
):
    video = await db.scalar(
        select(ArticleVideo).where(ArticleVideo.id == video_id).with_for_update()
    )
    if video is None:
        raise NotFoundException(message="视频不存在")
    bound = await db.scalar(select(Article.id).where(Article.video_id == video_id))
    if video.uploaded_by_admin_id != admin_id and bound is None:
        raise NotFoundException(message="视频不存在")
    if video.status in (
        VideoStatus.AUTHORIZED,
        VideoStatus.PROCESSING,
    ) and video.updated_at < datetime.utcnow() - timedelta(seconds=60):
        await reconcile_video(db, video, cloud=cloud)
    return video


async def bind_video(
    db: AsyncSession, article: Article, video_id: int | None, admin_id: int | None
):
    if article.video_id == video_id:
        return
    video = None
    if video_id is not None:
        video = await db.scalar(
            select(ArticleVideo).where(ArticleVideo.id == video_id).with_for_update()
        )
        if video is None:
            raise NotFoundException(message="视频不存在")
        if video.uploaded_by_admin_id != admin_id:
            raise ForbiddenException(message="只能绑定自己上传的视频")
        if video.vod_sub_app_id != get_settings().vod_sub_app_id:
            raise ConflictException(message="视频所属点播应用不匹配，请重新上传")
        if video.status in (VideoStatus.FAILED, VideoStatus.DELETING, VideoStatus.DELETED):
            raise ConflictException(message="视频不可用，请重新上传")
        # The locked row carries the current binding state even when another
        # non-locking read in this MySQL transaction used an older snapshot.
        if video.unbound_at is None:
            raise ConflictException(message="视频已被另一篇文章使用")
        if article.status == ArticleStatus.PUBLISHED and video.status != VideoStatus.READY:
            raise ConflictException(message="新视频尚未就绪，请等待处理完成后保存")
        if await db.scalar(
            select(Article.id).where(Article.video_id == video_id, Article.id != article.id)
        ):
            raise ConflictException(message="视频已被另一篇文章使用")
    if article.video_id is not None:
        previous = await db.scalar(
            select(ArticleVideo).where(ArticleVideo.id == article.video_id).with_for_update()
        )
        previous.unbound_at = datetime.utcnow()
    if video:
        video.unbound_at = None
    article.video = video
    article.video_id = video_id


def fail(video: ArticleVideo, message: str):
    video.status = VideoStatus.FAILED
    video.failure_message = message
    video.playback_url = None
    video.poster_url = None


def confirm_playback(video: ArticleVideo, metadata: dict, config: Settings):
    details = metadata.get("MetaData") or {}
    size = details.get("Size")
    if size is None and not video.processing_confirmed_at:
        video.status = VideoStatus.PROCESSING
        return
    if size is None:
        raise unavailable()
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_VIDEO_BYTES:
        fail(video, "视频实际大小不符合要求（最大 1 GB）")
        return
    video.actual_size_bytes = size
    if not video.upload_confirmed_at or not video.processing_confirmed_at:
        video.status = VideoStatus.PROCESSING
        return
    outputs = (metadata.get("TranscodeInfo") or {}).get("TranscodeSet") or []
    if not outputs:
        raise unavailable()
    for output in outputs:
        url = trusted_https_url(output.get("Url"), config)
        streams = output.get("VideoStreamSet") or []
        audio = output.get("AudioStreamSet") or []
        if (
            not url
            or not urlsplit(url).path.lower().endswith(".mp4")
            or not output.get("Definition")
            or not streams
            or any(str(s.get("Codec", "")).lower() not in ("h264", "avc") for s in streams)
            or any(str(s.get("Codec", "")).lower() != "aac" for s in audio)
        ):
            continue
        video.status = VideoStatus.READY
        video.playback_url = url
        video.poster_url = trusted_https_url(
            (metadata.get("BasicInfo") or {}).get("CoverUrl"), config
        )
        duration = output.get("Duration", details.get("Duration"))
        video.duration_seconds = (
            float(duration)
            if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0
            else None
        )
        video.failure_message = None
        return
    fail(video, "未生成可播放的 HTTPS MP4 视频，请检查点播任务流与播放域名")


async def handle_event(
    db: AsyncSession,
    event: dict,
    *,
    config: Settings | None = None,
    cloud: TencentVod | None = None,
):
    config = config or get_settings()
    cloud = cloud or TencentVod(config)
    kind = event.get("EventType")
    if kind not in ("NewFileUpload", "ProcedureStateChanged"):
        return
    payload = event.get(
        "FileUploadEvent" if kind == "NewFileUpload" else "ProcedureStateChangeEvent"
    )
    if not isinstance(payload, dict):
        raise BadRequestException(message="点播事件格式无效")
    if kind == "NewFileUpload":
        basic_info = payload.get("MediaBasicInfo") or {}
        source_info = basic_info.get("SourceInfo") if isinstance(basic_info, dict) else None
        context = source_info.get("SourceContext") if isinstance(source_info, dict) else None
    else:
        context = payload.get("SessionContext")
    file_id = payload.get("FileId")
    if (
        not isinstance(context, str)
        or not isinstance(file_id, str)
        or not file_id
        or len(file_id) > 100
    ):
        raise BadRequestException(message="点播事件缺少上传会话或文件标识")
    video = await db.scalar(
        select(ArticleVideo).where(ArticleVideo.upload_session_id == context).with_for_update()
    )
    if video is None or video.status in (
        VideoStatus.READY,
        VideoStatus.FAILED,
        VideoStatus.DELETING,
        VideoStatus.DELETED,
    ):
        return
    if video.vod_sub_app_id != config.vod_sub_app_id or (
        video.file_id and video.file_id != file_id
    ):
        raise BadRequestException(message="点播事件与上传会话不一致")
    if await db.scalar(
        select(ArticleVideo.id).where(ArticleVideo.file_id == file_id, ArticleVideo.id != video.id)
    ):
        raise ConflictException(message="点播文件已被使用")
    # Sign/T authenticate the notification. Cloud metadata independently proves the
    # file belongs to this application's random upload context and configured app.
    metadata = await cloud.describe_media(file_id, video.vod_sub_app_id)
    if not metadata:
        raise unavailable()
    if (
        metadata.get("FileId") != file_id
        or ((metadata.get("BasicInfo") or {}).get("SourceInfo") or {}).get("SourceContext")
        != context
    ):
        fail(video, "点播媒资来源校验失败")
        await db.flush()
        return
    video.file_id = file_id
    video.ownership_verified = True
    if kind == "NewFileUpload":
        task_id = payload.get("ProcedureTaskId")
        if not isinstance(task_id, str) or not task_id or len(task_id) > 255:
            fail(video, "上传未触发转码任务，请检查点播任务流")
            await db.flush()
            return
        if video.procedure_task_id and video.procedure_task_id != task_id:
            raise BadRequestException(message="点播任务与上传会话不一致")
        video.procedure_task_id = task_id
        video.upload_confirmed_at = video.upload_confirmed_at or datetime.utcnow()
    else:
        task_id = payload.get("TaskId")
        if not isinstance(task_id, str) or len(task_id) > 255:
            raise BadRequestException(message="点播任务标识无效")
        if video.procedure_task_id and video.procedure_task_id != task_id:
            raise BadRequestException(message="点播任务与上传会话不一致")
        video.procedure_task_id = task_id
        task = await cloud.describe_task(task_id, video.vod_sub_app_id)
        if not isinstance(task, dict):
            raise unavailable()
        if (
            task.get("FileId") != file_id
            or task.get("SessionContext") != context
            or task.get("TaskId") != task_id
        ):
            raise BadRequestException(message="点播任务与上传会话不一致")
        if task.get("Status") != "FINISH":
            video.status = VideoStatus.PROCESSING
            await db.flush()
            return
        transcodes = [
            item.get("TranscodeTask") or {}
            for item in (task.get("MediaProcessResultSet") or [])
            if item.get("Type") == "Transcode"
        ]
        if not transcodes or any(
            task.get("Status") != "SUCCESS" or task.get("ErrCode", 0) != 0 for task in transcodes
        ):
            fail(video, "视频转码失败，请重新上传或联系管理员")
            await db.flush()
            return
        video.processing_confirmed_at = video.processing_confirmed_at or datetime.utcnow()
    confirm_playback(video, metadata, config)
    await db.flush()


async def reconcile_video(db: AsyncSession, video: ArticleVideo, *, config=None, cloud=None):
    """Recover missed notifications using independently verified cloud state."""
    config = config or get_settings()
    cloud = cloud or TencentVod(config)
    if not video.file_id or not video.ownership_verified or not video.procedure_task_id:
        if video.created_at < datetime.utcnow() - timedelta(days=1):
            fail(video, "上传确认超时，请重新上传")
        video.updated_at = datetime.utcnow()
        await db.flush()
        return
    metadata = await cloud.describe_media(video.file_id, video.vod_sub_app_id)
    if not metadata:
        raise unavailable()
    context = ((metadata.get("BasicInfo") or {}).get("SourceInfo") or {}).get("SourceContext")
    if metadata.get("FileId") != video.file_id or context != video.upload_session_id:
        raise BadRequestException(message="点播媒资来源校验失败")
    video.upload_confirmed_at = video.upload_confirmed_at or datetime.utcnow()
    await handle_event(
        db,
        {
            "EventType": "ProcedureStateChanged",
            "ProcedureStateChangeEvent": {
                "FileId": video.file_id,
                "TaskId": video.procedure_task_id,
                "SessionContext": video.upload_session_id,
            },
        },
        config=config,
        cloud=cloud,
    )
    video.updated_at = datetime.utcnow()
    await db.flush()
