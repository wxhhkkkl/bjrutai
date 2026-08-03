"""Admin customer management endpoints (US1-US4).

All endpoints require admin auth; read operations require ``customers.read``,
write operations require ``customers.write``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
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
    orgId: str = Query(..., description="组织 ID，返回该组织及全部下级组织范围客户"),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("customers.read")),
):
    """List customers in an org's subtree (FR-003)."""
    try:
        org_id_int = int(orgId)
    except (ValueError, TypeError):
        raise BadRequestException(message="无效的组织 ID")
    result = await customer_admin_service.list_customers_by_org(
        db, org_id_int, status=status, keyword=keyword, page=page, page_size=pageSize
    )
    return _build_response(0, "success", result)


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
