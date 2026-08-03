"""Admin management endpoints.

All endpoints require admin authentication.

Hierarchy endpoints were removed with the org-personnel-management migration
(T065): the hierarchy feature is replaced by org management, and its tables are
deprecated (migration 004). Only admin binding endpoints remain here.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ..deps import get_admin_user
from ...schemas.binding import UnbindRequest, TransferRequest
from ...services.binding_service import get_binding_service

admin_bindings_router = APIRouter(prefix="/admin/bindings", tags=["admin-bindings"])


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
