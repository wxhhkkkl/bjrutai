"""Durable, bounded finance export requests and private file generation."""

import csv
import hashlib
import io
import uuid
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.mall_deps import MallActor
from ..core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ..models.mall_base import utc_now
from ..models.mall_finance import MallFinanceExportRequest, MallPayment, MallRefund
from ..models.mall_operations import MallCommand, MallFile, MallJob
from ..models.mall_trade import MallOrder
from ..models.user import User
from ..tasks.mall_tasks import MallWorkItem
from .mall_audit_service import record_mall_admin_audit
from .mall_command_service import canonical_payload_hash, reserve_mall_command
from .mall_job_service import enqueue_mall_job, locked_mall_lease
from .mall_order_text import safe_order_text

MAX_FINANCE_EXPORT_ROWS = 50_000
MAX_FINANCE_EXPORT_BYTES = 10 * 1024 * 1024
CSV_MIME = "text/csv"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PAYMENT_COLUMNS = (
    ("支付单ID", "paymentId"),
    ("订单号", "orderNo"),
    ("买家ID", "buyerId"),
    ("买家", "buyerName"),
    ("商户支付单号", "outTradeNo"),
    ("渠道交易单号", "channelTransactionId"),
    ("状态", "status"),
    ("支付金额（分）", "amountCent"),
    ("成功退款（分）", "refundSucceededCent"),
    ("净收（分）", "netReceivedCent"),
    ("支付成功时间", "confirmedAt"),
    ("记录时间", "createdAt"),
)
REFUND_COLUMNS = (
    ("退款单ID", "refundId"),
    ("订单号", "orderNo"),
    ("售后ID", "aftersaleId"),
    ("支付单ID", "paymentId"),
    ("商户退款单号", "outRefundNo"),
    ("渠道退款单号", "channelRefundId"),
    ("状态", "status"),
    ("商品退款（分）", "goodsRefundCent"),
    ("运费退款（分）", "freightRefundCent"),
    ("退款总额（分）", "totalCent"),
    ("退款成功时间", "confirmedAt"),
    ("记录时间", "createdAt"),
)
PAYMENT_STATUSES = {"creating", "pending", "unknown", "succeeded", "closed", "failed"}
REFUND_STATUSES = {
    "prepared",
    "processing",
    "unknown",
    "succeeded",
    "closed",
    "abnormal",
    "rejected_unaccepted",
}


def _require_export(actor: MallActor):
    if actor.actor_type != "admin" or "mall.finance.export" not in actor.permissions:
        raise ForbiddenException(message="缺少商城权限: mall.finance.export")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("finance export time must include a timezone")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_text(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_kind_status(kind, status):
    allowed = PAYMENT_STATUSES if kind == "payments" else REFUND_STATUSES
    if status is not None and status not in allowed:
        raise ValidationException(message="状态筛选与导出类型不匹配")


def _export_response(request, command, job):
    state = {
        "ready": "pending",
        "retry": "pending",
        "running": "running",
        "manual": "failed",
        "done": "completed",
    }.get(job.status, request.status)
    if request.status == "ready":
        state = "completed"
    elif request.status == "failed" and job.status != "running":
        state = "failed"
    return {
        "commandId": str(command.id),
        "requestId": str(request.id),
        "jobId": str(job.id),
        "entityId": str(request.file_id),
        "fileId": str(request.file_id),
        "status": state,
        "version": request.version,
    }


async def _request_by_command(db, command_id):
    return await db.scalar(
        select(MallFinanceExportRequest).where(
            MallFinanceExportRequest.command_id == command_id
        )
    )


async def _job_for_request(db, request_id):
    return await db.scalar(
        select(MallJob).where(
            MallJob.kind == "mall_finance_export",
            MallJob.entity_type == "mall_finance_export_request",
            MallJob.entity_id == request_id,
        )
    )


async def create_finance_export(
    db: AsyncSession,
    actor: MallActor,
    kind: str,
    data,
    *,
    key: str,
):
    """Queue one explicit payment/refund export; no client-supplied file path."""
    _require_export(actor)
    if kind not in {"payments", "refunds"}:
        raise ConflictException(message="导出类型不合法")
    _validate_kind_status(kind, data.status)
    start, end = _utc_naive(data.from_at), _utc_naive(data.to_at)
    if start >= end or end - start > timedelta(days=31):
        raise ValidationException(message="导出时间范围无效或超过31天")
    payload = {
        "kind": kind,
        "from": _utc_text(start),
        "to": _utc_text(end),
        "status": data.status,
        "format": data.format,
    }
    action = "exportMallPayment" if kind == "payments" else "exportMallRefund"
    intent = await reserve_mall_command(
        db, actor=actor, action=action, key=key, payload=payload
    )
    if not intent.created:
        request = await _request_by_command(db, intent.command.id)
        if request is None:
            raise ConflictException(message="原导出请求记录不存在")
        job = await _job_for_request(db, request.id)
        if job is None:
            raise ConflictException(message="原导出任务不存在")
        if request.status == "failed":
            if job.status not in {"ready", "retry", "running"}:
                job.status = "ready"
                job.attempts = 0
                job.last_error_code = None
                job.lease_owner = job.lease_until = job.finished_at = None
                job.next_run_at = utc_now()
            request.status, request.error_code = "queued", None
            await db.flush()
        return _export_response(request, intent.command, job)

    extension = "csv" if data.format == "csv" else "xlsx"
    mime = CSV_MIME if data.format == "csv" else XLSX_MIME
    file = MallFile(
        object_key=f"mall/verified/finance-exports/pending-{uuid.uuid4().hex}.{extension}",
        purpose="finance_export",
        owner_actor_type=actor.actor_type,
        owner_actor_id=actor.actor_id,
        mime=mime,
        size=0,
        sha256="0" * 64,
        status="uploading",
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db.add(file)
    await db.flush()
    request = MallFinanceExportRequest(
        kind=kind,
        from_at=start,
        to_at=end,
        status_filter=data.status,
        format=data.format,
        status="queued",
        requested_by=actor.actor_id,
        command_id=intent.command.id,
        file_id=file.id,
    )
    db.add(request)
    await db.flush()
    job = await enqueue_mall_job(
        db,
        kind="mall_finance_export",
        entity_type="mall_finance_export_request",
        entity_id=request.id,
        entity_version=request.version,
        dedupe_key=f"mall-finance-export:{request.id}",
    )
    digest = canonical_payload_hash(payload)
    await record_mall_admin_audit(
        db,
        actor=actor,
        action="mall_finance_export_requested",
        entity_type="mall_finance_export_request",
        entity_id=str(request.id),
        detail={"kind": kind, "format": data.format, "filterDigest": digest},
    )
    await db.flush()
    return _export_response(request, intent.command, job)


def _csv_text(value):
    if isinstance(value, str):
        first = value.lstrip(" \t\r\n")[:1]
        if first in {"=", "+", "-", "@"} or value[:1] in {"\t", "\r", "\n"}:
            return "'" + value
    return value


def render_finance_export(kind: str, rows: list[dict], output_format: str):
    if kind not in {"payments", "refunds"} or output_format not in {"csv", "xlsx"}:
        raise ValueError("unsupported finance export format")
    columns = PAYMENT_COLUMNS if kind == "payments" else REFUND_COLUMNS
    if output_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow([label for label, _ in columns])
        for row in rows:
            writer.writerow([_csv_text(row.get(field)) for _, field in columns])
        return output.getvalue().encode("utf-8-sig"), CSV_MIME

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("支付订单" if kind == "payments" else "退款订单")
    sheet.append([label for label, _ in columns])
    for row in rows:
        cells = []
        for _, field in columns:
            value = row.get(field)
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                cell.data_type = "s"
            cells.append(cell)
        sheet.append(cells)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue(), XLSX_MIME


async def get_finance_export_rows(db: AsyncSession, request: MallFinanceExportRequest):
    """Load an explicit bounded scope; success rows use success time, other rows creation time."""
    if request.kind == "payments":
        event_time = case(
            (MallPayment.status == "succeeded", MallPayment.confirmed_at),
            else_=MallPayment.created_at,
        )
        query = (
            select(
                MallPayment,
                MallOrder.order_no,
                MallOrder.buyer_user_id,
                User.name,
                select(func.coalesce(func.sum(MallRefund.total_cent), 0))
                .where(
                    MallRefund.payment_id == MallPayment.id,
                    MallRefund.status == "succeeded",
                )
                .scalar_subquery()
                .label("refund_succeeded_cent"),
            )
            .join(MallOrder, MallOrder.id == MallPayment.order_id)
            .join(User, User.id == MallOrder.buyer_user_id)
            .where(event_time >= request.from_at, event_time < request.to_at)
        )
        if request.status_filter:
            query = query.where(MallPayment.status == request.status_filter)
        query = query.order_by(event_time, MallPayment.id).limit(MAX_FINANCE_EXPORT_ROWS + 1)
        result = (await db.execute(query)).all()
        if len(result) > MAX_FINANCE_EXPORT_ROWS:
            raise ValueError("export_row_limit")
        rows = []
        for payment, order_no, buyer_id, buyer_name, refund_cent in result:
            successful_refund = int(refund_cent or 0)
            rows.append(
                {
                    "paymentId": str(payment.id),
                    "orderNo": order_no,
                    "buyerId": str(buyer_id),
                    "buyerName": safe_order_text(buyer_name or f"用户{buyer_id}")[:64],
                    "outTradeNo": payment.out_trade_no,
                    "channelTransactionId": payment.channel_transaction_id,
                    "status": payment.status,
                    "amountCent": payment.amount_cent,
                    "refundSucceededCent": successful_refund,
                    "netReceivedCent": (
                        payment.amount_cent - successful_refund
                        if payment.status == "succeeded"
                        else None
                    ),
                    "confirmedAt": (
                        _utc_text(payment.confirmed_at) if payment.confirmed_at else None
                    ),
                    "createdAt": _utc_text(payment.created_at),
                }
            )
        return rows

    event_time = case(
        (MallRefund.status == "succeeded", MallRefund.confirmed_at),
        else_=MallRefund.created_at,
    )
    query = (
        select(MallRefund, MallOrder.order_no)
        .join(MallOrder, MallOrder.id == MallRefund.order_id)
        .where(event_time >= request.from_at, event_time < request.to_at)
    )
    if request.status_filter:
        query = query.where(MallRefund.status == request.status_filter)
    query = query.order_by(event_time, MallRefund.id).limit(MAX_FINANCE_EXPORT_ROWS + 1)
    result = (await db.execute(query)).all()
    if len(result) > MAX_FINANCE_EXPORT_ROWS:
        raise ValueError("export_row_limit")
    return [
        {
            "refundId": str(refund.id),
            "orderNo": order_no,
            "aftersaleId": str(refund.aftersale_id),
            "paymentId": str(refund.payment_id),
            "outRefundNo": refund.out_refund_no,
            "channelRefundId": refund.channel_refund_id,
            "status": refund.status,
            "goodsRefundCent": refund.goods_refund_cent,
            "freightRefundCent": refund.freight_refund_cent,
            "totalCent": refund.total_cent,
            "confirmedAt": _utc_text(refund.confirmed_at) if refund.confirmed_at else None,
            "createdAt": _utc_text(refund.created_at),
        }
        for refund, order_no in result
    ]


async def _fail_export(db, request_id, error_code="generation_failed"):
    row = await db.scalar(
        select(MallFinanceExportRequest)
        .where(MallFinanceExportRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row and row.status != "ready":
        row.status = "failed"
        row.error_code = error_code
        await db.commit()


async def process_finance_export(
    db: AsyncSession,
    identity: int,
    storage,
    *,
    work_item: MallWorkItem | None = None,
):
    """Build, upload, verify, and publish an export under an optional job lease."""
    request = await db.scalar(
        select(MallFinanceExportRequest)
        .where(MallFinanceExportRequest.id == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise NotFoundException(message="资金导出请求不存在")
    if work_item:
        if (
            (work_item.entity_type, work_item.entity_id, work_item.entity_version)
            != ("mall_finance_export_request", request.id, request.version)
            or not await locked_mall_lease(db, work_item)
        ):
            return None
    if request.status == "ready":
        command = await db.get(MallCommand, request.command_id)
        job = await _job_for_request(db, request.id)
        if command is None or job is None:
            raise ConflictException(message="已完成导出的关联记录不存在")
        return _export_response(request, command, job)
    file = await db.scalar(
        select(MallFile)
        .where(MallFile.id == request.file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if file is None or file.purpose != "finance_export":
        raise ConflictException(message="资金导出私有文件关联无效")
    command = await db.get(MallCommand, request.command_id)
    if command is None:
        raise ConflictException(message="资金导出命令关联无效")
    request.status, request.error_code = "processing", None
    await db.flush()
    try:
        rows = await get_finance_export_rows(db, request)
        content, mime = render_finance_export(request.kind, rows, request.format)
        if len(content) > MAX_FINANCE_EXPORT_BYTES:
            raise ValueError("export_size_limit")
        object_key = file.object_key
        await db.commit()

        await storage.put_private_bytes(object_key, content, mime=mime)
        actual = await storage.head(object_key)
        expected = {
            "mime": mime,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        if not actual or any(actual.get(name) != value for name, value in expected.items()):
            raise ValueError("export_checksum_mismatch")

        request = await db.scalar(
            select(MallFinanceExportRequest)
            .where(MallFinanceExportRequest.id == identity)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if request is None or request.status == "ready":
            return None
        if work_item:
            if (
                request.version != work_item.entity_version
                or not await locked_mall_lease(db, work_item)
            ):
                return None
        file = await db.scalar(
            select(MallFile)
            .where(MallFile.id == request.file_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        command = await db.scalar(
            select(MallCommand)
            .where(MallCommand.id == request.command_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = utc_now()
        file.mime, file.size, file.sha256 = mime, len(content), expected["sha256"]
        file.status, file.expires_at = "verified", now - timedelta(seconds=1)
        request.status, request.error_code = "ready", None
        request.row_count, request.completed_at = len(rows), now
        request.version += 1
        command.status = "completed"
        command.entity_type, command.entity_id = "mall_file", file.id
        command.result_code = "ready"
        await db.commit()
        return {
            "commandId": str(command.id),
            "requestId": str(request.id),
            "jobId": str(work_item.job_id) if work_item else None,
            "entityId": str(file.id),
            "fileId": str(file.id),
            "status": "completed",
            "rowCount": len(rows),
            "version": request.version,
        }
    except Exception:
        await db.rollback()
        await _fail_export(db, identity)
        raise


async def get_finance_export(db: AsyncSession, actor: MallActor, identity: int):
    """Return safe status only to the requester with current export permission."""
    _require_export(actor)
    request = await db.get(MallFinanceExportRequest, identity, populate_existing=True)
    if request is None or request.requested_by != actor.actor_id:
        raise NotFoundException(message="资金导出请求不存在")
    command = await db.get(MallCommand, request.command_id)
    job = await _job_for_request(db, request.id)
    if command is None or job is None:
        raise ConflictException(message="资金导出状态关联不完整")
    result = _export_response(request, command, job)
    result["rowCount"] = request.row_count
    result["errorCode"] = request.error_code
    result["completedAt"] = _utc_text(request.completed_at) if request.completed_at else None
    return result


def finance_export_handlers(sessions, storage=None):
    """Register the export worker only when private storage egress is enabled."""
    if storage is None:
        from ..core.config import get_settings
        from ..integrations.cos_client import MallCOSStore, get_cos_client

        settings = get_settings()
        if not settings.mall_storage_outbound_enabled:
            return {}
        storage = MallCOSStore(get_cos_client(), outbound_enabled=True)

    async def handler(item: MallWorkItem):
        if (item.kind, item.entity_type) != (
            "mall_finance_export",
            "mall_finance_export_request",
        ):
            raise ValueError("invalid finance export work item")
        async with sessions() as db:
            return await process_finance_export(
                db, item.entity_id, storage, work_item=item
            )

    return {"mall_finance_export": handler}
