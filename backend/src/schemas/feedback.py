"""Pydantic contracts for feedback APIs."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

FeedbackType = Literal["bug", "suggestion", "other"]
FeedbackStatus = Literal["submitted", "processing", "resolved"]


class FeedbackUploadTokenRequest(BaseModel):
    fileName: str = Field(min_length=1, max_length=255)
    contentType: Literal["image/jpeg", "image/png"]
    fileSize: int = Field(gt=0, le=5 * 1024 * 1024)


class FeedbackCreateRequest(BaseModel):
    type: str
    content: str = Field(min_length=1, max_length=500)
    imageFiles: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        value = value.strip().lower()
        if value == "feature":
            return "suggestion"
        if value not in {"bug", "suggestion", "other"}:
            raise ValueError("type must be bug, suggestion or other")
        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not 10 <= len(value) <= 500:
            raise ValueError("content must contain 10 to 500 characters")
        return value

    @field_validator("imageFiles")
    @classmethod
    def unique_files(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("imageFiles must not contain duplicates")
        return value


class FeedbackAdminUpdateRequest(BaseModel):
    expectedVersion: int = Field(ge=1)
    status: Literal["processing", "resolved"]
    internalNote: str | None = Field(default=None, max_length=1000)
    resolution: str | None = Field(default=None, max_length=500)

    @field_validator("internalNote", "resolution")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value else None
