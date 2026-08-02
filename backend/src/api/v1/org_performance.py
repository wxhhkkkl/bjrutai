"""Org performance endpoints for the mini-program (US5).

GET /api/v1/org/performance — org admin's subtree contribution view.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...core.error_handler import _build_response
from ...services import org_performance_service

router = APIRouter(prefix="/org", tags=["org"])


@router.get("/performance")
async def get_org_performance(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Return org performance for the authenticated org admin."""
    user_id = int(payload["sub"])
    result = await org_performance_service.get_org_performance(db, user_id, month)
    return _build_response(0, "success", result)
