"""Sharing service layer -- business logic for sharing rules and contribution coefficient."""

import base64
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, ConflictException, NotFoundException
from ..models.sharing import (
    RuleBase,
    RuleStatus,
    RuleType,
    SharingRule,
    sharing_rule_change_logs,
)
from ..schemas.sharing import SharingRuleCreate, SharingRuleUpdate


# ============================================================================
# Cursor helpers
# ============================================================================
def _encode_cursor(id_value: int) -> str:
    """Encode a rule ID as a base64 cursor string."""
    return base64.urlsafe_b64encode(str(id_value).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int | None:
    """Decode a base64 cursor string back to a rule ID."""
    if not cursor:
        return None
    try:
        padding = 4 - len(cursor) % 4
        if padding != 4:
            cursor += "=" * padding
        return int(base64.urlsafe_b64decode(cursor).decode())
    except Exception:
        return None


# ============================================================================
# Status label helper
# ============================================================================
def _status_label(status: RuleStatus) -> str:
    """Return a human-readable label for the rule status."""
    labels = {
        RuleStatus.ACTIVE: "Active",
        RuleStatus.INACTIVE: "Inactive",
        RuleStatus.EXPIRED: "Expired",
    }
    return labels.get(status, status.value)


def _rule_to_response(rule: SharingRule) -> dict:
    """Serialize a SharingRule ORM object to a response dict."""
    return {
        "ruleId": str(rule.id),
        "level": rule.level,
        "rule_type": rule.rule_type.value if hasattr(rule.rule_type, "value") else rule.rule_type,
        "base": rule.base.value if hasattr(rule.base, "value") else rule.base,
        "value": rule.value,
        "effective_at": rule.effective_at,
        "expires_at": rule.expires_at,
        "status": rule.status.value if hasattr(rule.status, "value") else rule.status,
        "statusLabel": _status_label(rule.status),
        "version": rule.version,
        "created_by": rule.created_by,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


# ============================================================================
# Conflict checking
# ============================================================================
async def _check_active_conflict(db: AsyncSession, level: int) -> Optional[SharingRule]:
    """Check if there is already an active rule at the given level."""
    result = await db.execute(
        select(SharingRule).where(
            SharingRule.level == level,
            SharingRule.status == RuleStatus.ACTIVE,
        )
    )
    return result.scalars().first()


# ============================================================================
# CRUD operations
# ============================================================================
async def create_rule(
    db: AsyncSession,
    data: SharingRuleCreate,
    created_by: int | None = None,
) -> SharingRule:
    """Create a new sharing rule.

    Validates no active rule conflict at the same level before creating.
    """
    # Check for active rule conflict at the same level
    conflict = await _check_active_conflict(db, data.level)
    if conflict is not None:
        raise ConflictException(
            message="An active rule already exists at this level",
            detail={"level": data.level, "existingRuleId": str(conflict.id)},
        )

    now = datetime.now(timezone.utc)
    rule = SharingRule(
        level=data.level,
        rule_type=RuleType(data.rule_type),
        base=RuleBase(data.base),
        value=data.value,
        effective_at=data.effective_at,
        expires_at=data.expires_at,
        status=RuleStatus.ACTIVE,
        version=1,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


async def update_rule(
    db: AsyncSession,
    rule_id: int,
    data: SharingRuleUpdate,
    changed_by: int | None = None,
) -> SharingRule:
    """Update a sharing rule with optimistic locking and change logging.

    Raises ConflictException if the version does not match (optimistic lock).
    Records old and new values in the sharing_rule_change_logs table.
    """
    result = await db.execute(select(SharingRule).where(SharingRule.id == rule_id))
    rule = result.scalar_one_or_none()

    if rule is None:
        raise NotFoundException(message="Sharing rule not found")

    if data.version != rule.version:
        raise ConflictException(
            message="Version conflict: the rule has been modified by another user",
            detail={"currentVersion": rule.version, "providedVersion": data.version},
        )

    # Save old values for audit log
    old_values = {
        "level": rule.level,
        "rule_type": rule.rule_type.value,
        "base": rule.base.value,
        "value": rule.value,
        "effective_at": rule.effective_at.isoformat() if rule.effective_at else None,
        "expires_at": rule.expires_at.isoformat() if rule.expires_at else None,
    }

    # Apply updates
    update_data = data.model_dump(exclude_unset=True)
    update_data.pop("version", None)

    for key, value in update_data.items():
        if value is not None and hasattr(rule, key):
            if key == "rule_type":
                value = RuleType(value)
            elif key == "base":
                value = RuleBase(value)
            setattr(rule, key, value)

    rule.version += 1
    rule.updated_at = datetime.now(timezone.utc)

    await db.flush()

    # Record change log
    new_values = {
        "level": rule.level,
        "rule_type": rule.rule_type.value,
        "base": rule.base.value,
        "value": rule.value,
        "effective_at": rule.effective_at.isoformat() if rule.effective_at else None,
        "expires_at": rule.expires_at.isoformat() if rule.expires_at else None,
    }

    await db.execute(
        insert(sharing_rule_change_logs).values(
            rule_id=rule.id,
            changed_by=changed_by or 0,
            old_value=old_values,
            new_value=new_values,
            created_at=datetime.now(timezone.utc),
        )
    )

    await db.flush()
    await db.refresh(rule)
    return rule


async def deactivate_rule(db: AsyncSession, rule_id: int) -> SharingRule:
    """Deactivate an active sharing rule."""
    result = await db.execute(select(SharingRule).where(SharingRule.id == rule_id))
    rule = result.scalar_one_or_none()

    if rule is None:
        raise NotFoundException(message="Sharing rule not found")

    if rule.status == RuleStatus.INACTIVE:
        raise BadRequestException(message="Rule is already inactive")

    if rule.status == RuleStatus.EXPIRED:
        raise BadRequestException(message="Cannot deactivate an expired rule")

    rule.status = RuleStatus.INACTIVE
    rule.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(rule)
    return rule


# ============================================================================
# Query operations
# ============================================================================
async def get_rules(
    db: AsyncSession,
    *,
    level: int | None = None,
    status: str | None = None,
    cursor: str | None = None,
    page_size: int = 20,
) -> dict:
    """List sharing rules with optional filters and cursor pagination."""
    page_size = max(1, min(page_size, 100))

    stmt = select(SharingRule)

    if level is not None:
        stmt = stmt.where(SharingRule.level == level)

    if status:
        try:
            stmt = stmt.where(SharingRule.status == RuleStatus(status))
        except ValueError:
            raise BadRequestException(message=f"Invalid status: {status}")

    # Cursor pagination: sort by id desc
    cursor_id = _decode_cursor(cursor)
    if cursor_id is not None:
        stmt = stmt.where(SharingRule.id < cursor_id)

    stmt = stmt.order_by(SharingRule.id.desc())
    stmt = stmt.limit(page_size + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars())

    has_more = len(rows) > page_size
    if has_more:
        rows = rows[:page_size]

    next_cursor = _encode_cursor(rows[-1].id) if rows and has_more else None

    items = [_rule_to_response(r) for r in rows]
    return {"items": items, "nextCursor": next_cursor, "hasMore": has_more}


async def get_active_rule_for_level(db: AsyncSession, level: int) -> Optional[SharingRule]:
    """Return the currently active rule for a given level (effective_at <= now)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(SharingRule).where(
            SharingRule.level == level,
            SharingRule.status == RuleStatus.ACTIVE,
            SharingRule.effective_at <= now,
        )
    )
    return result.scalars().first()


async def get_rule_by_id(db: AsyncSession, rule_id: int) -> Optional[SharingRule]:
    """Get a single sharing rule by ID."""
    result = await db.execute(select(SharingRule).where(SharingRule.id == rule_id))
    return result.scalar_one_or_none()


# ============================================================================
# Calculation
# ============================================================================
async def apply_rule(rule, base_amount_cent: int) -> int:
    """Calculate the share amount in cents based on the rule type.

    Args:
        rule: A SharingRule ORM object or mock with rule_type and value attributes.
        base_amount_cent: The base amount in cents (integer).

    Returns:
        The calculated share amount in cents.
    """
    rule_type = rule.rule_type
    # Handle both enum and string values (for mock objects)
    if hasattr(rule_type, "value"):
        rule_type = rule_type.value

    if rule_type == "fixed_ratio":
        ratio = float(rule.value)
        return int(base_amount_cent * ratio)
    elif rule_type == "fixed_amount":
        return int(rule.value)
    elif rule_type == "tiered":
        tiers = json.loads(rule.value)
        # Sort tiers by threshold descending to find the highest applicable tier
        tiers_sorted = sorted(tiers, key=lambda t: t["threshold"], reverse=True)
        for tier in tiers_sorted:
            if base_amount_cent > tier["threshold"]:
                return int(base_amount_cent * tier["ratio"])
        return 0
    return 0


# ============================================================================
# Scheduler helper
# ============================================================================
async def activate_due_rules(db: AsyncSession) -> int:
    """Called by scheduler to activate rules where effective_at <= now.

    Note: Rules are created with ACTIVE status; this function is reserved
    for future use when a PENDING status is added to the lifecycle.

    Returns:
        Number of rules activated.
    """
    # Currently a no-op since all rules are created as ACTIVE.
    # Reserved for future PENDING -> ACTIVE transition support.
    return 0


async def check_conflicts(db: AsyncSession, level: int) -> Optional[SharingRule]:
    """Check for overlapping active rules at the given level.

    Returns the conflicting rule if found, None otherwise.
    """
    return await _check_active_conflict(db, level)
