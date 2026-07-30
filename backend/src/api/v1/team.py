"""Team contribution API endpoints (US6).

GET /api/v1/team/contributions            – team summary
GET /api/v1/team/contributions/{promoterId} – drill-down (branch access verified)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...services.team_service import TeamService

router = APIRouter(prefix="/team", tags=["team"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────
# GET /team/contributions
# ──────────────────────────────────────────────────────────────────
@router.get("/contributions")
async def get_team_summary(
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get team contribution summary for the authenticated promoter.

    Only returns contribution points -- no monetary amounts.
    """
    user_id = int(payload["sub"])
    svc = TeamService()
    result = await svc.get_team_summary(db, user_id, month)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# GET /team/contributions/{promoterId}
# ──────────────────────────────────────────────────────────────────
@router.get("/contributions/{promoter_id}")
async def drill_down_team(
    promoter_id: int,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Drill down into a specific team member's team view.

    Requires the target promoter to be in the requester's branch (subtree).
    Returns 403 if unauthorized.
    """
    user_id = int(payload["sub"])
    svc = TeamService()
    result = await svc.drill_down(db, user_id, promoter_id, month)
    return _ok(result)
