"""Administrator endpoints for homepage banner management."""
import httpx

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user
from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...integrations.cos_client import MAX_FILE_SIZE, get_cos_client
from ...models.banner import BannerStatus
from ...schemas.banner import BannerCreate, BannerUpdate
from ...services.banner_service import (
    create_banner,
    delete_banner,
    list_admin,
    set_status,
    update_banner,
)

router = APIRouter(prefix="/admin/banners", tags=["admin-banners"])


class ImageUploadRequest(BaseModel):
    fileName: str = Field(..., min_length=1, max_length=255)
    contentType: str = Field(..., pattern=r"^image/(jpeg|png|gif|webp)$")


@router.get("")
async def admin_list_banners(
    status: str | None = Query(None, pattern="^(enabled|disabled)$"),
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    return _build_response(0, "success", {"items": await list_admin(db, status)})


@router.post("")
async def admin_create_banner(
    data: BannerCreate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    banner = await create_banner(db, data)
    return _build_response(0, "success", {"bannerId": str(banner.id), "status": banner.status.value})


@router.put("/{banner_id}")
async def admin_update_banner(
    banner_id: int,
    data: BannerUpdate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    banner = await update_banner(db, banner_id, data)
    return _build_response(0, "success", {"bannerId": str(banner.id), "version": banner.version})


@router.post("/{banner_id}/enable")
async def admin_enable_banner(
    banner_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    banner = await set_status(db, banner_id, BannerStatus.ENABLED)
    return _build_response(0, "success", {"bannerId": str(banner.id), "status": banner.status.value})


@router.post("/{banner_id}/disable")
async def admin_disable_banner(
    banner_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    banner = await set_status(db, banner_id, BannerStatus.DISABLED)
    return _build_response(0, "success", {"bannerId": str(banner.id), "status": banner.status.value})


@router.delete("/{banner_id}")
async def admin_delete_banner(
    banner_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    await delete_banner(db, banner_id)
    return _build_response(0, "success", {"bannerId": str(banner_id)})


@router.post("/upload-image")
async def upload_banner_image(
    body: ImageUploadRequest,
    _current_admin: dict = Depends(get_admin_user),
):
    try:
        result = get_cos_client().generate_upload_token(
            user_id=0,
            file_name=body.fileName,
            content_type=body.contentType,
            file_size=1,
            key_prefix="banners/",
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc)) from exc
    return _build_response(0, "success", {
        "uploadUrl": result["uploadUrl"],
        "fileUrl": result["fileUrl"],
        "expiresAt": result["expiresAt"],
    })


@router.post("/upload-image-file")
async def upload_banner_image_file(
    file: UploadFile = File(...),
    _current_admin: dict = Depends(get_admin_user),
):
    """Upload a banner image through the API to avoid browser-to-COS CORS."""
    content = await file.read()
    if not content:
        raise BadRequestException(message="请选择要上传的图片")
    if len(content) > MAX_FILE_SIZE:
        raise BadRequestException(message="图片大小不能超过 10MB")

    content_type = file.content_type or "application/octet-stream"
    try:
        token = get_cos_client().generate_upload_token(
            user_id=0,
            file_name=file.filename or "homepage-banner.jpg",
            content_type=content_type,
            file_size=len(content),
            key_prefix="banners/",
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc)) from exc

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.put(
                token["uploadUrl"],
                content=content,
                headers={"Content-Type": content_type},
            )
    except httpx.HTTPError as exc:
        raise BadRequestException(message="COS 上传连接失败，请稍后重试") from exc

    if response.status_code >= 300:
        raise BadRequestException(message=f"COS 上传失败 (HTTP {response.status_code})")

    return _build_response(0, "success", {
        "fileUrl": token["fileUrl"],
        "fileName": file.filename,
    })
