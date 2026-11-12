"""Server-mediated image uploads shared by admin editors."""

import httpx

from ..integrations.cos_client import MAX_FILE_SIZE, get_cos_client


async def upload_image_via_cos(
    content: bytes,
    *,
    file_name: str,
    content_type: str,
    user_id: int,
    key_prefix: str,
) -> dict:
    if not content:
        raise ValueError("请选择要上传的图片")
    if len(content) > MAX_FILE_SIZE:
        raise ValueError("图片大小不能超过 10MB")

    token = get_cos_client().generate_upload_token(
        user_id=user_id,
        file_name=file_name,
        content_type=content_type,
        file_size=len(content),
        key_prefix=key_prefix,
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.put(
                token["uploadUrl"],
                content=content,
                headers={"Content-Type": content_type},
            )
    except httpx.HTTPError as exc:
        raise ValueError("COS 上传连接失败，请稍后重试") from exc

    if response.status_code >= 300:
        raise ValueError(f"COS 上传失败 (HTTP {response.status_code})")
    return token
