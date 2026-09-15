"""Request schemas for homepage banners."""
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def _image_url(value: str) -> str:
    text = str(value or "").strip()
    if not re.match(r"^https?://", text, re.IGNORECASE):
        raise ValueError("图片地址必须为 HTTP(S) URL")
    return text


class BannerCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=100)
    imageUrl: str = Field(..., min_length=1, max_length=2048)
    actionType: Literal["none", "article"] = "none"
    articleId: Optional[int] = Field(None, ge=1)
    sortOrder: int = Field(0, ge=0, le=9999)

    @field_validator("imageUrl")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        return _image_url(value)

    @model_validator(mode="after")
    def validate_action(self):
        if self.actionType == "article" and self.articleId is None:
            raise ValueError("跳转文章时必须选择文章")
        if self.actionType == "none":
            self.articleId = None
        return self


class BannerUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=100)
    imageUrl: Optional[str] = Field(None, min_length=1, max_length=2048)
    actionType: Optional[Literal["none", "article"]] = None
    articleId: Optional[int] = Field(None, ge=1)
    sortOrder: Optional[int] = Field(None, ge=0, le=9999)
    version: int = Field(..., ge=1)

    @field_validator("imageUrl")
    @classmethod
    def validate_image_url(cls, value: Optional[str]) -> Optional[str]:
        return _image_url(value) if value is not None else value

    @model_validator(mode="after")
    def validate_action(self):
        if self.actionType == "article" and self.articleId is None:
            raise ValueError("跳转文章时必须选择文章")
        return self
