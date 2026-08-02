"""Pydantic schemas for organization tree endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class OrgCreate(BaseModel):
    """Schema for creating a new organization node."""

    name: str = Field(..., min_length=1, max_length=128, description="Organization name")
    parent_id: Optional[int] = Field(None, alias="parentId", description="Parent org ID (null = root)")
    org_type: str = Field(..., min_length=1, max_length=50, alias="orgType", description="Org type")
    sort_order: int = Field(0, alias="sortOrder", description="Sort order among siblings")

    class Config:
        populate_by_name = True


class OrgUpdate(BaseModel):
    """Schema for updating an existing organization node."""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    org_type: Optional[str] = Field(None, min_length=1, max_length=50, alias="orgType")
    sort_order: Optional[int] = Field(None, alias="sortOrder")
    status: Optional[str] = Field(None, description="active | disabled")

    class Config:
        populate_by_name = True


class OrgMigrateRequest(BaseModel):
    """Schema for migrating an org subtree under a new parent."""

    new_parent_id: Optional[int] = Field(None, alias="newParentId", description="New parent org ID (null = root)")
    new_sort_order: Optional[int] = Field(None, alias="newSortOrder")

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class OrgNodeResponse(BaseModel):
    """Response for a single org node (recursive children)."""

    org_id: str = Field(..., alias="orgId")
    name: str
    org_type: str = Field(..., alias="orgType")
    level: int
    parent_id: Optional[str] = Field(None, alias="parentId")
    sort_order: int = Field(0, alias="sortOrder")
    status: str
    children: list["OrgNodeResponse"] = []
    created_at: Optional[str] = Field(None, alias="createdAt")
    updated_at: Optional[str] = Field(None, alias="updatedAt")

    class Config:
        populate_by_name = True


class OrgTreeResponse(BaseModel):
    """Response for the full organization tree."""

    tree: Optional[OrgNodeResponse] = None
    total_nodes: int = Field(0, alias="totalNodes")
    max_depth: int = Field(0, alias="maxDepth")

    class Config:
        populate_by_name = True


class OrgHistoryItem(BaseModel):
    """Response item for an org operation history record."""

    org_id: str = Field(..., alias="orgId")
    action: str
    operator_id: Optional[str] = Field(None, alias="operatorId")
    detail: Optional[dict] = None
    created_at: Optional[str] = Field(None, alias="createdAt")

    class Config:
        populate_by_name = True
