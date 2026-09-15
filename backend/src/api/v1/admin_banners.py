"""Administrator endpoints for homepage banner management."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user
from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...integrations.cos_client import get_cos_client
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
