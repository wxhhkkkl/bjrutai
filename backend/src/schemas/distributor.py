"""Pydantic schemas for distributor endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class DistributorCreate(BaseModel):
    """Schema for creating a distributor account within an org."""

    name: str = Field(..., min_length=1, max_length=64)
    phone: str = Field(..., pattern=r"^\d{11}$")
    initial_password: str = Field(..., min_length=8, max_length=128, alias="initialPassword")

    class Config:
        populate_by_name = True


class DistributorUpdate(BaseModel):
    """Schema for adjusting distributor org / status."""

    org_id: Optional[int] = Field(None, alias="orgId")
    status: Optional[str] = Field(None, description="active | disabled")

    class Config:
        populate_by_name = True


class DistributorRoleUpdate(BaseModel):
    """Schema for setting/revoking org admin role."""

    org_role: str = Field(..., alias="orgRole", description="member | admin")

    class Config:
        populate_by_name = True


class ResetPassword(BaseModel):
    """Schema for resetting a distributor's login credential."""

    new_password: str = Field(..., min_length=8, max_length=128, alias="newPassword")

    class Config:
        populate_by_name = True


class DistributorResponse(BaseModel):
    """Response for a distributor record."""

    distributor_id: str = Field(..., alias="distributorId")
    org_id: str = Field(..., alias="orgId")
    org_name: Optional[str] = Field(None, alias="orgName")
    name: Optional[str] = None
    phone: Optional[str] = None
    org_role: str = Field(..., alias="orgRole")
    status: str
    wechat_bound: bool = Field(False, alias="wechatBound")
    created_at: Optional[str] = Field(None, alias="createdAt")

    class Config:
        populate_by_name = True
