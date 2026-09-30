from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...schemas.article_video import VideoUploadRequest
from ...services.article_video_service import (
    authorize_upload,
    get_video,
    handle_event,
    serialize_video,
)
from ...services.tencent_vod import get_vod_client, verify_callback
from ..deps import get_admin_user, require_permission

router = APIRouter(tags=["article-videos"])


@router.post("/admin/article-videos/uploads", status_code=201)
async def upload_authorization(
    data: VideoUploadRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("articles.write")),
):
    result = await authorize_upload(db, data, int(admin["sub"]))
    await db.commit()  # Persist the context before a cloud callback can arrive.
    return _build_response(0, "success", result)


@router.get("/admin/article-videos/{video_id}")
async def video_status(
    video_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("articles.write")),
    cloud=Depends(get_vod_client),
):
    return _build_response(
        0, "success", serialize_video(await get_video(db, video_id, int(admin["sub"]), cloud=cloud))
    )


@router.post("/integrations/tencent-vod/events")
async def vod_event(
    request: Request, db: AsyncSession = Depends(get_db), cloud=Depends(get_vod_client)
):
    try:
        event = await request.json()
    except ValueError:
        raise BadRequestException(message="点播事件必须为 JSON") from None
    if not isinstance(event, dict):
        raise BadRequestException(message="点播事件格式无效")
    verify_callback(get_settings(), event)
    await handle_event(db, event, cloud=cloud)
    await db.commit()  # Acknowledge only committed state; retries are idempotent.
    return _build_response(0, "success", None)
