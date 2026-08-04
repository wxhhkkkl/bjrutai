"""Admin performance rules endpoints (US1-US3 + commission calc).

All endpoints require admin auth; reads need ``sharing_rules.read``, writes
need ``sharing_rules.write`` (permission keys kept from the old sharing module).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...schemas.performance_rule import PerformanceRuleUpdateRequest
from ...services import commission_service, performance_service

router = APIRouter(prefix="/admin", tags=["admin-performance-rules"])


def _operator_id(payload: dict) -> Optional[int]:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


@router.get("/orgs/{org_id}/performance-rules")
async def get_rules(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("sharing_rules.read")),
):
    """Get both commission types for an org (US1)."""
    result = await performance_service.get_rules_for_org(db, org_id)
    return _build_response(0, "success", result)


@router.put("/orgs/{org_id}/performance-rules/{rule_type}")
async def save_rule(
    org_id: int,
    rule_type: str,
    body: PerformanceRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("sharing_rules.write")),
):
    """Save a commission type's tier ladder (US2/US3)."""
    result = await performance_service.save_rule(
        db, org_id, rule_type, body, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.post("/orgs/{org_id}/performance-rules/{rule_type}/apply-to-descendants")
async def apply_to_descendants(
    org_id: int,
    rule_type: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("sharing_rules.write")),
):
    """One-click copy the org's rule to all descendant orgs."""
    result = await performance_service.apply_rule_to_descendants(
        db, org_id, rule_type, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.get("/orgs/{org_id}/performance-rules/history")
async def get_history(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("sharing_rules.read")),
):
    """Get change history for an org's rules (FR-007)."""
    result = await performance_service.get_history(db, org_id)
    return _build_response(0, "success", result)


@router.get("/orgs/{org_id}/performance-rules/preview")
async def preview(
    org_id: int,
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("sharing_rules.read")),
):
    """Real-time commission preview for an org (FR-013), not persisted."""
    result = await commission_service.preview_org_commission(db, org_id, period)
    return _build_response(0, "success", result)


@router.get("/commission-results")
async def list_results(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    orgId: Optional[str] = Query(None, description="组织 ID，按子树过滤"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("sharing_rules.read")),
):
    """Monthly commission results (FR-013/SC-009)."""
    org_id_int = None
    if orgId:
        try:
            org_id_int = int(orgId)
        except (ValueError, TypeError):
            org_id_int = None
    result = await commission_service.list_results(
        db, period, org_id=org_id_int, page=page, page_size=pageSize
    )
    return _build_response(0, "success", result)
