"""Admin sharing rules management endpoints (US7).

All endpoints require admin authentication.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ...schemas.sharing import (
    CoefficientResponse,
    CoefficientUpdateRequest,
    SharingRuleCreate,
    SharingRuleResponse,
    SharingRuleUpdate,
)
from ...services.sharing_service import (
    _rule_to_response,
    create_rule,
    deactivate_rule,
    get_coefficient,
    get_rule_by_id,
    get_rules,
    update_coefficient,
    update_rule,
)
from ..deps import get_admin_user

router = APIRouter(prefix="/admin", tags=["admin-sharing"])


# ============================================================================
# Sharing Rules CRUD
# ============================================================================
@router.get("/sharing-rules")
async def list_sharing_rules(
    level: int | None = Query(None, ge=2, le=5, description="Filter by level"),
    status: str | None = Query(
        None, pattern=r"^(active|inactive|expired)$", description="Filter by status"
    ),
    cursor: str | None = Query(None, max_length=256, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """List all sharing rules with optional filters and cursor pagination."""
    result = await get_rules(db, level=level, status=status, cursor=cursor, page_size=limit)
    return _build_response(0, "success", result)


@router.post("/sharing-rules")
async def create_sharing_rule(
    data: SharingRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(get_admin_user),
):
    """Create a new sharing rule. Fails if an active rule already exists at this level."""
    created_by = current_admin.get("sub")
    try:
        created_by = int(created_by) if created_by else None
    except (ValueError, TypeError):
        created_by = None

    rule = await create_rule(db, data, created_by=created_by)
    now = datetime.now(timezone.utc)
    return _build_response(
        0,
        "success",
        {
            "ruleId": str(rule.id),
            "level": rule.level,
            "rule_type": rule.rule_type.value,
            "base": rule.base.value,
            "value": rule.value,
            "status": rule.status.value,
            "effective_at": rule.effective_at.isoformat() if rule.effective_at else None,
            "created_at": now.isoformat() if not rule.created_at else rule.created_at.isoformat(),
        },
    )


@router.put("/sharing-rules/{rule_id}")
async def update_sharing_rule(
    rule_id: int,
    data: SharingRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(get_admin_user),
):
    """Update a sharing rule with optimistic locking."""
    changed_by = current_admin.get("sub")
    try:
        changed_by = int(changed_by) if changed_by else None
    except (ValueError, TypeError):
        changed_by = None

    rule = await update_rule(db, rule_id, data, changed_by=changed_by)
    return _build_response(
        0,
        "success",
        _rule_to_response(rule),
    )


@router.post("/sharing-rules/{rule_id}/deactivate")
async def deactivate_sharing_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Deactivate an active sharing rule."""
    rule = await deactivate_rule(db, rule_id)
    now = datetime.now(timezone.utc)
    return _build_response(
        0,
        "success",
        {
            "ruleId": str(rule.id),
            "status": rule.status.value,
            "statusLabel": "Inactive",
            "deactivatedAt": now.isoformat(),
        },
    )


# ============================================================================
# Contribution Coefficient
# ============================================================================
@router.get("/contribution-coefficient")
async def get_contribution_coefficient(
    db: AsyncSession = Depends(get_db),
    _current_admin: dict = Depends(get_admin_user),
):
    """Get the current contribution coefficient."""
    coeff = await get_coefficient(db)
    if coeff is None:
        return _build_response(
            0,
            "success",
            {
                "coefficient": "1.0",
                "coefficientPercent": "100%",
                "effective_from": None,
                "previousCoefficient": None,
                "updatedAt": None,
            },
        )
    return _build_response(0, "success", coeff)


@router.put("/contribution-coefficient")
async def update_contribution_coefficient(
    data: CoefficientUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(get_admin_user),
):
    """Update the contribution coefficient."""
    created_by = current_admin.get("sub")
    try:
        created_by = int(created_by) if created_by else None
    except (ValueError, TypeError):
        created_by = None

    coeff = await update_coefficient(db, data, created_by=created_by)
    try:
        pct = f"{float(coeff.coefficient) * 100:.0f}%"
    except ValueError:
        pct = "0%"
    return _build_response(
        0,
        "success",
        {
            "coefficient": coeff.coefficient,
            "coefficientPercent": pct,
            "effective_from": coeff.effective_from.isoformat() if coeff.effective_from else None,
            "previousCoefficient": coeff.previous_coefficient,
            "updatedAt": coeff.created_at.isoformat() if coeff.created_at else None,
        },
    )
