"""COS image upload endpoint for article editor."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...api.deps import get_admin_user
from ...integrations.cos_client import get_cos_client

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
    from ...core.error_handler import _build_response

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
