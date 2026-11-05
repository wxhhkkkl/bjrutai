"""Administrator endpoints for Mini Program share cards."""

import httpx

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import require_permission
from ...core.database import get_db
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...integrations.cos_client import MAX_FILE_SIZE, get_cos_client
from ...services.share_config_service import (
    SHARE_SOURCE_ROUTES,
    create_share_config,
    delete_share_config,
    list_share_configs,
    page_key_for_route,
    update_share_config,
)

router = APIRouter(prefix="/admin/share-configs", tags=["admin-share-configs"])


class ShareConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    friend_title: str = Field(..., alias="friendTitle", min_length=1, max_length=100)
    friend_image_url: str = Field(..., alias="friendImageUrl", min_length=1, max_length=2048)
    landing_path: str = Field(..., alias="landingPath", min_length=1, max_length=512)
    timeline_title: str | None = Field(None, alias="timelineTitle", max_length=100)
    timeline_image_url: str | None = Field(None, alias="timelineImageUrl", max_length=2048)
    version: int = Field(..., ge=1)


class ShareConfigCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    page_key: str = Field(..., alias="pageKey", min_length=1, max_length=40)
    friend_title: str = Field(..., alias="friendTitle", min_length=1, max_length=100)
    friend_image_url: str = Field(..., alias="friendImageUrl", min_length=1, max_length=2048)
    landing_path: str = Field("/pages/home/index", alias="landingPath", min_length=1, max_length=512)
    timeline_title: str | None = Field(None, alias="timelineTitle", max_length=100)
    timeline_image_url: str | None = Field(None, alias="timelineImageUrl", max_length=2048)


@router.get("")
async def admin_list_share_configs(
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_permission("mini_program_shares.read")),
):
    items = await list_share_configs(db)
    configured_keys = {item["pageKey"] for item in items}
    return _build_response(0, "success", {
        "items": items,
        "sources": [
            {"pageKey": page_key_for_route(path), "pageName": name, "sourcePath": path}
            for path, name in SHARE_SOURCE_ROUTES
            if page_key_for_route(path) not in configured_keys
        ],
    })


@router.post("")
async def admin_create_share_config(
    data: ShareConfigCreate,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_permission("mini_program_shares.write")),
):
    item = await create_share_config(db, data.model_dump(by_alias=False))
    return _build_response(0, "success", {"item": item})


@router.put("/{page_key}")
async def admin_update_share_config(
    page_key: str,
    data: ShareConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_permission("mini_program_shares.write")),
):
    item = await update_share_config(db, page_key, data.model_dump(by_alias=False))
    return _build_response(0, "success", {"item": item})


@router.delete("/{page_key}")
async def admin_delete_share_config(
    page_key: str,
    version: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_permission("mini_program_shares.write")),
):
    item = await delete_share_config(db, page_key, version)
    return _build_response(0, "success", item)


@router.post("/upload-image-file")
async def upload_share_image(
    file: UploadFile = File(...),
    _admin: dict = Depends(require_permission("mini_program_shares.write")),
):
    content = await file.read()
    if not content:
        raise BadRequestException(message="请选择要上传的图片")
    if len(content) > MAX_FILE_SIZE:
        raise BadRequestException(message="图片大小不能超过 10MB")

    content_type = file.content_type or "application/octet-stream"
    try:
        token = get_cos_client().generate_upload_token(
            user_id=0,
            file_name=file.filename or "mini-program-share.jpg",
            content_type=content_type,
            file_size=len(content),
            key_prefix="shares/",
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc)) from exc

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.put(
                token["uploadUrl"], content=content, headers={"Content-Type": content_type}
            )
    except httpx.HTTPError as exc:
        raise BadRequestException(message="COS 上传连接失败，请稍后重试") from exc
    if response.status_code >= 300:
        raise BadRequestException(message=f"COS 上传失败 (HTTP {response.status_code})")
    return _build_response(0, "success", {"fileUrl": token["fileUrl"], "fileName": file.filename})
