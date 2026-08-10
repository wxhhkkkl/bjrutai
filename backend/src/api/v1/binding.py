"""Binding API endpoints.

Endpoints:
- GET   /promoters/selectable
- POST  /binding-requests            (Idempotency-Key required)
- GET   /binding-requests
- GET   /binding-requests/{id}
- POST  /binding-requests/{id}/retry  (Idempotency-Key required)
- PUT   /binding-requests/{id}/customer-info  (Idempotency-Key required)
- GET   /binding-summary
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...schemas.binding import (
    BindingRequestCreate,
    CustomerInfoUpdateRequest,
    UnbindRequest,
    TransferRequest,
)
from ...models.notification import Notification, NotificationCategory
from ...services.binding_service import get_binding_service

router = APIRouter(tags=["binding"])


def _ok(data=None) -> dict:
    return _build_response(0, "success", data)


# =============================================================================
# GET /promoters/selectable
# =============================================================================


@router.get("/promoters/selectable")
async def get_selectable_promoters(
    keyword: str = Query(None, max_length=100),
    cursor: str = Query(None, max_length=256),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    """Return promoters available for binding, filtered by the current user's scope."""
    user_id = int(payload["sub"])
    svc = get_binding_service()
    result = await svc.get_selectable_promoters(
        db,
        keyword=keyword,
        cursor=cursor,
        page_size=limit,
        doctor_user_id=user_id,
    )
    return _ok(result)


# =============================================================================
# POST /binding-requests
# =============================================================================


@router.post("/binding-requests")
async def submit_binding_request(
    data: BindingRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    """Submit a new customer binding request. Idempotency-Key header REQUIRED."""
    if not idempotency_key:
        raise BadRequestException(message="Idempotency-Key header is required")

    user_id = int(payload["sub"])
    svc = get_binding_service()

    req_data = data.model_dump(exclude_none=False)
    result = await svc.submit_binding_request(
        db,
        data=req_data,
        submitted_by=user_id,
        idempotency_key=idempotency_key,
    )

    # Keep the initiator and the selected promoter informed of the resulting
    # binding state.  Notification delivery is best-effort and is committed
    # together with the binding request so the two records cannot diverge.
    status = str(result.get("status") or "processing")
    status_label = str(result.get("statusLabel") or "处理中")
    target_filter = "bound" if status == "bound" else "matching" if status == "matching" else "processing"
    customer_info = data.customerInfo.model_dump() if data.customerInfo else {}
    customer_name = str(customer_info.get("name") or "客户")
    target = f"/pages/binding-records/index?filter={target_filter}"
    db.add(Notification(
        user_id=user_id,
        category=NotificationCategory.BINDING,
        title="客户绑定状态更新",
        summary=f"{customer_name}的绑定状态：{status_label}",
        target=target,
    ))
    promoter_user_id = str(result.get("promoterId") or "")
    if promoter_user_id and promoter_user_id != str(user_id):
        db.add(Notification(
            user_id=int(promoter_user_id),
            category=NotificationCategory.BINDING,
            title="收到新的客户绑定请求",
            summary=f"{customer_name}的绑定状态：{status_label}",
            target=target,
        ))
    await db.commit()
    return _ok(result)


# =============================================================================
# GET /binding-requests
# =============================================================================


@router.get("/binding-requests")
async def list_binding_requests(
    status: str = Query(None),
    role: str = Query("initiator", pattern="^(initiator|target)$"),
    cursor: str = Query(None, max_length=256),
    limit: int = Query(20, ge=1, le=100),
    submittedByMe: bool = Query(False, alias="submittedByMe"),
    keyword: str = Query(None, max_length=100),
    sortBy: str = Query("created_at"),
    sortOrder: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    """List binding requests with filters."""
    user_id = int(payload["sub"])
    svc = get_binding_service()

    sub_by_me = user_id if submittedByMe else None
    result = await svc.get_binding_requests(
        db,
        status=status,
        role=role,
        cursor=cursor,
        page_size=limit,
        submitted_by_me=sub_by_me,
        keyword=keyword,
        sort_by=sortBy,
        sort_order=sortOrder,
    )
    return _ok(result)


# =============================================================================
# GET /binding-requests/{id}
# =============================================================================


@router.get("/binding-requests/{binding_request_id}")
async def get_binding_detail(
    binding_request_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    """Get full detail for a binding request including audit events."""
    svc = get_binding_service()
    result = await svc.get_binding_detail(db, binding_request_id)
    return _ok(result)


# =============================================================================
# POST /binding-requests/{id}/retry
# =============================================================================


@router.post("/binding-requests/{binding_request_id}/retry")
async def retry_binding_request(
    binding_request_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    """Retry a failed binding request."""
    if not idempotency_key:
        raise BadRequestException(message="Idempotency-Key header is required")

    svc = get_binding_service()
    result = await svc.retry_binding(
        db,
        binding_request_id,
        idempotency_key=idempotency_key,
    )
    await db.commit()
    return _ok(result)


# =============================================================================
# PUT /binding-requests/{id}/customer-info
# =============================================================================


@router.put("/binding-requests/{binding_request_id}/customer-info")
async def update_customer_info(
    binding_request_id: int,
    data: CustomerInfoUpdateRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    """Update customer info on a binding request."""
    if not idempotency_key:
        raise BadRequestException(message="Idempotency-Key header is required")

    svc = get_binding_service()
    result = await svc.update_customer_info(
        db,
        binding_request_id,
        data=data.model_dump(exclude_none=False),
    )
    await db.commit()
    return _ok(result)


# =============================================================================
# GET /binding-summary
# =============================================================================


@router.get("/binding-summary")
async def get_binding_summary(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    """Get binding summary counts."""
    user_id = int(payload["sub"])
    svc = get_binding_service()
    result = await svc.get_binding_summary(db, user_id=user_id)
    return _ok(result)
