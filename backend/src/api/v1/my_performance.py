"""Mini-program performance endpoints (008, US3).

Promoter: GET /my/performance/commission (own estimate + confirmed months).
Org admin: GET /org/performance/commission (managed org subtree view).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.error_handler import _build_response
from ...services import performance_view_service

router = APIRouter(tags=["performance-view"])


@router.get("/my/performance/commission")
async def my_performance_commission(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    """Promoter's own commission estimate + confirmed history (FR-009)."""
    result = await performance_view_service.my_commission(db, int(payload["sub"]), month)
    return _build_response(0, "success", result)


@router.get("/org/performance/commission")
async def org_performance_commission(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    """Org-admin's managed org commission view (FR-009)."""
    result = await performance_view_service.org_commission(db, int(payload["sub"]), month)
    return _build_response(0, "success", result)
