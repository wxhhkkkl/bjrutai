"""Pydantic schemas for hierarchy endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class HierarchyNodeCreate(BaseModel):
    """Schema for creating a new hierarchy node."""

    parent_id: int = Field(..., alias="parentId", description="Parent node ID")
    name: str = Field(..., min_length=1, max_length=200, description="Node name")
    node_type: str = Field(..., min_length=1, max_length=50, alias="nodeType", description="Node type")

    class Config:
        populate_by_name = True


class HierarchyNodeUpdate(BaseModel):
    """Schema for updating an existing hierarchy node."""

    name: Optional[str] = Field(None, min_length=1, max_length=200, description="New node name")
    node_type: Optional[str] = Field(None, min_length=1, max_length=50, alias="nodeType", description="New node type")

    class Config:
        populate_by_name = True


class MigrateRequest(BaseModel):
    """Schema for migrating a branch to a new parent."""

    target_parent_id: int = Field(..., alias="targetParentId", description="New parent node ID")

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class HierarchyNodeResponse(BaseModel):
    """Response for a single hierarchy node (recursive children)."""

    node_id: str = Field(..., alias="nodeId")
    name: str
    node_type: str = Field(..., alias="nodeType")
    level: int
    parent_id: Optional[str] = Field(None, alias="parentId")
    children: list["HierarchyNodeResponse"] = []
    created_at: Optional[str] = Field(None, alias="createdAt")
    updated_at: Optional[str] = Field(None, alias="updatedAt")

    class Config:
        populate_by_name = True


class HierarchyTreeResponse(BaseModel):
    """Response for the full hierarchy tree."""

    tree: Optional[HierarchyNodeResponse] = None
    total_nodes: int = Field(0, alias="totalNodes")
    max_depth: int = Field(0, alias="maxDepth")

    class Config:
        populate_by_name = True


class HierarchyNodeCreateResponse(BaseModel):
    """Response after creating a node."""

    node_id: str = Field(..., alias="nodeId")
    name: str
    node_type: str = Field(..., alias="nodeType")
    level: int
    parent_id: Optional[str] = Field(None, alias="parentId")
    created_at: Optional[str] = Field(None, alias="createdAt")

    class Config:
        populate_by_name = True


class HierarchyNodeUpdateResponse(BaseModel):
    """Response after updating a node."""

    node_id: str = Field(..., alias="nodeId")
    name: str
    node_type: str = Field(..., alias="nodeType")
    updated_at: Optional[str] = Field(None, alias="updatedAt")

    class Config:
        populate_by_name = True


class MigrateResponse(BaseModel):
    """Response after migrating a branch."""

    migrated_node_id: str = Field(..., alias="migratedNodeId")
    migrated_node_name: str = Field(..., alias="migratedNodeName")
    from_parent_id: Optional[str] = Field(None, alias="fromParentId")
    to_parent_id: str = Field(..., alias="toParentId")
    migrated_at: Optional[str] = Field(None, alias="migratedAt")

    class Config:
        populate_by_name = True
