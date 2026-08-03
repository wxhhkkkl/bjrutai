"""Organization service: org-tree CRUD, migration, cycle detection, history."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ..models.organization import Organization, OrgStatus
from ..models.org_history import OrgHistory, OrgHistoryAction
from ..schemas.organization import (
    OrgCreate,
    OrgMigrateRequest,
    OrgUpdate,
)

# 最大深度：None = 不限制（后台可配置项；未配置则不限制）
MAX_DEPTH: Optional[int] = None


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def _org_to_dict(node: Organization, include_children: bool = True) -> dict:
    """Convert an Organization ORM instance to a response dict.

    ``children`` is only read when it has already been loaded — accessing an
    unloaded collection in an async context would raise MissingGreenlet.
    """
    children: list = []
    if include_children and "children" in node.__dict__:
        children = [_org_to_dict(c) for c in node.children]
    return {
        "orgId": str(node.id),
        "name": node.name,
        "orgType": node.org_type,
        "level": node.level,
        "parentId": str(node.parent_id) if node.parent_id else None,
        "sortOrder": node.sort_order,
        "status": node.status.value if hasattr(node.status, "value") else str(node.status),
        "qualificationStatus": "none",  # 由 get_tree/get_subtree 填充：approved/reviewing/rejected
        "children": children,
        "createdAt": node.created_at.isoformat() if node.created_at else None,
        "updatedAt": node.updated_at.isoformat() if node.updated_at else None,
    }


def _compute_depth(node: dict) -> int:
    """Compute max depth of a tree node dict."""
    if not node.get("children"):
        return node.get("level", 1)
    return max(_compute_depth(c) for c in node["children"])


async def _get_org_or_404(db: AsyncSession, org_id: int) -> Organization:
    """Fetch an org by ID or raise NotFoundException."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    node = result.scalars().first()
    if node is None:
        raise NotFoundException(message="Organization not found")
    return node


async def _get_org_by_id(db: AsyncSession, org_id: int) -> Optional[Organization]:
    """Fetch an org by ID without children loaded. Returns None if not found."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    return result.scalars().first()


async def _record_history(
    db: AsyncSession,
    org_id: int,
    action: OrgHistoryAction,
    operator_id: Optional[int],
    detail: Optional[dict] = None,
) -> None:
    """Append an org operation history record (FR-004)."""
    history = OrgHistory(
        org_id=org_id,
        action=action,
        operator_id=operator_id,
        detail=detail,
        created_at=datetime.now(timezone.utc),
    )
    db.add(history)
    await db.flush()


# ---------------------------------------------------------------------------
# Tree retrieval
# ---------------------------------------------------------------------------
async def _org_qualification_status_map(db: AsyncSession, org_ids: set[int]) -> dict[int, str]:
    """Return org_id -> latest qualification status for display.

    Values: 'approved' / 'reviewing' / 'rejected'（无资质时不在 map 中）。
    """
    if not org_ids:
        return {}
    from ..models.org_qualification import OrganizationQualification

    result = await db.execute(
        select(OrganizationQualification)
        .where(OrganizationQualification.org_id.in_(org_ids))
        .order_by(OrganizationQualification.created_at.desc())
    )
    status_map: dict[int, str] = {}
    for q in result.scalars().all():
        if q.org_id not in status_map:
            status_map[q.org_id] = q.status.value if hasattr(q.status, "value") else str(q.status)
    return status_map


async def get_tree(db: AsyncSession) -> dict:
    """Return the full organization tree starting from the root node."""
    result = await db.execute(select(Organization))
    all_nodes = result.scalars().all()

    if not all_nodes:
        return {"tree": [], "totalNodes": 0, "maxDepth": 0}

    node_map: dict[int, dict] = {}
    children_map: dict[int, list[dict]] = {}

    for node in all_nodes:
        node_dict = _org_to_dict(node, include_children=False)
        node_dict["children"] = []
        node_map[node.id] = node_dict
        children_map.setdefault(node.parent_id if node.parent_id else 0, []).append(node_dict)

    # 填充每个组织的资质状态（最新一条）
    qual_map = await _org_qualification_status_map(db, set(node_map.keys()))
    for nid, nd in node_map.items():
        nd["qualificationStatus"] = qual_map.get(nid, "none")

    def build_subtree(node_dict: dict) -> dict:
        nid = int(node_dict["orgId"])
        if nid in children_map:
            for child_dict in children_map[nid]:
                node_dict["children"].append(build_subtree(child_dict))
        return node_dict

    roots = [node_map[n.id] for n in all_nodes if n.parent_id is None]
    if not roots:
        return {"tree": [], "totalNodes": len(all_nodes), "maxDepth": 0}

    # Multiple root orgs are allowed — return a forest of root subtrees.
    trees = [build_subtree(r) for r in roots]

    return {
        "tree": trees,
        "totalNodes": len(all_nodes),
        "maxDepth": max((_compute_depth(t) for t in trees), default=0),
    }


async def get_subtree(db: AsyncSession, org_id: int) -> dict:
    """Return the subtree rooted at the given org."""
    await _get_org_or_404(db, org_id)

    result = await db.execute(select(Organization))
    all_nodes = result.scalars().all()

    node_map: dict[int, dict] = {}
    children_map: dict[int, list[dict]] = {}

    for node in all_nodes:
        node_dict = _org_to_dict(node, include_children=False)
        node_dict["children"] = []
        node_map[node.id] = node_dict
        children_map.setdefault(node.parent_id if node.parent_id else 0, []).append(node_dict)

    qual_map = await _org_qualification_status_map(db, set(node_map.keys()))
    for nid, nd in node_map.items():
        nd["qualificationStatus"] = qual_map.get(nid, "none")

    def build_subtree(node_dict: dict) -> dict:
        nid = int(node_dict["orgId"])
        if nid in children_map:
            for child_dict in children_map[nid]:
                node_dict["children"].append(build_subtree(child_dict))
        return node_dict

    return build_subtree(node_map[org_id])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
async def create_org(
    db: AsyncSession, data: OrgCreate, operator_id: Optional[int] = None
) -> Organization:
    """Create a new organization node under *parent_id* (null = root).

    Raises:
        NotFoundException: parent does not exist.
        ConflictException: a sibling with the same name already exists.
        BadRequestException: max depth exceeded.
    """
    new_level = 1
    if data.parent_id is not None:
        parent = await _get_org_by_id(db, data.parent_id)
        if parent is None:
            raise NotFoundException(message="Parent organization not found")
        new_level = parent.level + 1
        if MAX_DEPTH is not None and new_level > MAX_DEPTH:
            raise BadRequestException(message=f"Maximum organization depth ({MAX_DEPTH}) exceeded")

    # Duplicate name under same parent
    result = await db.execute(
        select(Organization).where(
            Organization.parent_id == data.parent_id,
            Organization.name == data.name,
        )
    )
    if result.scalars().first() is not None:
        raise ConflictException(message="Organization name already exists under this parent")

    node = Organization(
        parent_id=data.parent_id,
        name=data.name,
        org_type=data.org_type,
        level=new_level,
        sort_order=data.sort_order,
        status=OrgStatus.ACTIVE,
    )
    db.add(node)
    await db.flush()
    await db.refresh(node)

    await _record_history(db, node.id, OrgHistoryAction.CREATED, operator_id, {"name": node.name, "orgType": node.org_type})
    return node


async def update_org(
    db: AsyncSession, org_id: int, data: OrgUpdate, operator_id: Optional[int] = None
) -> Organization:
    """Update an org's name/org_type/sort_order/status."""
    node = await _get_org_by_id(db, org_id)
    if node is None:
        raise NotFoundException(message="Organization not found")

    if data.name is not None:
        result = await db.execute(
            select(Organization).where(
                Organization.parent_id == node.parent_id,
                Organization.name == data.name,
                Organization.id != org_id,
            )
        )
        if result.scalars().first() is not None:
            raise ConflictException(message="Organization name already exists under this parent")
        node.name = data.name

    if data.org_type is not None:
        node.org_type = data.org_type
    if data.sort_order is not None:
        node.sort_order = data.sort_order
    if data.status is not None:
        if data.status not in {s.value for s in OrgStatus}:
            raise BadRequestException(message=f"Invalid org status: {data.status}")
        node.status = OrgStatus(data.status)

    node.updated_at = datetime.now(timezone.utc)
    db.add(node)
    await db.flush()
    await db.refresh(node)

    await _record_history(db, node.id, OrgHistoryAction.UPDATED, operator_id, data.model_dump(exclude_none=True))
    return node


async def delete_org(db: AsyncSession, org_id: int, operator_id: Optional[int] = None) -> None:
    """Delete an org. Only orgs with no children and no distributors can be deleted.

    Raises:
        NotFoundException: org not found.
        BadRequestException: org has children or distributors.
    """
    node = await _get_org_or_404(db, org_id)

    result = await db.execute(select(Organization.id).where(Organization.parent_id == org_id))
    if result.first() is not None:
        raise BadRequestException(message="该组织下仍有下级组织，请先迁移或删除下级组织后再删除")

    from ..models.distributor import Distributor

    result = await db.execute(select(Distributor.id).where(Distributor.org_id == org_id))
    if result.first() is not None:
        raise BadRequestException(message="该组织下仍有分销员，请先调整归属或停用后再删除")

    await _record_history(db, org_id, OrgHistoryAction.DELETED, operator_id)
    await db.delete(node)
    await db.flush()


# ---------------------------------------------------------------------------
# Cycle detection & migration
# ---------------------------------------------------------------------------
async def detect_cycle(db: AsyncSession, org_id: int, new_parent_id: int) -> bool:
    """Return True if reassigning *org_id* under *new_parent_id* would create a cycle."""
    if org_id == new_parent_id:
        return True

    descendants: set[int] = set()
    stack = [org_id]
    while stack:
        current = stack.pop()
        if current in descendants:
            continue
        descendants.add(current)
        result = await db.execute(
            select(Organization.id).where(Organization.parent_id == current)
        )
        for row in result.fetchall():
            if row[0] not in descendants:
                stack.append(row[0])

    return new_parent_id in descendants


async def migrate_branch(
    db: AsyncSession, org_id: int, data: OrgMigrateRequest, operator_id: Optional[int] = None
) -> dict:
    """Move *org_id* (and its descendants) under *new_parent_id* (null = root).

    Performs cycle detection before migrating and records operation history.
    """
    node = await _get_org_by_id(db, org_id)
    if node is None:
        raise NotFoundException(message="Source organization not found")

    target_parent = None
    if data.new_parent_id is not None:
        target_parent = await _get_org_by_id(db, data.new_parent_id)
        if target_parent is None:
            raise NotFoundException(message="Target parent organization not found")

    if target_parent is not None and await detect_cycle(db, org_id, data.new_parent_id):
        raise BadRequestException(message="Cannot migrate an organization to its own descendant (circular)")

    new_parent_id = data.new_parent_id
    if target_parent is not None:
        target_level = target_parent.level + 1
        if MAX_DEPTH is not None and target_level > MAX_DEPTH:
            raise BadRequestException(message=f"Maximum organization depth ({MAX_DEPTH}) exceeded")
    else:
        target_level = 1

    old_parent_id = node.parent_id
    node.parent_id = new_parent_id
    node.level = target_level
    node.updated_at = datetime.now(timezone.utc)
    db.add(node)

    # Recursively update levels of descendants (root level already set above)
    await _update_subtree_levels(db, org_id)

    await db.flush()

    await _record_history(
        db,
        org_id,
        OrgHistoryAction.MOVED,
        operator_id,
        {"fromParentId": str(old_parent_id) if old_parent_id else None, "toParentId": str(new_parent_id) if new_parent_id else None},
    )

    return {"orgId": str(node.id), "level": node.level, "parentId": str(node.parent_id) if node.parent_id else None}


async def _update_subtree_levels(db: AsyncSession, org_id: int) -> None:
    """Recompute `level` for the subtree rooted at *org_id* via BFS.

    The root's level is already set by the caller; children get parent.level + 1.
    """
    root = await _get_org_by_id(db, org_id)
    if root is None:
        return

    stack = [(root, root.level)]
    while stack:
        current, current_level = stack.pop()
        if current.id != org_id:
            current.level = current_level
            current.updated_at = datetime.now(timezone.utc)
            db.add(current)
        result = await db.execute(
            select(Organization).where(Organization.parent_id == current.id)
        )
        for child in result.scalars().all():
            stack.append((child, current_level + 1))


# ---------------------------------------------------------------------------
# Business availability
# ---------------------------------------------------------------------------
async def get_org_business_blocked_reasons(db: AsyncSession, org_id: int) -> list[str]:
    """Return reasons an org's business is blocked (empty = available).

    US1 implements the org-disabled check; US2 adds qualification checks.
    Enforcement consumers (promotion code generation, contribution calc)
    call this before allowing new business activity (FR-008 / T020).
    """
    org = await _get_org_by_id(db, org_id)
    if org is None:
        return ["org_not_found"]

    reasons: list[str] = []
    if org.status == OrgStatus.DISABLED:
        reasons.append("org_disabled")

    from ..models.org_qualification import OrgQualStatus
    from ..models.org_qualification import OrganizationQualification

    result = await db.execute(
        select(OrganizationQualification)
        .where(OrganizationQualification.org_id == org_id)
        .order_by(OrganizationQualification.created_at.desc())
    )
    latest = result.scalars().first()
    if latest is None:
        reasons.append("qualification_missing")
    elif latest.status != OrgQualStatus.APPROVED:
        reasons.append("qualification_not_approved")
    elif latest.valid_until and latest.valid_until <= datetime.utcnow():
        reasons.append("qualification_expired")

    return reasons


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
async def get_history(db: AsyncSession, org_id: int) -> list[dict]:
    """Return operation history for an org (FR-004)."""
    await _get_org_or_404(db, org_id)
    result = await db.execute(
        select(OrgHistory).where(OrgHistory.org_id == org_id).order_by(OrgHistory.created_at.desc())
    )
    return [
        {
            "orgId": str(h.org_id),
            "action": h.action.value,
            "operatorId": str(h.operator_id) if h.operator_id else None,
            "detail": h.detail,
            "createdAt": h.created_at.isoformat() if h.created_at else None,
        }
        for h in result.scalars().all()
    ]
