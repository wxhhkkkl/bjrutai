"""Admin contribution dashboard endpoints (US1-US5).

All endpoints require admin auth + ``contributions.read``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...services import contribution_dashboard_service
from ...core.exceptions import BadRequestException
from ...models.user import AdminAccount
from ...schemas.admin_contribution import ManualConsumptionCreateRequest
from ...services import manual_consumption_service

router = APIRouter(prefix="/admin/contributions", tags=["admin-contributions"])


def _parse_org(org_id: Optional[str]) -> Optional[int]:
    if not org_id:
        return None
    try:
        return int(org_id)
    except (ValueError, TypeError):
        return None


@router.get("/customers")
async def search_customers(
    keyword: str = Query(..., min_length=1, max_length=100),
    pageSize: int = Query(20, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("contributions.write")),
):
    result = await manual_consumption_service.search_eligible_customers(
        db, keyword=keyword, page_size=pageSize
    )
    return _build_response(0, "success", result)


@router.post("/manual")
async def create_manual_consumption(
    body: ManualConsumptionCreateRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("contributions.write")),
):
    if not idempotency_key or len(idempotency_key) > 128:
        raise BadRequestException(message="缺少或无效的 Idempotency-Key")
    admin_id = int(admin["sub"])
    admin_username = (
        await db.execute(select(AdminAccount.username).where(AdminAccount.id == admin_id))
    ).scalar_one_or_none()
    result = await manual_consumption_service.create_manual_consumption(
        db,
        data=body,
        admin_id=admin_id,
        admin_username=admin_username,
        idempotency_key=idempotency_key,
        ip_address=request.client.host if request.client else None,
    )
    return _build_response(0, "消费录入成功", result)


@router.get("/dashboard")
async def get_dashboard(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="统计月份 YYYY-MM"),
    period: str = Query("12m", description="趋势月数，如 6m/12m/3m"),
    orgId: Optional[str] = Query(None, description="组织 ID，过滤其子树"),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("contributions.read")),
):
    """Stats + monthly trend + latest 30 details (US1/US5)."""
    result = await contribution_dashboard_service.get_dashboard(
        db, month, period, org_id=_parse_org(orgId)
    )
    return _build_response(0, "success", result)


@router.get("/rankings/orgs")
async def org_ranking(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    orgId: Optional[str] = Query(None, description="筛选某组织及子树"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("contributions.read")),
):
    """Org monthly performance ranking (US2)."""
    result = await contribution_dashboard_service.org_ranking(
        db, month, org_id=_parse_org(orgId), page=page, page_size=pageSize
    )
    return _build_response(0, "success", result)


@router.get("/rankings/persons")
async def persons_ranking(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    orgId: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("contributions.read")),
):
    """Person monthly performance ranking (US3)."""
    result = await contribution_dashboard_service.persons_ranking(
        db, month, org_id=_parse_org(orgId), page=page, page_size=pageSize
    )
    return _build_response(0, "success", result)


@router.get("/rankings/bindings")
async def bindings_ranking(
    scope: str = Query(..., pattern=r"^(person|org)$"),
    orgId: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("contributions.read")),
):
    """Bound-customer-count ranking (person or org scope, US4)."""
    result = await contribution_dashboard_service.bindings_ranking(
        db, scope, org_id=_parse_org(orgId), page=page, page_size=pageSize
    )
    return _build_response(0, "success", result)
