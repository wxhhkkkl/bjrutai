from pathlib import PurePath

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_VIDEO_BYTES = 1_073_741_824


class VideoUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_name: str = Field(alias="fileName", min_length=1, max_length=255)
    content_type: str = Field(alias="contentType", max_length=50)
    size_bytes: int = Field(alias="sizeBytes", gt=0, le=MAX_VIDEO_BYTES, strict=True)

    @model_validator(mode="after")
    def validate_media(self):
        name = self.file_name
        if (
            name != name.strip()
            or any(c in name for c in ("/", "\\", "\x00"))
            or any(ord(c) < 32 for c in name)
        ):
            raise ValueError("视频文件名无效")
        allowed = {".mp4": "video/mp4", ".mov": "video/quicktime"}
        if allowed.get(PurePath(name).suffix.lower()) != self.content_type:
            raise ValueError("仅支持 MP4/MOV 视频，文件类型需与扩展名一致")
        return self
