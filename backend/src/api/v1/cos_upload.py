"""COS image upload endpoint for article editor."""

import httpx
from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from ...api.deps import get_admin_user
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...integrations.cos_client import MAX_FILE_SIZE, get_cos_client

router = APIRouter(prefix="/admin/articles", tags=["cos-upload"])


class ImageUploadRequest(BaseModel):
    fileName: str = Field(..., min_length=1, max_length=255)
    contentType: str = Field(..., min_length=1, max_length=100)


@router.post("/upload-image")
async def upload_article_image(
    body: ImageUploadRequest,
    _current_admin: dict = Depends(get_admin_user),
) -> dict:
    """Generate a pre-signed COS upload URL for an article image."""
    client = get_cos_client()
    try:
        result = client.generate_upload_token(
            user_id=0,  # not tied to a specific user for articles
            file_name=body.fileName,
            content_type=body.contentType,
            file_size=1,  # dummy value; actual size check on client side
            key_prefix="articles/",
        )
    except ValueError as e:
        from ...core.exceptions import BadRequestException
        raise BadRequestException(message=str(e))

    return _build_response(0, "success", {
        "uploadUrl": result["uploadUrl"],
        "fileUrl": result["fileUrl"],
        "expiresAt": result["expiresAt"],
    })


@router.post("/upload-image-file")
async def upload_article_image_file(
    file: UploadFile = File(...),
    _current_admin: dict = Depends(get_admin_user),
) -> dict:
    """Upload an article cover through the API instead of browser-to-COS.

    COS direct uploads require the bucket to allow every admin origin with a
    CORS rule.  Keeping that dependency in the editor means a valid signed
    URL can still fail in the browser.  The API-to-COS request does not have
    that browser restriction and keeps COS credentials on the server.
    """
    content = await file.read()
    if not content:
        raise BadRequestException(message="请选择要上传的图片")
    if len(content) > MAX_FILE_SIZE:
        raise BadRequestException(message="图片大小不能超过 10MB")

    content_type = file.content_type or "application/octet-stream"
    try:
        token = get_cos_client().generate_upload_token(
            user_id=0,
            file_name=file.filename or "article-cover.jpg",
            content_type=content_type,
            file_size=len(content),
            key_prefix="articles/",
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
