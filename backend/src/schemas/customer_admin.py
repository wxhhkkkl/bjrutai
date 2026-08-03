"""Pydantic schemas for admin customer management endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class CustomerCreateRequest(BaseModel):
    """Manual customer entry (FR-005/FR-006/FR-008)."""

    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=7, max_length=20)
    id_card: str = Field(..., min_length=18, max_length=18, alias="idCard")
    medical_account: Optional[str] = Field(None, max_length=64, alias="medicalAccount")
    family_phone: Optional[str] = Field(None, max_length=20, alias="familyPhone")
    note: Optional[str] = Field(None, max_length=500)
    distributor_id: str = Field(..., alias="distributorId")

    class Config:
        populate_by_name = True


class CustomerUpdateRequest(BaseModel):
    """Customer profile update. Sensitive fields require changeReason (FR-010)."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=20)
    id_card: Optional[str] = Field(None, min_length=18, max_length=18, alias="idCard")
    medical_account: Optional[str] = Field(None, max_length=64, alias="medicalAccount")
    family_phone: Optional[str] = Field(None, max_length=20, alias="familyPhone")
    note: Optional[str] = Field(None, max_length=500)
    change_reason: Optional[str] = Field(None, max_length=500, alias="changeReason")

    class Config:
        populate_by_name = True


class CustomerTransferRequest(BaseModel):
    """Change a customer's promoter (distributor) with an audit reason (FR-011)."""

    new_distributor_id: str = Field(..., alias="newDistributorId")
    reason: str = Field(..., min_length=1, max_length=500)

    class Config:
        populate_by_name = True
