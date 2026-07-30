"""Admin management endpoints.

All endpoints require admin authentication.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ..deps import get_admin_user
from ...schemas.hierarchy import (
    HierarchyNodeCreate,
    HierarchyNodeCreateResponse,
    HierarchyNodeUpdate,
    HierarchyNodeUpdateResponse,
    MigrateRequest,
    MigrateResponse,
)
from ...schemas.binding import UnbindRequest, TransferRequest
from ...services import hierarchy_service
from ...services.binding_service import get_binding_service

router = APIRouter(prefix="/admin/hierarchy", tags=["admin-hierarchy"])

# ---------------------------------------------------------------------------
# Separate router for admin binding endpoints
# ---------------------------------------------------------------------------
admin_bindings_router = APIRouter(prefix="/admin/bindings", tags=["admin-bindings"])


# =============================================================================
# Hierarchy endpoints (existing)
# =============================================================================

@router.get("")
async def get_full_tree(
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Return the full hierarchy tree."""
    result = await hierarchy_service.get_tree(db)
    return _build_response(0, "success", result)


@router.get("/nodes/{node_id}")
async def get_subtree(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Return the subtree rooted at the given node."""
    result = await hierarchy_service.get_subtree(db, node_id)
    return _build_response(0, "success", result)


@router.post("/nodes")
async def create_node(
    data: HierarchyNodeCreate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Create a new hierarchy node under a parent."""
    node = await hierarchy_service.create_node(db, data)
    return _build_response(
        0,
        "success",
        {
            "nodeId": str(node.id),
            "name": node.name,
            "nodeType": node.node_type.value,
            "level": node.level,
            "parentId": str(node.parent_id) if node.parent_id else None,
            "createdAt": node.created_at.isoformat() if node.created_at else None,
        },
    )


@router.put("/nodes/{node_id}")
async def update_node(
    node_id: int,
    data: HierarchyNodeUpdate,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Update a hierarchy node's name or type."""
    node = await hierarchy_service.update_node(db, node_id, data)
    return _build_response(
        0,
        "success",
        {
            "nodeId": str(node.id),
            "name": node.name,
            "nodeType": node.node_type.value,
            "updatedAt": node.updated_at.isoformat() if node.updated_at else None,
        },
    )


@router.delete("/nodes/{node_id}")
async def delete_node(
    node_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Delete a leaf hierarchy node. Non-leaf nodes cannot be deleted."""
    await hierarchy_service.delete_node(db, node_id)
    return _build_response(0, "success", None)


@router.post("/nodes/{node_id}/migrate")
async def migrate_branch(
    node_id: int,
    data: MigrateRequest,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Migrate a branch (node + all descendants) to a new parent.

    Creates a hierarchy snapshot before migration. Cycle detection prevents
    migrating a node to its own descendant.
    """
    result = await hierarchy_service.migrate_branch(db, node_id, data)
    return _build_response(0, "success", result)


# =============================================================================
# Admin binding endpoints
# =============================================================================


@admin_bindings_router.post("/{binding_request_id}/unbind")
async def admin_unbind_customer(
    binding_request_id: int,
    data: UnbindRequest,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Admin unbinds a customer from their promoter. Requires a reason.

    Checks for unsettled contributions and creates a full audit log entry.
    """
    admin_id = int(_current_admin["sub"])
    svc = get_binding_service()
    result = await svc.unbind_customer(
        db,
        binding_request_id,
        reason=data.reason,
        operator_id=admin_id,
    )
    await db.commit()
    return _build_response(0, "success", result)


@admin_bindings_router.post("/{binding_request_id}/transfer")
async def admin_transfer_customer(
    binding_request_id: int,
    data: TransferRequest,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Admin transfers a customer to a different promoter.

    Preserves historical contribution data. Warns if unsettled contributions exist.
    """
    admin_id = int(_current_admin["sub"])

    try:
        new_promoter_id = int(data.newPromoterId)
    except (ValueError, TypeError):
        from ...core.exceptions import BadRequestException
        raise BadRequestException(message="Invalid newPromoterId")

    svc = get_binding_service()
    result = await svc.transfer_customer(
        db,
        binding_request_id,
        new_promoter_id=new_promoter_id,
        operator_id=admin_id,
        reason=data.reason,
    )
    await db.commit()
    return _build_response(0, "success", result)
