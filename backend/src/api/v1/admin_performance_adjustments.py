"""Live-authorized adjustment review, evidence, and net-entitlement routes."""

import base64

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_db
from ...api.mall_deps import MallActor, require_mall_admin
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException, ConflictException
from ...schemas.performance_adjustment import (
    PerformanceAdjustmentReconcileRequest,
    PerformanceAdjustmentRejectRequest,
    PerformanceAdjustmentReviewRequest,
)
from ...services.mall_audit_service import record_mall_admin_audit
from ...services.mall_command_service import complete_mall_command, reserve_mall_command
from ...services.performance_adjustment_service import (
    get_performance_adjustment,
    list_performance_adjustments,
    reconcile_performance_adjustment,
    reject_performance_adjustment,
    review_performance_adjustment,
)

router = APIRouter(prefix="/admin/performance/adjustments", tags=["admin-performance-adjustments"])


def _encode_cursor(identity: int) -> str:
    return base64.urlsafe_b64encode(str(identity).encode("ascii")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = int(base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii"))
        if value <= 0:
            raise ValueError
        return value
    except (ValueError, UnicodeError) as exc:
        raise BadRequestException(message="cursor无效") from exc


def _response(data):
    return JSONResponse(
        _build_response(0, "success", data),
        headers={"Cache-Control": "no-store"},
    )


async def _replay_adjustment(db: AsyncSession, intent, adjustment_id: int):
    if intent.command.entity_type != "performance_adjustment":
        raise ConflictException(message="幂等请求未完成")
    if intent.command.entity_id != adjustment_id:
        raise ConflictException(message="幂等请求关联的绩效差额不一致")
    return await get_performance_adjustment(db, adjustment_id)


@router.get("", operation_id="listPerformanceAdjustments")
async def list_adjustments(
    response: Response,
    cursor: str | None = Query(None, max_length=64),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _actor: MallActor = Depends(require_mall_admin("sharing_rules.read")),
):
    page = await list_performance_adjustments(
        db, cursor_id=_decode_cursor(cursor), page_size=page_size
    )
    next_cursor_id = page.pop("nextCursorId")
    page["nextCursor"] = _encode_cursor(next_cursor_id) if next_cursor_id else None
    response.headers["Cache-Control"] = "no-store"
    return _response(page)


@router.get("/{adjustmentId}", operation_id="getPerformanceAdjustment")
async def get_adjustment(
    response: Response,
    adjustment_id: int = Path(alias="adjustmentId", gt=0),
    db: AsyncSession = Depends(get_db),
    _actor: MallActor = Depends(require_mall_admin("sharing_rules.read")),
):
    response.headers["Cache-Control"] = "no-store"
    return _response(await get_performance_adjustment(db, adjustment_id))


@router.post("/{adjustmentId}/review", operation_id="reviewPerformanceAdjustment")
async def review_adjustment(
    body: PerformanceAdjustmentReviewRequest,
    adjustment_id: int = Path(alias="adjustmentId", gt=0),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(require_mall_admin("performance.settle")),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = body.model_dump(mode="json", by_alias=True)
        intent = await reserve_mall_command(
            db,
            actor=actor,
            action="reviewPerformanceAdjustment",
            key=idempotency_key,
            payload={"adjustmentId": str(adjustment_id), **payload},
        )
        if intent.created:
            row = await review_performance_adjustment(
                db,
                adjustment_id=adjustment_id,
                expected_version=body.expected_version,
                admin_id=actor.actor_id,
            )
            await complete_mall_command(
                db,
                intent,
                entity_type="performance_adjustment",
                entity_id=row.id,
            )
            await record_mall_admin_audit(
                db,
                actor=actor,
                action="performance_adjustment_reviewed",
                entity_type="performance_adjustment",
                entity_id=str(row.id),
                detail={
                    "expectedVersion": body.expected_version,
                    "version": row.version,
                    "deltaCent": row.delta_cent,
                    "originEvidenceId": str(row.evidence_id),
                },
            )
            result = await get_performance_adjustment(db, row.id)
        else:
            result = await _replay_adjustment(db, intent, adjustment_id)
        await db.commit()
        return _response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{adjustmentId}/reject", operation_id="rejectPerformanceAdjustment")
async def reject_adjustment(
    body: PerformanceAdjustmentRejectRequest,
    adjustment_id: int = Path(alias="adjustmentId", gt=0),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(require_mall_admin("performance.settle")),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = body.model_dump(mode="json", by_alias=True)
        intent = await reserve_mall_command(
            db,
            actor=actor,
            action="rejectPerformanceAdjustment",
            key=idempotency_key,
            payload={"adjustmentId": str(adjustment_id), **payload},
        )
        if intent.created:
            row = await reject_performance_adjustment(
                db,
                adjustment_id=adjustment_id,
                expected_version=body.expected_version,
                admin_id=actor.actor_id,
                reason=body.reason,
            )
            await complete_mall_command(
                db,
                intent,
                entity_type="performance_adjustment",
                entity_id=row.id,
            )
            await record_mall_admin_audit(
                db,
                actor=actor,
                action="performance_adjustment_rejected",
                entity_type="performance_adjustment",
                entity_id=str(row.id),
                detail={
                    "expectedVersion": body.expected_version,
                    "version": row.version,
                    "reason": body.reason,
                },
            )
            result = await get_performance_adjustment(db, row.id)
        else:
            result = await _replay_adjustment(db, intent, adjustment_id)
        await db.commit()
        return _response(result)
    except Exception:
        await db.rollback()
        raise


@router.post("/{adjustmentId}/reconcile", operation_id="reconcilePerformanceAdjustment")
async def reconcile_adjustment(
    body: PerformanceAdjustmentReconcileRequest,
    adjustment_id: int = Path(alias="adjustmentId", gt=0),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(require_mall_admin("performance.settle")),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = body.model_dump(mode="json", by_alias=True)
        intent = await reserve_mall_command(
            db,
            actor=actor,
            action="reconcilePerformanceAdjustment",
            key=idempotency_key,
            payload={"adjustmentId": str(adjustment_id), **payload},
        )
        if intent.created:
            row, previous_status, current_status = await reconcile_performance_adjustment(
                db,
                adjustment_id=adjustment_id,
                expected_version=body.expected_version,
                evidence_file_ids=[int(value) for value in body.evidence_file_ids],
                admin_id=actor.actor_id,
                reason=body.reason,
            )
            await complete_mall_command(
                db,
                intent,
                entity_type="performance_adjustment",
                entity_id=row.id,
            )
            await record_mall_admin_audit(
                db,
                actor=actor,
                action="performance_adjustment_reconciled",
                entity_type="performance_adjustment",
                entity_id=str(row.id),
                detail={
                    "expectedVersion": body.expected_version,
                    "version": row.version,
                    "previousStatus": previous_status,
                    "status": current_status,
                    "evidenceFileIds": row.evidence_file_ids,
                    "reason": body.reason,
                },
            )
            result = await get_performance_adjustment(db, row.id)
        else:
            result = await _replay_adjustment(db, intent, adjustment_id)
        await db.commit()
        return _response(result)
    except Exception:
        await db.rollback()
        raise
