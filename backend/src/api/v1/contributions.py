"""Contribution view API endpoints (US6).

GET /api/v1/contributions/overview  – monthly overview
GET /api/v1/contributions/trend     – monthly trend
GET /api/v1/contributions/composition – category breakdown
GET /api/v1/contributions           – cursor-paginated list
GET /api/v1/contributions/{id}      – full detail
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...services.contribution_query_service import ContributionQueryService

router = APIRouter(prefix="/contributions", tags=["contributions"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────
# GET /contributions/overview
# ──────────────────────────────────────────────────────────────────
@router.get("/overview")
async def get_overview(
    month: str = Query(..., description="Month in YYYY-MM format (e.g. 2026-07)"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get contribution overview for the authenticated promoter."""
    user_id = int(payload["sub"])
    svc = ContributionQueryService()
    result = await svc.get_overview(db, user_id, month)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# GET /contributions/trend
# ──────────────────────────────────────────────────────────────────
@router.get("/trend")
async def get_trend(
    period: str = Query("6m", description="Number of months (e.g. 6m, 12m, 3m)"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get monthly contribution trend for the last N months."""
    user_id = int(payload["sub"])
    svc = ContributionQueryService()
    result = await svc.get_trend(db, user_id, period)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# GET /contributions/composition
# ──────────────────────────────────────────────────────────────────
@router.get("/composition")
async def get_composition(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get contribution composition breakdown by category for a month."""
    user_id = int(payload["sub"])
    svc = ContributionQueryService()
    result = await svc.get_composition(db, user_id, month)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# GET /contributions (list)
# ──────────────────────────────────────────────────────────────────
@router.get("")
async def list_contributions(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    status: Optional[str] = Query(None, description="Filter by status (pending, settled, etc.)"),
    category: Optional[str] = Query(None, description="Filter by category (bill, binding, etc.)"),
    cursor: Optional[str] = Query(None, description="Pagination cursor (last ID from previous page)"),
    pageSize: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """List contribution records with cursor pagination and optional filters."""
    user_id = int(payload["sub"])
    svc = ContributionQueryService()
    result = await svc.list_details(
        db, user_id,
        month=month,
        status=status,
        category=category,
        cursor=cursor,
        page_size=pageSize,
    )
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# GET /contributions/{id}
# ──────────────────────────────────────────────────────────────────
@router.get("/{contribution_id}")
async def get_detail(
    contribution_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get full detail of a contribution record including calculation info."""
    svc = ContributionQueryService()
    result = await svc.get_detail(db, contribution_id)
    return _ok(result)
