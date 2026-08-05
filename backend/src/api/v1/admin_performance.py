"""Admin performance calculation endpoints (008, US1/US2/US4).

- Estimates (real-time)            : sharing_rules.read
- Settlement review/reject/recompute/export : performance.settle (FR-014)
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...models.organization import Organization
from ...services import commission_service, settlement_service

router = APIRouter(prefix="/admin/performance", tags=["admin-performance"])


class RejectRequest(BaseModel):
    reason: str


async def _root_org_id(db: AsyncSession) -> Optional[int]:
    row = (
        await db.execute(
            select(Organization)
            .where(Organization.parent_id.is_(None))
            .order_by(Organization.id)
            .limit(1)
        )
    ).scalars().first()
    return row.id if row else None


@router.get("/estimates")
async def estimates(
    period: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    orgId: Optional[str] = Query(None, description="组织 ID，缺省用根组织"),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("sharing_rules.read")),
):
    """Real-time per-person estimates for an org (US1, SC-002). Not persisted."""
    org_id = None
    if orgId:
        try:
            org_id = int(orgId)
        except (ValueError, TypeError):
            org_id = None
    if org_id is None:
        org_id = await _root_org_id(db)

    if org_id is None:
        return _build_response(0, "success", {
            "orgId": None,
            "period": period,
            "intraOrg": [],
            "orgManagement": [],
            "unconfigured": ["intra_org", "org_management"],
        })

    result = await commission_service.preview_org_commission(db, org_id, period)
    return _build_response(0, "success", result)


@router.get("/settlements")
async def settlements(
    period: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("sharing_rules.read")),
):
    """Settlement batch status per period (US2)."""
    result = await settlement_service.get_settlements(db, period)
    return _build_response(0, "success", result)


@router.post("/settlements/{period}/review")
async def review_settlement(
    period: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("performance.settle")),
):
    """Confirm a month's settlement (freezes it, FR-006)."""
    result = await settlement_service.review_settlement(
        db, period, operator_id=int(admin["sub"])
    )
    return _build_response(0, "success", result)


@router.post("/settlements/{period}/reject")
async def reject_settlement(
    period: str,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("performance.settle")),
):
    """Reject a month's settlement with a reason (FR-013)."""
    result = await settlement_service.reject_settlement(
        db, period, operator_id=int(admin["sub"]), reason=body.reason
    )
    return _build_response(0, "success", result)


@router.post("/settlements/{period}/recompute")
async def recompute_settlement(
    period: str,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("performance.settle")),
):
    """Recompute a pending/rejected month (FR-008)."""
    result = await settlement_service.recompute_settlement(db, period)
    return _build_response(0, "success", result)


@router.get("/settlements/{period}/export")
async def export_settlement(
    period: str,
    orgId: Optional[str] = Query(None, description="组织 ID，缺省全部"),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("performance.settle")),
):
    """Export a month's results as CSV (FR-010 / SC-007)."""
    org_id = None
    if orgId:
        try:
            org_id = int(orgId)
        except (ValueError, TypeError):
            org_id = None
    csv_text = await commission_service.export_results_csv(db, period, org_id=org_id)
    filename = f"performance_{period}.csv"
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
