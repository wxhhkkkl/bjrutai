"""Pydantic schemas for organization qualification endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrgQualificationCreate(BaseModel):
    """Schema for uploading an org qualification."""

    legal_entity_name: str = Field(..., min_length=1, max_length=256, alias="legalEntityName")
    qualification_types: list[str] = Field(..., min_length=1, alias="qualificationTypes")
    credit_code: str = Field(..., min_length=1, max_length=64, alias="creditCode")
    file_urls: list[dict] = Field(..., min_length=1, alias="fileUrls")
    valid_from: Optional[str] = Field(None, alias="validFrom")
    valid_until: Optional[str] = Field(None, alias="validUntil")

    class Config:
        populate_by_name = True


class OrgQualificationReview(BaseModel):
    """Schema for reviewing an org qualification."""

    action: str = Field(..., description="approve | reject")
    comment: Optional[str] = Field(None, max_length=1000)

    class Config:
        populate_by_name = True


class OrgQualificationResponse(BaseModel):
    """Response for an org qualification record."""

    qualification_id: str = Field(..., alias="qualificationId")
    org_id: str = Field(..., alias="orgId")
    legal_entity_name: str = Field(..., alias="legalEntityName")
    qualification_types: list[str] = Field(..., alias="qualificationTypes")
    file_urls: list[dict] = Field(..., alias="fileUrls")
    valid_from: Optional[str] = Field(None, alias="validFrom")
    valid_until: str = Field(..., alias="validUntil")
    status: str
    review_comment: Optional[str] = Field(None, alias="reviewComment")
    reviewed_by: Optional[str] = Field(None, alias="reviewedBy")
    reviewed_at: Optional[str] = Field(None, alias="reviewedAt")
    created_at: Optional[str] = Field(None, alias="createdAt")

    class Config:
        populate_by_name = True
