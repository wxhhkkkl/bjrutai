"""Order-scoped logistics cache, shared query reservation and safe projections."""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..api.mall_deps import require_mall_admin_permission
from ..core.config import get_settings
from ..core.exceptions import ConflictException, NotFoundException
from ..integrations.kuaidi100_client import FakeKuaidi100Client, Kuaidi100Error
from ..models.mall_base import utc_now
from ..models.mall_operations import MallJob
from ..models.mall_trade import MallOrder, MallShipment
from ..schemas.mall_catalog import VersionAction
from ..tasks.mall_tasks import MallWorkItem
from .mall_admin_order_service import admin_order
from .mall_audit_service import record_mall_admin_audit
from .mall_command_service import complete_mall_command, reserve_mall_command
from .mall_job_service import enqueue_mall_job, locked_mall_lease
from .mall_order_service import audit_order, owned_order

QUERY_INTERVAL = timedelta(minutes=30)
MAX_EVENTS = 100
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[ -]?)?(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8})(?!\d)")
STATE_NAMES = {
    "0": "运输中",
    "1": "已揽收",
    "2": "物流异常",
    "3": "已签收",
    "4": "退签",
    "5": "派送中",
    "6": "退回中",
    "8": "清关中",
    "14": "拒签",
    "101": "已下单",
    "102": "待揽收",
    "103": "已揽收",
    "501": "已投柜或驿站",
}
SAFE_QUERY_ERRORS = {
    "no_record",
    "verification_failed",
    "permission_denied",
    "service_error",
    "config_required",
}


def _sanitize_text(value, *, limit=500):
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split())
    return PHONE_PATTERN.sub("[联系方式已隐藏]", normalized)[:limit]


def _parse_provider_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        pass
    try:
        parsed = datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
        return (
            parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
    except ValueError:
        return None


def _normalize_provider_result(result, *, source):
    state_code = result.get("state")
    state_code = str(state_code) if state_code is not None else None
    events = []
    for row in (result.get("data") or [])[:MAX_EVENTS]:
        if not isinstance(row, dict):
            continue
        state = row.get("statusCode", row.get("stateCode"))
        state = str(state) if state is not None else None
        state_name = _sanitize_text(row.get("status") or row.get("state"), limit=80) or None
        area_parts = [row.get(name) for name in ("province", "city", "district", "areaName")]
        area_name = _sanitize_text(" ".join(str(item) for item in area_parts if item), limit=100)
        description = _sanitize_text(
            row.get("context") or row.get("name") or row.get("description") or "物流节点更新"
        )
        time_text = _sanitize_text(
            row.get("ftime") or row.get("leaveTime") or row.get("time"), limit=64
        )
        occurred_at = _parse_provider_time(time_text)
        events.append(
            {
                "occurredAt": occurred_at.isoformat() + "Z" if occurred_at else None,
                "timeText": time_text or "时间待核实",
                "description": description or "物流节点更新",
                "stateCode": state,
                "stateName": state_name or STATE_NAMES.get(state),
                "areaName": area_name or None,
            }
        )
    return {
        "source": source,
        "stateCode": state_code,
        "stateName": STATE_NAMES.get(state_code),
        "events": events,
    }


async def _has_active_query(db, shipment):
    return bool(
        await db.scalar(
            select(MallJob.id)
            .where(
                MallJob.kind == "mall_logistics_query",
                MallJob.entity_type == "mall_shipment",
                MallJob.entity_id == shipment.id,
                MallJob.entity_version == shipment.version,
                MallJob.status.in_(("ready", "retry", "running")),
            )
            .limit(1)
        )
    )


async def _schedule_if_allowed(db, shipment, *, now=None):
    now = now or utc_now()
    if await _has_active_query(db, shipment):
        return False
    if shipment.logistics_next_query_at and shipment.logistics_next_query_at > now:
        return False
    key = f"mall-logistics:{shipment.id}:{shipment.version}:{int(now.timestamp())}"
    shipment.logistics_next_query_at = now + QUERY_INTERVAL
    shipment.logistics_status = (
        "stale" if (shipment.tracking_snapshot or {}).get("events") else "pending"
    )
    await enqueue_mall_job(
        db,
        kind="mall_logistics_query",
        entity_type="mall_shipment",
        entity_id=shipment.id,
        entity_version=shipment.version,
        dedupe_key=key,
        next_run_at=now,
    )
    await db.flush()
    return True


def _snapshot_view(order, shipment):
    data = shipment.tracking_snapshot or {}
    return {
        "orderId": str(order.id),
        "shipmentId": str(shipment.id),
        "shipmentVersion": shipment.version,
        "provider": "kuaidi100",
        "source": data.get("source"),
        "courierCode": shipment.courier_code,
        "trackingNo": shipment.tracking_no,
        "queryStatus": shipment.logistics_status,
        "stateCode": data.get("stateCode"),
        "stateName": data.get("stateName"),
        "events": data.get("events", []),
        "updatedAt": shipment.logistics_fetched_at,
        "nextQueryAt": shipment.logistics_next_query_at,
        "estimatedArrivalText": None,
        "mapAvailable": False,
        "errorCode": shipment.logistics_last_error_code,
    }


async def get_buyer_logistics(db, actor, order_id):
    order = await owned_order(db, actor, order_id, lock=True)
    shipment = await db.scalar(
        select(MallShipment)
        .where(MallShipment.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if shipment is None:
        raise ConflictException(message="订单尚无物流包裹")
    await _schedule_if_allowed(db, shipment)
    audit_order(db, actor, order, "mall_order_logistics_read")
    return _snapshot_view(order, shipment)


async def get_admin_logistics(db, actor, order_id):
    order = await admin_order(db, order_id, lock=True)
    shipment = await db.scalar(
        select(MallShipment)
        .where(MallShipment.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if shipment is None:
        raise ConflictException(message="订单尚无物流包裹")
    await _schedule_if_allowed(db, shipment)
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_logistics_read",
        entity_type="mall_order",
        entity_id=str(order.id),
        detail={"shipmentId": str(shipment.id), "shipmentVersion": shipment.version},
    )
    return _snapshot_view(order, shipment)


async def refresh_logistics(db, actor, shipment_id, body: VersionAction, *, key):
    if actor.actor_type != "admin":
        raise NotFoundException(message="商城包裹不存在")
    actor = await require_mall_admin_permission(
        {"sub": str(actor.actor_id), "user_type": "admin"},
        db,
        "mall.shipments.write",
        current=True,
    )
    order_id = await db.scalar(select(MallShipment.order_id).where(MallShipment.id == shipment_id))
    if order_id is None:
        raise NotFoundException(message="商城包裹不存在")
    order = await admin_order(db, order_id, lock=True)
    shipment = await db.scalar(
        select(MallShipment)
        .where(MallShipment.id == shipment_id, MallShipment.order_id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if shipment is None:
        raise NotFoundException(message="商城包裹不存在")
    payload = {"shipmentId": shipment_id, **body.model_dump(mode="json")}
    intent = await reserve_mall_command(
        db,
        actor=actor,
        action="refreshMallLogistics",
        key=key,
        payload=payload,
    )
    if not intent.created:
        command = intent.command
        if command.status != "completed" or command.entity_id != shipment.id:
            raise ConflictException(message="原物流刷新请求仍在处理中")
        return {
            "commandId": str(command.id),
            "scheduled": command.result_code == "scheduled",
            "snapshot": _snapshot_view(order, shipment),
        }
    if shipment.version != body.expected_version:
        raise ConflictException(message="包裹版本已变化，请重新读取")
    scheduled = await _schedule_if_allowed(db, shipment)
    await complete_mall_command(
        db,
        intent,
        entity_type="mall_shipment",
        entity_id=shipment.id,
        result_code="scheduled" if scheduled else "rate_limited",
    )
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_admin_logistics_refresh",
        entity_type="mall_order",
        entity_id=str(order.id),
        detail={
            "shipmentId": str(shipment.id),
            "shipmentVersion": shipment.version,
            "scheduled": scheduled,
        },
    )
    return {
        "commandId": str(intent.command.id),
        "scheduled": scheduled,
        "snapshot": _snapshot_view(order, shipment),
    }


def logistics_handlers(sessions, *, client=None):
    """Version-fenced worker; production remains closed until data-release governance."""
    fake_client = client or FakeKuaidi100Client()

    async def query(item: MallWorkItem):
        if item.kind != "mall_logistics_query" or item.entity_type != "mall_shipment":
            raise ValueError("invalid logistics work item")
        async with sessions() as db:
            order_id = await db.scalar(
                select(MallShipment.order_id).where(MallShipment.id == item.entity_id)
            )
            if order_id is None:
                return
            order = await db.scalar(
                select(MallOrder)
                .where(MallOrder.id == order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if order is None or await locked_mall_lease(db, item) is None:
                return
            shipment = await db.scalar(
                select(MallShipment)
                .where(MallShipment.id == item.entity_id, MallShipment.order_id == order.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                shipment is None
                or shipment.version != item.entity_version
                or order.status not in {"pending_receipt", "completed"}
                or not order.shipped_at
            ):
                return
            version, tracking_hash = shipment.version, shipment.tracking_identity_hash
            courier_code, tracking_no = shipment.courier_code, shipment.tracking_no
            settings = get_settings()
            local_fake = (
                settings.app_environment in {"development", "test"}
                and settings.mall_kuaidi100_mode == "fake"
                and not settings.mall_kuaidi100_outbound_enabled
            )
            await db.commit()

        result, source, failure = None, None, None
        if local_fake:
            try:
                result = await fake_client.query(
                    courier_code=courier_code,
                    tracking_no=tracking_no,
                )
                source = "fake"
            except Kuaidi100Error as exc:
                failure = exc.code if exc.code in SAFE_QUERY_ERRORS else "service_error"
            except Exception:
                failure = "service_error"
        else:
            failure = "data_release_gate_inactive"

        async with sessions() as db:
            order = await db.scalar(
                select(MallOrder)
                .where(MallOrder.id == order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if order is None or await locked_mall_lease(db, item) is None:
                return
            shipment = await db.scalar(
                select(MallShipment)
                .where(MallShipment.id == item.entity_id, MallShipment.order_id == order.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                shipment is None
                or shipment.version != version
                or shipment.tracking_identity_hash != tracking_hash
                or order.status not in {"pending_receipt", "completed"}
            ):
                return
            now = utc_now()
            shipment.logistics_fetched_at = now
            if result is not None:
                normalized = _normalize_provider_result(result, source=source)
                shipment.tracking_snapshot = normalized
                shipment.provider_state = normalized["stateCode"]
                shipment.logistics_status = "available" if normalized["events"] else "no_record"
                shipment.logistics_last_error_code = None
            else:
                has_old_data = bool((shipment.tracking_snapshot or {}).get("events"))
                shipment.logistics_status = (
                    "stale"
                    if has_old_data
                    else (failure if failure in SAFE_QUERY_ERRORS else "config_required")
                )
                shipment.logistics_last_error_code = failure or "service_error"
            await db.commit()

    return {"mall_logistics_query": query}
