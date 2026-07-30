"""Hierarchy service: business logic for org-tree CRUD and migration."""

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ..models.hierarchy import HierarchyNode, NodeType, hierarchy_snapshots
from ..schemas.hierarchy import (
    HierarchyNodeCreate,
    HierarchyNodeUpdate,
    MigrateRequest,
)

MAX_LEVEL = 6


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------
def _node_to_dict(node: HierarchyNode, include_children: bool = True) -> dict:
    """Convert a HierarchyNode ORM instance to a response dict."""
    return {
        "nodeId": str(node.id),
        "name": node.name,
        "nodeType": node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
        "level": node.level,
        "parentId": str(node.parent_id) if node.parent_id else None,
        "children": [_node_to_dict(c) for c in node.children] if include_children and node.children else [],
        "createdAt": node.created_at.isoformat() if node.created_at else None,
        "updatedAt": node.updated_at.isoformat() if node.updated_at else None,
    }


def _compute_depth(node: dict) -> int:
    """Compute max depth of a tree node dict."""
    if not node.get("children"):
        return node.get("level", 1)
    return max(_compute_depth(c) for c in node["children"])


async def _get_node_or_404(db: AsyncSession, node_id: int) -> HierarchyNode:
    """Fetch a node by ID or raise NotFoundException."""
    result = await db.execute(
        select(HierarchyNode).where(HierarchyNode.id == node_id)
    )
    node = result.scalars().first()
    if node is None:
        raise NotFoundException(message="Node not found")
    return node


async def _get_node_by_id(db: AsyncSession, node_id: int) -> Optional[HierarchyNode]:
    """Fetch a node by ID without children loaded. Returns None if not found."""
    result = await db.execute(
        select(HierarchyNode).where(HierarchyNode.id == node_id)
    )
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Tree retrieval
# ---------------------------------------------------------------------------
async def get_tree(db: AsyncSession) -> dict:
    """Return the full hierarchy tree starting from the root node.

    Loads all nodes and builds the tree in Python for reliable deep nesting.
    """
    # Load all nodes from DB
    result = await db.execute(select(HierarchyNode))
    all_nodes = result.scalars().all()

    if not all_nodes:
        return {"tree": None, "totalNodes": 0, "maxDepth": 0}

    # Build lookup by id and group by parent_id
    node_map: dict[int, dict] = {}
    children_map: dict[int, list[dict]] = {}

    for node in all_nodes:
        node_dict = _node_to_dict(node, include_children=False)
        node_dict["children"] = []
        node_map[node.id] = node_dict
        children_map.setdefault(node.parent_id if node.parent_id else 0, []).append(node_dict)

    # Recursively assemble the tree starting from root (parent_id is None -> use 0 as key)
    def build_subtree(node_dict: dict) -> dict:
        nid = int(node_dict["nodeId"])
        if nid in children_map:
            for child_dict in children_map[nid]:
                node_dict["children"].append(build_subtree(child_dict))
        return node_dict

    # Find roots (parent_id is None)
    roots = [node_map[n.id] for n in all_nodes if n.parent_id is None]
    if not roots:
        return {"tree": None, "totalNodes": len(all_nodes), "maxDepth": 0}

    root = roots[0]
    tree = build_subtree(root)

    total_nodes = len(all_nodes)
    depth = _compute_depth(tree)

    return {"tree": tree, "totalNodes": total_nodes, "maxDepth": depth}


async def get_subtree(db: AsyncSession, node_id: int) -> dict:
    """Return the subtree rooted at the given node.

    Loads all nodes and builds the subtree starting from the given node_id.
    """
    # Verify node exists
    await _get_node_or_404(db, node_id)

    # Load all nodes
    result = await db.execute(select(HierarchyNode))
    all_nodes = result.scalars().all()

    # Build lookup and children map
    node_map: dict[int, dict] = {}
    children_map: dict[int, list[dict]] = {}

    for node in all_nodes:
        node_dict = _node_to_dict(node, include_children=False)
        node_dict["children"] = []
        node_map[node.id] = node_dict
        children_map.setdefault(node.parent_id if node.parent_id else 0, []).append(node_dict)

    def build_subtree(node_dict: dict) -> dict:
        nid = int(node_dict["nodeId"])
        if nid in children_map:
            for child_dict in children_map[nid]:
                node_dict["children"].append(build_subtree(child_dict))
        return node_dict

    root_dict = node_map[node_id]
    return build_subtree(root_dict)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
async def create_node(db: AsyncSession, data: HierarchyNodeCreate) -> HierarchyNode:
    """Create a new hierarchy node under *parent_id*.

    Raises:
        NotFoundException: parent does not exist.
        ConflictException: a sibling with the same name already exists.
    """
    # Validate parent
    parent = await _get_node_by_id(db, data.parent_id)
    if parent is None:
        raise NotFoundException(message="Parent node not found")

    # Validate node_type
    valid_types = {t.value for t in NodeType}
    if data.node_type not in valid_types:
        raise BadRequestException(
            message=f"Invalid node type: {data.node_type}. Valid types: {', '.join(sorted(valid_types))}"
        )

    # Check duplicate name under same parent
    result = await db.execute(
        select(HierarchyNode).where(
            HierarchyNode.parent_id == data.parent_id,
            HierarchyNode.name == data.name,
        )
    )
    existing = result.scalars().first()
    if existing is not None:
        raise ConflictException(message="Node name already exists under this parent")

    # Compute level
    new_level = parent.level + 1
    if new_level > MAX_LEVEL:
        raise BadRequestException(message=f"Maximum hierarchy level ({MAX_LEVEL}) exceeded")

    node = HierarchyNode(
        parent_id=data.parent_id,
        level=new_level,
        node_type=NodeType(data.node_type),
        name=data.name,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(node)
    await db.flush()
    await db.refresh(node)
    return node


async def update_node(db: AsyncSession, node_id: int, data: HierarchyNodeUpdate) -> HierarchyNode:
    """Update a node's name and/or type.

    Raises:
        NotFoundException: node not found.
    """
    node = await _get_node_by_id(db, node_id)
    if node is None:
        raise NotFoundException(message="Node not found")

    if data.name is not None:
        # Check duplicate name under same parent (if changing name)
        result = await db.execute(
            select(HierarchyNode).where(
                HierarchyNode.parent_id == node.parent_id,
                HierarchyNode.name == data.name,
                HierarchyNode.id != node_id,
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            raise ConflictException(message="Node name already exists under this parent")
        node.name = data.name

    if data.node_type is not None:
        valid_types = {t.value for t in NodeType}
        if data.node_type not in valid_types:
            raise BadRequestException(
                message=f"Invalid node type: {data.node_type}. Valid types: {', '.join(sorted(valid_types))}"
            )
        node.node_type = NodeType(data.node_type)

    node.updated_at = datetime.now(timezone.utc)
    db.add(node)
    await db.flush()
    await db.refresh(node)
    return node


async def delete_node(db: AsyncSession, node_id: int) -> None:
    """Delete a hierarchy node. Only leaf nodes (no children) can be deleted.

    Raises:
        NotFoundException: node not found.
        BadRequestException: node has children (cannot delete).
    """
    node = await _get_node_or_404(db, node_id)

    # Check for children
    result = await db.execute(
        select(HierarchyNode).where(HierarchyNode.parent_id == node_id)
    )
    children = result.scalars().all()
    if children:
        raise BadRequestException(message="Cannot delete node with child nodes (migrate first)")

    await db.delete(node)
    await db.flush()


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------
async def detect_cycle(db: AsyncSession, node_id: int, new_parent_id: int) -> bool:
    """Check if reassigning *node_id* to *new_parent_id* would create a cycle.

    Returns True if a cycle WOULD be created (i.e. *new_parent_id* is a
    descendant of *node_id*, or they are the same node).
    """
    if node_id == new_parent_id:
        return True

    # Collect all descendant IDs of node_id via BFS/DFS
    descendants: set[int] = set()
    stack = [node_id]
    while stack:
        current = stack.pop()
        if current in descendants:
            continue
        descendants.add(current)
        result = await db.execute(
            select(HierarchyNode.id).where(HierarchyNode.parent_id == current)
        )
        child_ids = [row[0] for row in result.fetchall()]
        for cid in child_ids:
            if cid not in descendants:
                stack.append(cid)

    return new_parent_id in descendants


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
async def migrate_branch(db: AsyncSession, node_id: int, data: MigrateRequest) -> dict:
    """Move *node_id* (and all its descendants) under *target_parent_id*.

    Performs cycle detection before migrating. Creates a hierarchy_snapshots
    record of the node's state before migration.

    Raises:
        NotFoundException: source node or target parent not found.
        BadRequestException: cycle detected.
    """
    node = await _get_node_by_id(db, node_id)
    if node is None:
        raise NotFoundException(message="Source node not found")

    target_parent = await _get_node_by_id(db, data.target_parent_id)
    if target_parent is None:
        raise NotFoundException(message="Target parent node not found")

    # Cycle check
    if await detect_cycle(db, node_id, data.target_parent_id):
        raise BadRequestException(message="Cannot migrate a node to its own descendant (circular)")

    # Create snapshot before migration
    snapshot_data = _node_to_dict(node, include_children=False)
    from_parent_id = node.parent_id
    from_parent_name = None
    if from_parent_id:
        from_parent = await _get_node_by_id(db, from_parent_id)
        if from_parent:
            from_parent_name = from_parent.name

    stmt = hierarchy_snapshots.insert().values(
        node_id=node.id,
        snapshot_data=json.dumps(snapshot_data, default=str),
        created_at=datetime.now(timezone.utc),
    )
    await db.execute(stmt)

    # Perform the move: update parent_id, recompute level
    level_diff = (target_parent.level + 1) - node.level

    # Update the moved node
    old_parent_id = node.parent_id
    node.parent_id = data.target_parent_id
    node.level = target_parent.level + 1
    node.updated_at = datetime.now(timezone.utc)
    db.add(node)

    # Recursively update levels of all descendants
    await _update_descendant_levels(db, node_id, level_diff)

    await db.flush()
    await db.refresh(node)

    return {
        "migratedNodeId": str(node.id),
        "migratedNodeName": node.name,
        "fromParentId": str(old_parent_id) if old_parent_id else None,
        "fromParentName": from_parent_name,
        "toParentId": str(data.target_parent_id),
        "toParentName": target_parent.name,
        "migratedAt": datetime.now(timezone.utc).isoformat(),
    }


async def _update_descendant_levels(db: AsyncSession, node_id: int, delta: int) -> None:
    """Recursively adjust levels of all descendants by *delta*."""
    result = await db.execute(
        select(HierarchyNode).where(HierarchyNode.parent_id == node_id)
    )
    children = result.scalars().all()
    for child in children:
        child.level += delta
        child.updated_at = datetime.now(timezone.utc)
        db.add(child)
        await _update_descendant_levels(db, child.id, delta)


# ---------------------------------------------------------------------------
# Ancestors / Descendants retrieval
# ---------------------------------------------------------------------------
async def get_ancestors(db: AsyncSession, node_id: int) -> list[dict]:
    """Return the ancestor chain from L1 (root) down to the given node."""
    node = await _get_node_by_id(db, node_id)
    if node is None:
        raise NotFoundException(message="Node not found")

    ancestors: list[dict] = []
    current = node
    while current.parent_id is not None:
        parent = await _get_node_by_id(db, current.parent_id)
        if parent is None:
            break
        ancestors.append({
            "nodeId": str(parent.id),
            "name": parent.name,
            "nodeType": parent.node_type.value if hasattr(parent.node_type, "value") else str(parent.node_type),
            "level": parent.level,
        })
        current = parent

    # Reverse to get L1 -> ... -> parent order
    ancestors.reverse()
    return ancestors


async def get_descendants(db: AsyncSession, node_id: int) -> list[dict]:
    """Return all descendant nodes in the subtree of *node_id*."""
    node = await _get_node_by_id(db, node_id)
    if node is None:
        raise NotFoundException(message="Node not found")

    descendants: list[dict] = []
    stack = [node_id]
    while stack:
        current_id = stack.pop()
        result = await db.execute(
            select(HierarchyNode).where(HierarchyNode.parent_id == current_id)
        )
        children = result.scalars().all()
        for child in children:
            descendants.append(_node_to_dict(child, include_children=False))
            stack.append(child.id)

    return descendants


async def get_promoters_by_level(db: AsyncSession, level: int) -> list[dict]:
    """Return all promoter-type nodes at a given hierarchy level."""
    result = await db.execute(
        select(HierarchyNode).where(
            HierarchyNode.level == level,
            HierarchyNode.node_type == NodeType.PROMOTER,
        )
    )
    nodes = result.scalars().all()
    return [_node_to_dict(n, include_children=False) for n in nodes]
