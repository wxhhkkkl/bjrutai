"""Best-effort, idempotent in-app mall notices and responsibility tasks."""

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mall_base import utc_now
from ..models.mall_finance import MallPayment, MallRefund
from ..models.mall_operations import MallJob
from ..models.mall_trade import MallOrder
from ..models.notification import Notification, NotificationCategory
from ..models.user import ActivationStatus, User, UserType
from .mall_job_service import enqueue_mall_job, locked_mall_lease

logger = logging.getLogger(__name__)

FUNDS_RESPONSIBILITY_KIND = "mall_funds_unknown_responsibility"
FUNDS_UNKNOWN_LIMIT = timedelta(minutes=10)
RESPONSIBILITY_REFRESH_INTERVAL = timedelta(minutes=1)
MAX_FUND_TASKS_PER_SCAN = 100
AFTERSALE_STATUS_LABELS = {
    "submitted": "等待商家审核",
    "awaiting_return": "等待寄回",
    "awaiting_receipt": "等待商家验收",
    "awaiting_refund": "退款待处理",
    "refunding": "退款处理中",
    "completed": "售后完成",
    "rejected": "申请未通过",
    "withdrawn": "申请已撤回",
    "disputed": "等待人工核实",
    "closed": "售后已关闭",
}


def aftersale_status_label(status: str) -> str:
    return AFTERSALE_STATUS_LABELS.get(status, "处理中")


def _utc_naive(value: datetime | None = None) -> datetime:
    value = value or utc_now()
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


async def _persist_notification(
    db: AsyncSession,
    *,
    user_id: int,
    event_key: str,
    title: str,
    summary: str,
    target: str | None = None,
) -> str:
    """Return created/existing; insert errors escape so the caller can retry safely."""
    if not 1 <= len(event_key) <= 191 or not title or len(title) > 200:
        raise ValueError("invalid mall notification identity or title")
    try:
        async with db.begin_nested():
            existing = await db.scalar(
                select(Notification.id).where(Notification.event_key == event_key)
            )
            if existing is not None:
                return "existing"
            db.add(
                Notification(
                    user_id=user_id,
                    category=NotificationCategory.MALL,
                    event_key=event_key,
                    title=title,
                    summary=summary,
                    target=target,
                )
            )
            await db.flush()
        return "created"
    except IntegrityError:
        # A concurrent writer may have committed the same unique event key.
        return "existing"


async def _enqueue_notification_retry(
    db: AsyncSession,
    *,
    user_id: int,
    event_key: str,
    title: str,
    summary: str,
    target: str | None,
) -> None:
    payload = {
        "userId": user_id,
        "eventKey": event_key,
        "title": title,
        "summary": summary,
        "target": target,
    }
    dedupe_key = "mall-notification:" + hashlib.sha256(event_key.encode("utf-8")).hexdigest()
    try:
        async with db.begin_nested():
            job = await enqueue_mall_job(
                db,
                kind="mall_notification_deliver",
                entity_type="notification",
                entity_id=user_id,
                entity_version=1,
                dedupe_key=dedupe_key,
            )
            job.notification_payload = payload
            await db.flush()
    except Exception:
        # Notification/outbox storage is best effort with respect to the trade.
        logger.warning("mall_notification_outbox_enqueue_failed")


async def _write_notification(
    db: AsyncSession,
    *,
    user_id: int,
    event_key: str,
    title: str,
    summary: str,
    target: str | None = None,
) -> bool:
    """Insert immediately and persist a retry job if the in-app write fails."""
    try:
        return (
            await _persist_notification(
                db,
                user_id=user_id,
                event_key=event_key,
                title=title,
                summary=summary,
                target=target,
            )
            == "created"
        )
    except Exception:
        logger.warning("mall_notification_insert_failed")
        await _enqueue_notification_retry(
            db,
            user_id=user_id,
            event_key=event_key,
            title=title,
            summary=summary,
            target=target,
        )
        return False


def mall_notification_handlers(session_factory):
    """Build a worker handler for idempotent in-app delivery retries."""

    async def deliver(item):
        async with session_factory() as db:
            job = await locked_mall_lease(db, item)
            if job is None:
                return
            payload = job.notification_payload
            if not isinstance(payload, dict):
                raise ValueError("notification job payload is missing")
            try:
                user_id = int(payload["userId"])
                event_key = str(payload["eventKey"])
                title = str(payload["title"])
                summary = str(payload["summary"])
                target = payload.get("target")
                if target is not None:
                    target = str(target)
                await _persist_notification(
                    db,
                    user_id=user_id,
                    event_key=event_key,
                    title=title,
                    summary=summary,
                    target=target,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    return {"mall_notification_deliver": deliver}


async def notify_mall_buyer(
    db: AsyncSession,
    *,
    buyer_user_id: int,
    event_key: str,
    title: str,
    summary: str,
    target: str,
) -> bool:
    """Create a buyer-visible notice containing only the minimum trade context."""
    return await _write_notification(
        db,
        user_id=buyer_user_id,
        event_key=event_key,
        title=title,
        summary=summary,
        target=target,
    )


async def _active_finance_recipients(db: AsyncSession) -> list[int]:
    try:
        async with db.begin_nested():
            result = await db.scalars(
                select(User.id).where(
                    User.user_type.in_((UserType.ADMIN, UserType.FINANCE, UserType.OPS)),
                    User.activation_status == ActivationStatus.ACTIVE,
                )
            )
            return list(result.all())
    except Exception:
        logger.exception("Mall responsibility recipients could not be resolved")
        return []


async def _notify_finance_recipients(
    db: AsyncSession,
    *,
    event_key: str,
    title: str,
    summary: str,
    target: str,
) -> int:
    delivered = 0
    for user_id in await _active_finance_recipients(db):
        if await _write_notification(
            db,
            user_id=user_id,
            event_key=f"{event_key}:user:{user_id}",
            title=title,
            summary=summary,
            target=target,
        ):
            delivered += 1
    return delivered


def _funds_identity(record_type: str, identity: int, unknown_since: datetime) -> str:
    timestamp = _utc_naive(unknown_since).isoformat(timespec="microseconds")
    return f"mall:funds-unknown:{record_type}:{identity}:{timestamp}"


def _responsibility_evidence(record_type: str, record) -> dict:
    return {
        "recordType": record_type,
        "recordId": str(record.id),
        "orderId": str(record.order_id),
        "status": record.status,
        "unknownSince": _utc_naive(record.unknown_since).isoformat(timespec="microseconds"),
        "lastQueryAt": (
            _utc_naive(record.last_query_at).isoformat(timespec="seconds")
            if record.last_query_at
            else None
        ),
        "amountCent": record.amount_cent if record_type == "payment" else record.total_cent,
    }


def _responsibility_next_step(record_type: str) -> str:
    if record_type == "payment":
        return "按原支付记录查证；核实前保留订单和库存占用，不得按失败关闭"
    return "按原退款记录查证；核实前保留退款占用，不得重复发起退款"


def _resolution_for(record_type: str, status: str) -> tuple[str, str]:
    subject = "支付" if record_type == "payment" else "退款"
    return (
        f"{record_type}_{status}",
        f"最近查证确认{subject}状态为“{status}”，责任待办据此关闭。",
    )


async def _source_for_job(db: AsyncSession, job: MallJob):
    model = MallPayment if job.entity_type == "mall_payment" else MallRefund
    return await db.scalar(
        select(model)
        .where(model.id == job.entity_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _refresh_open_responsibilities(db: AsyncSession, *, now: datetime) -> int:
    refreshed = 0
    cursor_id = 0
    while True:
        jobs = (
            await db.scalars(
                select(MallJob)
                .where(
                    MallJob.kind == FUNDS_RESPONSIBILITY_KIND,
                    MallJob.status == "manual",
                    MallJob.id > cursor_id,
                )
                .order_by(MallJob.id)
                .limit(MAX_FUND_TASKS_PER_SCAN)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).all()
        if not jobs:
            break
        for job in jobs:
            record_type = "payment" if job.entity_type == "mall_payment" else "refund"
            record = await _source_for_job(db, job)
            if record is None:
                continue
            evidence = job.responsibility_evidence or {}
            current_unknown_since = (
                _utc_naive(record.unknown_since).isoformat(timespec="microseconds")
                if record.unknown_since
                else None
            )
            same_interval = (
                record.status == "unknown"
                and current_unknown_since is not None
                and evidence.get("unknownSince") == current_unknown_since
            )
            if record.status == "unknown" and not same_interval:
                if job.responsibility_last_verified_at is None or (
                    job.responsibility_last_verified_at
                    <= now - RESPONSIBILITY_REFRESH_INTERVAL
                ):
                    refreshed_evidence = _responsibility_evidence(record_type, record)
                    refreshed_evidence["currentUnknownSince"] = current_unknown_since
                    refreshed_evidence["unknownSince"] = evidence.get("unknownSince")
                    job.responsibility_last_verified_at = now
                    job.responsibility_evidence = refreshed_evidence
                    job.last_error_code = "funds_unknown_interval_changed_review_required"
                    job.responsibility_next_step = (
                        "核对原未知区间的准确结果，并按当前未知记录继续查证"
                    )
                    refreshed += 1
                continue
            if not same_interval:
                code, summary = _resolution_for(record_type, record.status)
                job.status = "done"
                job.finished_at = now
                job.resolved_at = now
                job.resolved_by_type = "system"
                job.resolved_by_id = 0
                job.resolution_code = code
                job.resolution_summary = summary
                job.last_error_code = None
                job.lease_owner = job.lease_until = None
                refreshed += 1
                continue

            last_verified = job.responsibility_last_verified_at
            if last_verified is None or last_verified <= now - RESPONSIBILITY_REFRESH_INTERVAL:
                job.responsibility_last_verified_at = now
                job.responsibility_evidence = _responsibility_evidence(record_type, record)
                await _notify_fund_responsibility(db, record_type, record, job.dedupe_key)
                refreshed += 1
        cursor_id = jobs[-1].id
        if len(jobs) < MAX_FUND_TASKS_PER_SCAN:
            break
    return refreshed


async def _notify_fund_responsibility(
    db: AsyncSession, record_type: str, record, event_key: str
) -> None:
    order_no = await db.scalar(select(MallOrder.order_no).where(MallOrder.id == record.order_id))
    subject = "支付" if record_type == "payment" else "退款"
    title = f"商城{subject}结果待核实"
    summary = f"订单号 {order_no or '未知'} 的{subject}结果持续未知，需财务按原记录查证。"
    await _notify_finance_recipients(
        db,
        event_key=event_key,
        title=title,
        summary=summary,
        target=f"/admin/mall/{'payments' if record_type == 'payment' else 'refunds'}/{record.id}",
    )


async def _create_fund_responsibility(
    db: AsyncSession,
    *,
    record_type: str,
    record,
    now: datetime,
) -> bool:
    if record.unknown_since is None:
        return False
    job_kind = "mall_payment" if record_type == "payment" else "mall_refund"
    event_key = _funds_identity(record_type, record.id, record.unknown_since)
    existing = await db.scalar(select(MallJob).where(MallJob.dedupe_key == event_key))
    if existing is not None:
        return False

    job = await enqueue_mall_job(
        db,
        kind=FUNDS_RESPONSIBILITY_KIND,
        entity_type=job_kind,
        entity_id=record.id,
        entity_version=record.version,
        dedupe_key=event_key,
        next_run_at=now,
    )
    if job.status == "done":
        return False
    first_discovery = job.responsibility_first_discovered_at is None
    job.status = "manual"
    job.last_error_code = "funds_unknown_reconciliation_required"
    job.responsibility_role = "finance"
    job.responsibility_first_discovered_at = job.responsibility_first_discovered_at or now
    job.responsibility_last_verified_at = now
    job.responsibility_evidence = _responsibility_evidence(record_type, record)
    job.responsibility_next_step = _responsibility_next_step(record_type)
    job.entity_version = record.version

    if first_discovery:
        await _notify_fund_responsibility(db, record_type, record, event_key)
    return first_discovery


async def schedule_overdue_funds_responsibilities(
    db: AsyncSession, *, now: datetime | None = None
) -> int:
    """Open one finance responsibility task after a continuous unknown interval >10m."""
    current = _utc_naive(now)
    await _refresh_open_responsibilities(db, now=current)
    cutoff = current - FUNDS_UNKNOWN_LIMIT
    created = 0
    for model, record_type in ((MallPayment, "payment"), (MallRefund, "refund")):
        cursor_time = None
        cursor_id = 0
        while True:
            conditions = [model.status == "unknown", model.unknown_since < cutoff]
            if cursor_time is not None:
                conditions.append(
                    or_(
                        model.unknown_since > cursor_time,
                        and_(model.unknown_since == cursor_time, model.id > cursor_id),
                    )
                )
            rows = (
                await db.scalars(
                    select(model)
                    .where(*conditions)
                    .order_by(model.unknown_since, model.id)
                    .limit(MAX_FUND_TASKS_PER_SCAN)
                    .with_for_update(skip_locked=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
            if not rows:
                break
            for record in rows:
                created += await _create_fund_responsibility(
                    db, record_type=record_type, record=record, now=current
                )
            cursor_time, cursor_id = rows[-1].unknown_since, rows[-1].id
            if len(rows) < MAX_FUND_TASKS_PER_SCAN:
                break
    await db.flush()
    return created
