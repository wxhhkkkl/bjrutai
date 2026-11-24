"""Public internet-hospital visit intent events.

The endpoint accepts guests and signed-in mini program users. A valid user
token is recorded for attribution; invalid or missing tokens are anonymous.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db, get_optional_user
from ...core.error_handler import _build_response
from ...schemas.hospital_stats import HospitalEventIn
from ...services import hospital_stats_service

router = APIRouter(prefix="/hospital", tags=["hospital"])


@router.post("/events", operation_id="recordHospitalVisitEvent")
async def record_event(
    body: HospitalEventIn,
    payload: dict | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = None
    if payload and payload.get("user_type") != "admin":
        candidate = int(payload.get("sub") or 0)
        if candidate and await hospital_stats_service.user_exists(db, candidate):
            user_id = candidate
    await hospital_stats_service.record_event(
        db,
        user_id=user_id,
        event_type=body.event,
        source=body.source,
    )
    await db.commit()
    return _build_response(0, "success", {"recorded": True})
