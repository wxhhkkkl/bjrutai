"""Read-only admin projection for independent mall consumption evidence."""

import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_admin_user, get_db, require_permission
from ...core.error_handler import _build_response
from ...core.exceptions import BadRequestException
from ...models.mall_consumption import MallConsumption
from ...api.mall_deps import MallActor, require_mall_admin
from ...schemas.mall_attribution import AttributionConfirm
from ...services.mall_attribution_service import attribute_mall_consumption

router = APIRouter(prefix="/admin/mall/consumptions", tags=["admin-mall-consumptions"])


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        paid_at = datetime.fromisoformat(payload["paidAt"])
        source_id = int(payload["id"])
        if paid_at.tzinfo is not None:
            paid_at = paid_at.astimezone(timezone.utc).replace(tzinfo=None)
        if source_id <= 0:
            raise ValueError
        return paid_at, source_id
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        raise BadRequestException(message="cursor无效") from exc


def _encode_cursor(source: MallConsumption) -> str:
    payload = json.dumps(
        {"paidAt": source.paid_at.isoformat(timespec="microseconds"), "id": source.id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _serialize(source: MallConsumption) -> dict:
    occurred_at = source.paid_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    else:
        occurred_at = occurred_at.astimezone(timezone.utc)
    return {
        "id": str(source.id),
        "sourceType": "mall",
        "sourceRecordId": str(source.id),
        "customerId": str(source.customer_id) if source.customer_id else None,
        "distributorId": (
            str(source.attributed_distributor_id) if source.attributed_distributor_id else None
        ),
        "businessPeriod": source.business_period,
        "occurredAt": occurred_at.isoformat().replace("+00:00", "Z"),
        "originalAmountCent": source.original_goods_cent,
        "refundAmountCent": source.successful_goods_refund_cent,
        "performanceBaseCent": source.performance_base_cent,
        "status": source.status,
        "sourceVersion": source.source_version,
        "orderId": str(source.order_id),
    }


@router.get("", operation_id="listAdminMallConsumptions")
async def list_mall_consumptions(
    response: Response,
    cursor: str | None = Query(None, max_length=2048),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(get_admin_user),
    _perm: dict = Depends(require_permission("contributions.read")),
):
    """List assigned and unassigned mall sources without order address details."""
    response.headers["Cache-Control"] = "no-store"
    filters = []
    cursor_key = _decode_cursor(cursor) if cursor else None
    if cursor_key:
        paid_at, source_id = cursor_key
        filters.append(
            or_(
                MallConsumption.paid_at < paid_at,
                and_(MallConsumption.paid_at == paid_at, MallConsumption.id < source_id),
            )
        )

    total = int(await db.scalar(select(func.count(MallConsumption.id))) or 0)
    rows = (
        (
            await db.execute(
                select(MallConsumption)
                .where(*filters)
                .order_by(MallConsumption.paid_at.desc(), MallConsumption.id.desc())
                .limit(page_size + 1)
            )
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > page_size
    page = rows[:page_size]
    return _build_response(
        0,
        "success",
        {
            "items": [_serialize(source) for source in page],
            "nextCursor": _encode_cursor(page[-1]) if has_more and page else None,
            "total": total,
        },
    )


@router.post("/{consumptionId}/attribution", operation_id="attributeMallConsumption")
async def confirm_consumption_attribution(
    body: AttributionConfirm,
    consumption_id: int = Path(alias="consumptionId", gt=0),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    actor: MallActor = Depends(require_mall_admin("mall.attribution.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await attribute_mall_consumption(
            db,
            actor=actor,
            consumption_id=consumption_id,
            expected_version=body.expected_version,
            distributor_id=int(body.distributor_id),
            customer_id=int(body.customer_id) if body.customer_id else None,
            evidence_file_ids=[int(file_id) for file_id in body.evidence_file_ids],
            reason=body.reason,
            idempotency_key=idempotency_key,
        )
        data = _serialize(result.source)
        data["performanceHandling"] = result.handling
        await db.commit()
        return JSONResponse(
            _build_response(0, "success", data), headers={"Cache-Control": "no-store"}
        )
    except Exception:
        await db.rollback()
        raise
