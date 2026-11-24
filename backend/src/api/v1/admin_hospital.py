"""Administrator statistics for internet-hospital visit intent events."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db, require_permission
from ...core.error_handler import _build_response
from ...models.audit import AuditLog
from ...services import hospital_stats_service

router = APIRouter(prefix="/admin/hospital", tags=["admin-hospital"])


@router.get("/stats", operation_id="getHospitalStats")
async def stats(
    from_time: str | None = Query(None, alias="from", max_length=10),
    to_time: str | None = Query(None, alias="to", max_length=10),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    payload: dict = Depends(require_permission("hospital.stats.read")),
    db: AsyncSession = Depends(get_db),
):
    from_date, to_date = hospital_stats_service.parse_range(from_time, to_time)
    result = await hospital_stats_service.get_stats(
        db,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    db.add(
        AuditLog(
            user_id=None,
            action="hospital_stats_read",
            entity_type="hospital_visit_event",
            entity_id=None,
            detail={
                "adminAccountId": str(payload.get("sub") or ""),
                "from": result["range"]["from"],
                "to": result["range"]["to"],
                "page": page,
            },
        )
    )
    await db.commit()
    return JSONResponse(
        _build_response(0, "success", result),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/stats/export", operation_id="exportHospitalStats")
async def export_stats(
    from_time: str | None = Query(None, alias="from", max_length=10),
    to_time: str | None = Query(None, alias="to", max_length=10),
    payload: dict = Depends(require_permission("hospital.stats.read")),
    db: AsyncSession = Depends(get_db),
):
    from_date, to_date = hospital_stats_service.parse_range(from_time, to_time)
    content, row_count = await hospital_stats_service.export_users_xlsx(
        db, from_date=from_date, to_date=to_date
    )
    db.add(
        AuditLog(
            user_id=None,
            action="hospital_stats_export",
            entity_type="hospital_visit_event",
            entity_id=None,
            detail={
                "adminAccountId": str(payload.get("sub") or ""),
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "rowCount": row_count,
            },
        )
    )
    await db.commit()
    filename = f"hospital_stats_{from_date.isoformat()}_{to_date.isoformat()}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
