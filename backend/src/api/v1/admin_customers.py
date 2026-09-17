"""Admin customer management endpoints (US1-US4).

All endpoints require admin auth; read operations require ``customers.read``,
write operations require ``customers.write``.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...schemas.customer_admin import (
    CustomerCreateRequest,
    CustomerTransferRequest,
    CustomerUpdateRequest,
)
from ...services import customer_admin_service

router = APIRouter(prefix="/admin/customers", tags=["admin-customers"])


def _operator_id(payload: dict) -> Optional[int]:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


@router.get("")
async def list_customers(
    orgId: Optional[str] = Query(None, description="组织 ID；留空时返回无归属待绑定客户池"),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("customers.read")),
):
    """List customers in an org's subtree (FR-003)."""
    if orgId is None:
        result = await customer_admin_service.list_unassigned_customers(
            db, status=status, keyword=keyword, page=page, page_size=pageSize
        )
    else:
        try:
            org_id_int = int(orgId)
        except (ValueError, TypeError):
            raise BadRequestException(message="无效的组织 ID")
        result = await customer_admin_service.list_customers_by_org(
            db, org_id_int, status=status, keyword=keyword, page=page, page_size=pageSize
        )
    return _build_response(0, "success", result)


@router.get("/export")
async def export_customers(
    org_id: str = Query(
        ..., alias="orgId", description="组织 ID，导出该组织及全部下级组织客户"
    ),
    start_date: date = Query(..., alias="startDate", description="客户创建日期起始值"),
    end_date: date = Query(..., alias="endDate", description="客户创建日期结束值"),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("customers.read")),
):
    """Export a creation-date-scoped, masked customer list as an Excel-friendly CSV."""
    if start_date > end_date:
        raise BadRequestException(message="开始日期不能晚于结束日期")
    try:
        org_id_int = int(org_id)
    except (ValueError, TypeError):
        raise BadRequestException(message="无效的组织 ID")

    content = await customer_admin_service.export_customers_csv(
        db,
        org_id_int,
        start_date=start_date,
        end_date=end_date,
        status=status,
        keyword=keyword,
    )
    filename = f"customers_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("")
async def create_customer(
    body: CustomerCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("customers.write")),
):
    """Manually create a customer and attempt hospital binding match (FR-005/FR-008)."""
    result = await customer_admin_service.create_manual_customer(
        db, body, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.get("/{customer_id}")
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("customers.read")),
):
    """Get customer detail with masked sensitive fields (FR-009)."""
    result = await customer_admin_service.get_customer_detail(db, customer_id)
    return _build_response(0, "success", result)


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: int,
    body: CustomerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("customers.write")),
):
    """Update customer profile; sensitive fields require changeReason (FR-010)."""
    result = await customer_admin_service.update_customer_profile(
        db, customer_id, body, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.post("/{customer_id}/transfer")
async def transfer_customer(
    customer_id: int,
    body: CustomerTransferRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("customers.write")),
):
    """Reassign a customer's promoter with a full audit record (FR-011/FR-012)."""
    result = await customer_admin_service.transfer_customer(
        db, customer_id, body, operator_id=_operator_id(admin)
    )
    return _build_response(0, "success", result)


@router.get("/{customer_id}/change-logs")
async def get_change_logs(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("customers.read")),
):
    """Get a customer's promoter change history (FR-012)."""
    result = await customer_admin_service.get_change_logs(db, customer_id)
    return _build_response(0, "success", result)
