"""Pydantic schemas for qualification upload and review endpoints (US2)."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Upload Token
# ──────────────────────────────────────────────
class UploadTokenRequest(BaseModel):
    fileName: str = Field(..., min_length=1, max_length=255, description="Original file name")
    fileType: str = Field(..., min_length=1, max_length=255, description="MIME content type")
    fileSize: int = Field(..., gt=0, description="File size in bytes (max 10MB)")


class UploadTokenResponse(BaseModel):
    fileId: str
    uploadUrl: str
    expiresAt: str
    contentType: str


# ──────────────────────────────────────────────
# Qualification CRUD
# ──────────────────────────────────────────────
class QualificationCreate(BaseModel):
    qualificationType: str = Field(..., description="Qualification type: individual, enterprise")
    fileId: str = Field(..., min_length=1, max_length=512, description="COS file key")
    fileName: str = Field(..., min_length=1, max_length=255, description="Original file name")
    fileType: str = Field(..., min_length=1, max_length=50, description="MIME type of the file")
    fileSize: int = Field(..., gt=0, description="File size in bytes")


class QualificationUpdate(BaseModel):
    fileId: Optional[str] = Field(None, min_length=1, max_length=512)
    fileName: Optional[str] = Field(None, min_length=1, max_length=255)
    fileType: Optional[str] = Field(None, min_length=1, max_length=50)
    fileSize: Optional[int] = Field(None, gt=0)
    version: int = Field(..., ge=1, description="Current version for optimistic locking")


class DraftRequest(BaseModel):
    qualificationType: str = Field(..., description="Qualification type: individual, enterprise")
    fileId: Optional[str] = Field(None, min_length=1, max_length=512)
    fileName: Optional[str] = Field(None, min_length=1, max_length=255)
    fileType: Optional[str] = Field(None, min_length=1, max_length=50)
    fileSize: Optional[int] = Field(None, gt=0)


# ──────────────────────────────────────────────
# Responses
# ──────────────────────────────────────────────
class QualificationItem(BaseModel):
    qualificationId: str
    qualificationType: str
    status: str
    statusLabel: str
    fileName: Optional[str] = None
    fileType: Optional[str] = None
    fileSize: Optional[int] = None
    fileId: Optional[str] = None
    version: int
    rejectedReason: Optional[str] = None
    submittedAt: Optional[str] = None
    approvedAt: Optional[str] = None
    createdAt: str
    updatedAt: str


class QualificationListResponse(BaseModel):
    items: list[QualificationItem]


class QualificationSubmitResponse(BaseModel):
    qualificationId: str
    status: str
    statusLabel: str
    submittedAt: Optional[str] = None


class DraftSaveResponse(BaseModel):
    qualificationId: str
    status: str
    statusLabel: str
    savedAt: Optional[str] = None


# ──────────────────────────────────────────────
# Review
# ──────────────────────────────────────────────
class ReviewRequest(BaseModel):
    action: str = Field(..., description="Review action: approve or reject")
    comment: Optional[str] = Field(None, max_length=500, description="Review comment or rejection reason")


class ReviewItem(BaseModel):
    reviewId: str
    reviewerName: Optional[str] = None
    action: str
    actionLabel: str
    comment: Optional[str] = None
    reviewedAt: Optional[str] = None


class ReviewListResponse(BaseModel):
    items: list[ReviewItem]


# ──────────────────────────────────────────────
# Helper: status labels
# ──────────────────────────────────────────────
STATUS_LABELS = {
    "draft": "草稿",
    "reviewing": "待审核",
    "approved": "已通过",
    "rejected": "已驳回",
    "expiring": "即将过期",
    "expired": "已过期",
}

ACTION_LABELS = {
    "approve": "通过",
    "rejected": "驳回",
    "reject": "驳回",
}


def get_status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def get_action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)
