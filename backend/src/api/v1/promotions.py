"""Promotion code endpoints (US10).

Promoter-facing endpoints for managing promotion codes, statistics, and posters.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.error_handler import _build_response
from ..deps import get_current_user
from ...services import promotion_service

router = APIRouter(tags=["promotions"])


# ──────────────────────────────────────────────────────────────────
# GET /promotion-code
# ──────────────────────────────────────────────────────────────────
@router.get("/promotion-code")
async def get_promotion_code(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's promotion code.

    Generates a new promotion code if none exists. Requires an approved
    qualification.
    """
    user_id = int(current_user["sub"])
    result = await promotion_service.get_promotion_code(db, user_id)
    return _build_response(0, "success", result)


# ──────────────────────────────────────────────────────────────────
# POST /promotion-code/refresh
# ──────────────────────────────────────────────────────────────────
@router.post("/promotion-code/refresh")
async def refresh_promotion_code(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Refresh the promotion code by invalidating the current one and generating a new one.

    Requires an approved qualification.
    """
    user_id = int(current_user["sub"])
    result = await promotion_service.refresh_code(db, user_id)
    return _build_response(0, "success", result)


# ──────────────────────────────────────────────────────────────────
# GET /promotion-code/statistics
# ──────────────────────────────────────────────────────────────────
@router.get("/promotion-code/statistics")
async def get_promotion_statistics(
    period: str = Query("30d", description="Time period: 7d, 30d, 90d"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get promotion code statistics (scan count, lead count, bind count, conversion rate).

    Requires an approved qualification.
    """
    user_id = int(current_user["sub"])
    result = await promotion_service.get_statistics(db, user_id, period=period)
    return _build_response(0, "success", result)


# ──────────────────────────────────────────────────────────────────
# GET /promotion-code/poster
# ──────────────────────────────────────────────────────────────────
@router.get("/promotion-code/poster")
async def get_promotion_poster(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the promotion poster image URL and share info.

    Requires an approved qualification and an active promotion code.
    """
    user_id = int(current_user["sub"])
    result = await promotion_service.get_poster(db, user_id)
    return _build_response(0, "success", result)
