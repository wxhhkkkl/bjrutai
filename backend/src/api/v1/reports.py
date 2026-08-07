"""Reconciliation report API endpoints (US8).

POST /api/v1/reports/generate    – generate report
GET  /api/v1/reports             – list historical reports
GET  /api/v1/reports/{id}        – report detail
GET  /api/v1/reports/{id}/export – export Excel

Requires admin or finance role.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db, require_role
from ...core.exceptions import ForbiddenException
from ...schemas.report import ReportGenerateRequest
from ...services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _has_permission(payload: dict, key: str) -> bool:
    perms = payload.get("permissions") or []
    return key in perms


def _assert_settlement_read_permission(payload: dict) -> None:
    """Settlement report records require sharing_rules.read (FR-011)."""
    if not _has_permission(payload, "sharing_rules.read"):
        raise ForbiddenException(message="缺少权限: sharing_rules.read")


# ──────────────────────────────────────────────────────────────────
# POST /reports/generate
# ──────────────────────────────────────────────────────────────────
@router.post("/generate")
async def generate_report(
    body: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_role("admin", "finance")),
) -> dict:
    """Generate a multi-dimensional reconciliation report.

    Requires admin or finance role.
    """
    user_display = f"User {payload.get('sub', 'unknown')}"
    svc = ReportService()
    result = await svc.generate_report(
        db,
        start_date=body.startDate,
        end_date=body.endDate,
        dimensions=body.dimensions,
        user_display=user_display,
    )
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# GET /reports
# ──────────────────────────────────────────────────────────────────
@router.get("")
async def list_reports(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_role("admin", "finance")),
) -> dict:
    """List historical reconciliation reports.

    Settlement-source records are only visible to callers with
    ``sharing_rules.read`` (FR-011).
    """
    svc = ReportService()
    result = await svc.list_reports(db)
    if not _has_permission(payload, "sharing_rules.read"):
        result["items"] = [
            item for item in result["items"]
            if item.get("source") != "performance_settlement"
        ]
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# GET /reports/{id}
# ──────────────────────────────────────────────────────────────────
@router.get("/{report_id}")
async def get_report_detail(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_role("admin", "finance")),
) -> dict:
    """Get full detail of a reconciliation report.

    Settlement-source records require ``sharing_rules.read`` (FR-011).
    """
    svc = ReportService()
    result = await svc.get_detail(db, report_id)
    if result.get("source") == "performance_settlement":
        _assert_settlement_read_permission(payload)
    return _ok(result)


# ──────────────────────────────────────────────────────────────────
# GET /reports/{id}/export
# ──────────────────────────────────────────────────────────────────
@router.get("/{report_id}/export")
async def export_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_role("admin", "finance")),
):
    """Export a reconciliation report as an Excel (.xlsx) file.

    Settlement-source records require ``sharing_rules.read`` (FR-011/FR-012).
    Returns a file stream with proper Content-Type header.
    """
    svc = ReportService()
    detail = await svc.get_detail(db, report_id)
    if detail.get("source") == "performance_settlement":
        _assert_settlement_read_permission(payload)
    excel_bytes = await svc.export_excel(db, report_id)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="report-{report_id}.xlsx"',
        },
    )
