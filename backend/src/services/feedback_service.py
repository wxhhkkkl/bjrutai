"""Feedback domain service: submission, management queries and state changes."""

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    ValidationException,
)
from ..integrations.cos_client import COSClient
from ..models.audit import AuditLog
from ..models.feedback import Feedback, FeedbackAction
from ..models.user import AdminAccount, User
from ..schemas.feedback import FeedbackAdminUpdateRequest, FeedbackCreateRequest


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _mask_phone(phone: str | None) -> str | None:
    value = str(phone or "")
    if len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    return None


def _fingerprint(data: FeedbackCreateRequest) -> str:
    payload = {"type": data.type, "content": data.content, "imageFiles": data.imageFiles}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _feedback_no() -> str:
    return f"FB-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(4).upper()}"


def _attachment_descriptor(key: str) -> dict:
    suffix = key.lower().rsplit(".", 1)[-1] if "." in key else ""
    return {
        "objectKey": key,
        "contentType": "image/png" if suffix == "png" else "image/jpeg",
        "legacy": False,
    }


def _attachments(raw: object) -> list[dict]:
    result: list[dict] = []
    for item in raw or []:
        if isinstance(item, str):
            result.append({"objectKey": item, "contentType": None, "legacy": True})
        elif isinstance(item, dict) and item.get("objectKey"):
            result.append(item)
    return result


def serialize_submission(feedback: Feedback) -> dict:
    return {
        "feedbackId": str(feedback.id),
        "feedbackNo": feedback.feedback_no,
        "type": feedback.type,
        "status": feedback.status,
        "submittedAt": _iso(feedback.created_at),
        "version": feedback.version,
    }


async def create_feedback(
    db: AsyncSession,
    *,
    user_id: int,
    data: FeedbackCreateRequest,
    idempotency_key: str,
    cos: COSClient,
) -> Feedback:
    if not idempotency_key or len(idempotency_key) > 128:
        raise BadRequestException(message="缺少或无效的 Idempotency-Key")
    fingerprint = _fingerprint(data)
    existing = (
        (
            await db.execute(
                select(Feedback).where(
                    Feedback.user_id == user_id, Feedback.idempotency_key == idempotency_key
                )
            )
        )
        .scalars()
        .first()
    )
    if existing:
        if existing.submission_fingerprint != fingerprint:
            raise ConflictException(message="幂等键已用于不同的反馈内容", code=40911)
        return existing

    descriptors: list[dict] = []
    for file_id in data.imageFiles:
        if not cos.belongs_to_feedback_user(file_id, user_id):
            raise BadRequestException(message="图片不属于当前用户")
        if not await cos.feedback_object_exists(file_id):
            raise BadRequestException(message="图片尚未上传完成或不可访问")
        descriptors.append(_attachment_descriptor(file_id))

    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    feedback = Feedback(
        feedback_no=_feedback_no(),
        user_id=user_id,
        submitter_name_snapshot=user.name if user else None,
        submitter_phone_masked_snapshot=(user.phone_masked or _mask_phone(user.phone))
        if user
        else None,
        type=data.type,
        content=data.content,
        image_files=descriptors,
        status="submitted",
        version=1,
        idempotency_key=idempotency_key,
        submission_fingerprint=fingerprint,
        notification_status="not_required",
    )
    db.add(feedback)
    await db.flush()
    # Store a safe audit reference only; never duplicate content or object keys.
    db.add(
        AuditLog(
            user_id=user_id,
            action="feedback_submit",
            entity_type="feedback",
            entity_id=feedback.feedback_no,
            detail={
                "feedbackNo": feedback.feedback_no,
                "type": feedback.type,
                "imageCount": len(descriptors),
                "contentLength": len(feedback.content),
            },
        )
    )
    return feedback


async def list_current_feedbacks(
    db: AsyncSession, *, user_id: int, status: str | None, cursor: str | None, page_size: int
) -> dict:
    query = select(Feedback).where(Feedback.user_id == user_id)
    if status in {"submitted", "processing", "resolved"}:
        query = query.where(Feedback.status == status)
    if cursor:
        try:
            query = query.where(Feedback.id < int(cursor))
        except ValueError:
            pass
    rows = (
        (await db.execute(query.order_by(Feedback.id.desc()).limit(page_size + 1))).scalars().all()
    )
    items = rows[:page_size]
    return {
        "items": [
            {
                "feedbackId": str(row.id),
                "feedbackNo": row.feedback_no,
                "type": row.type,
                "content": row.content,
                "imageCount": len(_attachments(row.image_files)),
                "status": row.status,
                "resolution": row.resolution,
                "createdAt": _iso(row.created_at),
                "updatedAt": _iso(row.updated_at),
            }
            for row in items
        ],
        "nextCursor": str(items[-1].id) if len(rows) > page_size and items else None,
        "hasMore": len(rows) > page_size,
    }


async def list_admin_feedbacks(
    db: AsyncSession,
    *,
    status: str | None,
    type_: str | None,
    keyword: str | None,
    submitted_from: datetime | None,
    submitted_to: datetime | None,
    page: int,
    page_size: int,
) -> dict:
    query = select(Feedback)
    if status:
        query = query.where(Feedback.status == status)
    if type_:
        query = query.where(Feedback.type == type_)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                Feedback.feedback_no.ilike(pattern), Feedback.submitter_name_snapshot.ilike(pattern)
            )
        )
    if submitted_from:
        query = query.where(Feedback.created_at >= submitted_from)
    if submitted_to:
        query = query.where(Feedback.created_at <= submitted_to)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (
        (
            await db.execute(
                query.order_by(Feedback.created_at.desc(), Feedback.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    names = await _admin_names(db, [row.first_handler_id for row in rows])
    return {
        "items": [
            {
                "feedbackId": str(row.id),
                "feedbackNo": row.feedback_no,
                "type": row.type,
                "contentSummary": row.content[:100],
                "imageCount": len(_attachments(row.image_files)),
                "submitter": {
                    "name": row.submitter_name_snapshot,
                    "phoneMasked": row.submitter_phone_masked_snapshot,
                    "available": row.user_id is not None,
                },
                "status": row.status,
                "firstHandlerName": names.get(row.first_handler_id),
                "createdAt": _iso(row.created_at),
                "updatedAt": _iso(row.updated_at),
                "version": row.version,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    }


async def _admin_names(db: AsyncSession, ids: list[int | None]) -> dict[int, str]:
    values = [item for item in set(ids) if item]
    if not values:
        return {}
    rows = (
        (await db.execute(select(AdminAccount).where(AdminAccount.id.in_(values)))).scalars().all()
    )
    return {row.id: row.username for row in rows}


async def get_admin_feedback(
    db: AsyncSession, *, feedback_no: str, cos: COSClient, viewer_admin_id: int | None = None
) -> dict:
    feedback = (
        (await db.execute(select(Feedback).where(Feedback.feedback_no == feedback_no)))
        .scalars()
        .first()
    )
    if not feedback:
        raise NotFoundException(message="反馈不存在")
    actions = (
        (
            await db.execute(
                select(FeedbackAction)
                .where(FeedbackAction.feedback_id == feedback.id)
                .order_by(FeedbackAction.created_at, FeedbackAction.id)
            )
        )
        .scalars()
        .all()
    )
    names = await _admin_names(
        db,
        [feedback.first_handler_id, feedback.resolved_by_id]
        + [item.operator_id for item in actions],
    )
    attachments = []
    for index, item in enumerate(_attachments(feedback.image_files)):
        key = item.get("objectKey")
        try:
            preview = cos.generate_preview_url(key) if key else None
        except Exception:
            preview = None
        attachments.append(
            {
                "order": index,
                "contentType": item.get("contentType"),
                "available": bool(preview),
                "previewUrl": preview,
                "expiresAt": _iso(_now() + timedelta(minutes=10)) if preview else None,
            }
        )
    # A read audit deliberately contains only identifiers and lengths.
    db.add(
        AuditLog(
            user_id=None,
            action="feedback_view",
            entity_type="feedback",
            entity_id=feedback.feedback_no,
            detail={
                "adminAccountId": viewer_admin_id,
                "feedbackNo": feedback.feedback_no,
                "version": feedback.version,
            },
        )
    )
    return {
        "feedbackId": str(feedback.id),
        "feedbackNo": feedback.feedback_no,
        "type": feedback.type,
        "content": feedback.content,
        "attachments": attachments,
        "submitter": {
            "name": feedback.submitter_name_snapshot,
            "phoneMasked": feedback.submitter_phone_masked_snapshot,
            "available": feedback.user_id is not None,
        },
        "status": feedback.status,
        "firstHandler": (
            {
                "id": str(feedback.first_handler_id),
                "name": names.get(feedback.first_handler_id),
                "handledAt": _iso(feedback.first_handled_at),
            }
            if feedback.first_handler_id
            else None
        ),
        "resolver": (
            {
                "id": str(feedback.resolved_by_id),
                "name": names.get(feedback.resolved_by_id),
                "resolvedAt": _iso(feedback.resolved_at),
            }
            if feedback.resolved_by_id
            else None
        ),
        "resolution": feedback.resolution,
        "notificationStatus": feedback.notification_status,
        "createdAt": _iso(feedback.created_at),
        "updatedAt": _iso(feedback.updated_at),
        "version": feedback.version,
        "actions": [
            {
                "actionId": str(item.id),
                "actionType": item.action_type,
                "operatorName": item.operator_name_snapshot,
                "fromStatus": item.from_status,
                "toStatus": item.to_status,
                "internalNote": item.internal_note,
                "userResolution": item.user_resolution,
                "createdAt": _iso(item.created_at),
            }
            for item in actions
        ],
    }


async def update_admin_feedback(
    db: AsyncSession, *, feedback_no: str, data: FeedbackAdminUpdateRequest, admin_id: int
) -> Feedback:
    feedback = (
        (await db.execute(select(Feedback).where(Feedback.feedback_no == feedback_no)))
        .scalars()
        .first()
    )
    if not feedback:
        raise NotFoundException(message="反馈不存在")
    if feedback.version != data.expectedVersion or feedback.status == "resolved":
        raise ConflictException(
            message="反馈已被其他管理员更新，请刷新后重试",
            detail={"currentVersion": feedback.version},
            code=40910,
        )
    if feedback.status == "submitted" and data.status not in {"processing", "resolved"}:
        raise BadRequestException(message="非法状态转换")
    if feedback.status == "processing" and data.status not in {"processing", "resolved"}:
        raise BadRequestException(message="非法状态转换")
    if data.status == "processing" and feedback.status == "processing" and not data.internalNote:
        raise ValidationException(message="追加处理中备注时必须填写内部备注")
    if data.status == "resolved" and not data.resolution:
        raise ValidationException(message="标记已解决时必须填写处理结果")

    admin = (
        (await db.execute(select(AdminAccount).where(AdminAccount.id == admin_id)))
        .scalars()
        .first()
    )
    name = admin.username if admin else "管理员"
    previous = feedback.status
    next_version = feedback.version + 1
    now = _now()
    if data.status == "processing" and feedback.first_handler_id is None:
        feedback.first_handler_id, feedback.first_handled_at = admin_id, now
    if data.status == "resolved":
        if feedback.first_handler_id is None:
            feedback.first_handler_id, feedback.first_handled_at = admin_id, now
        feedback.resolved_by_id, feedback.resolved_at = admin_id, now
        feedback.resolution = data.resolution
        feedback.notification_status = "pending"
        feedback.notification_next_retry_at = now
        feedback.notification_last_error = None
    feedback.status, feedback.version, feedback.updated_at = data.status, next_version, now
    action_type = (
        "resolve"
        if data.status == "resolved"
        else ("note" if previous == data.status else "status_change")
    )
    db.add(
        FeedbackAction(
            feedback_id=feedback.id,
            operator_id=admin_id,
            operator_name_snapshot=name,
            action_type=action_type,
            from_status=previous,
            to_status=data.status,
            internal_note=data.internalNote,
            user_resolution=data.resolution if data.status == "resolved" else None,
            version_before=next_version - 1,
            version_after=next_version,
            created_at=now,
        )
    )
    db.add(
        AuditLog(
            user_id=None,
            action="feedback_process",
            entity_type="feedback",
            entity_id=feedback.feedback_no,
            detail={
                "adminAccountId": admin_id,
                "feedbackNo": feedback.feedback_no,
                "fromStatus": previous,
                "toStatus": data.status,
                "version": next_version,
                "internalNoteLength": len(data.internalNote or ""),
                "resolutionLength": len(data.resolution or ""),
            },
        )
    )
    await db.flush()
    return feedback
