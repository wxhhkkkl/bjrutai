"""COS image upload endpoint for article editor."""

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from ...api.deps import get_admin_user
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...integrations.cos_client import get_cos_client
from ...services.image_upload_service import upload_image_via_cos

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
    try:
        token = await upload_image_via_cos(
            await file.read(),
            file_name=file.filename or "article-cover.jpg",
            content_type=file.content_type or "application/octet-stream",
            user_id=0,
            key_prefix="articles/",
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc)) from exc

    return _build_response(0, "success", {
        "fileUrl": token["fileUrl"],
        "fileName": file.filename,
    })
