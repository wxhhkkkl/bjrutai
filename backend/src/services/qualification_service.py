"""Qualification service – business logic for upload tokens, submission, review (US2)."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ..integrations.cos_client import get_cos_client
from ..models.hierarchy import Promoter
from ..models.qualification import QualStatus, Qualification, QualificationType
from ..schemas.qualification import (
    ACTION_LABELS,
    STATUS_LABELS,
    DraftRequest,
    QualificationCreate,
    QualificationUpdate,
    ReviewRequest,
    get_status_label,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Upload Token
# ============================================================================
async def get_upload_token(
    user_id: int,
    file_name: str,
    content_type: str,
    file_size: int,
) -> dict:
    """Validate and generate a COS upload token for the given file."""
    client = get_cos_client()
    try:
        result = client.generate_upload_token(
            user_id=user_id,
            file_name=file_name,
            content_type=content_type,
            file_size=file_size,
        )
    except ValueError as exc:
        raise BadRequestException(message=str(exc))

    return result


# ============================================================================
# Get Promoter helper
# ============================================================================
async def _get_promoter(db: AsyncSession, user_id: int) -> Promoter:
    """Look up the Promoter record for the given user. Raises Forbidden if not found."""
    result = await db.execute(
        select(Promoter).where(Promoter.user_id == user_id)
    )
    promoter = result.scalars().first()
    if promoter is None:
        raise ForbiddenException(message="You are not registered as a promoter")
    return promoter


async def _get_promoter_qualification(db: AsyncSession, qual_id: int, promoter_id: int) -> Qualification:
    """Look up a qualification by ID, scoped to the promoter. Raises NotFound/Forbidden."""
    result = await db.execute(
        select(Qualification).where(Qualification.id == qual_id)
    )
    qual = result.scalars().first()
    if qual is None:
        raise NotFoundException(message="Qualification record not found")
    if qual.promoter_id != promoter_id:
        raise ForbiddenException(message="You can only access your own qualifications")
    return qual


# ============================================================================
# Submit Qualification
# ============================================================================
async def submit_qualification(
    db: AsyncSession,
    user_id: int,
    data: QualificationCreate,
) -> Qualification:
    """Submit a new qualification for review.

    Checks that the promoter does not already have a reviewing or approved
    qualification of the same type.
    """
    promoter = await _get_promoter(db, user_id)

    # Validate qualification type
    if data.qualificationType not in ("individual", "enterprise"):
        raise BadRequestException(
            message=f"Invalid qualification type: {data.qualificationType}"
        )

    qual_type = QualificationType(data.qualificationType)

    # Check for existing active qualification of the same type
    result = await db.execute(
        select(Qualification).where(
            Qualification.promoter_id == promoter.id,
            Qualification.qualification_type == qual_type,
            Qualification.status.in_([QualStatus.REVIEWING, QualStatus.APPROVED]),
        )
    )
    existing = result.scalars().first()
    if existing is not None:
        raise ConflictException(
            message="A qualification record is already under review or approved for this type"
        )

    now = datetime.now(timezone.utc)
    qualification = Qualification(
        promoter_id=promoter.id,
        qualification_type=qual_type,
        status=QualStatus.REVIEWING,
        file_id=data.fileId,
        file_name=data.fileName,
        file_type=data.fileType,
        file_size=data.fileSize,
        submitted_at=now,
        version=1,
    )
    db.add(qualification)
    await db.flush()
    await db.refresh(qualification)

    # Update promoter qualification_status for quick lookups
    promoter.qualification_status = QualStatus.REVIEWING.value
    db.add(promoter)

    logger.info("Qualification submitted: id=%d promoter=%d type=%s", qualification.id, promoter.id, data.qualificationType)
    return qualification


# ============================================================================
# Get Current Qualifications
# ============================================================================
async def get_current(
    db: AsyncSession,
    user_id: int,
) -> dict:
    """Return all qualifications for the current promoter."""
    promoter = await _get_promoter(db, user_id)

    result = await db.execute(
        select(Qualification)
        .where(Qualification.promoter_id == promoter.id)
        .order_by(Qualification.updated_at.desc())
    )
    qualifications = result.scalars().all()

    items = [_qualification_to_item(q) for q in qualifications]
    return {"items": items}


# ============================================================================
# Update / Resubmit Qualification
# ============================================================================
async def update_qualification(
    db: AsyncSession,
    user_id: int,
    qualification_id: int,
    data: QualificationUpdate,
) -> Qualification:
    """Update and resubmit a qualification (only allowed for rejected or draft records)."""
    promoter = await _get_promoter(db, user_id)
    qual = await _get_promoter_qualification(db, qualification_id, promoter.id)

    # Only rejected or draft qualifications can be updated
    if qual.status not in (QualStatus.REJECTED, QualStatus.DRAFT):
        raise BadRequestException(
            message="Can only update rejected or draft qualification records"
        )

    # Optimistic locking
    if data.version != qual.version:
        raise ConflictException(
            message="Version conflict: the qualification has been modified since you last loaded it",
            detail={"currentVersion": qual.version, "providedVersion": data.version},
        )

    # Update fields
    if data.fileId is not None:
        qual.file_id = data.fileId
    if data.fileName is not None:
        qual.file_name = data.fileName
    if data.fileType is not None:
        qual.file_type = data.fileType
    if data.fileSize is not None:
        qual.file_size = data.fileSize

    qual.status = QualStatus.REVIEWING
    qual.rejected_reason = None
    qual.submitted_at = datetime.now(timezone.utc)
    qual.version += 1
    qual.updated_at = datetime.now(timezone.utc)

    db.add(qual)
    await db.flush()
    await db.refresh(qual)

    logger.info("Qualification resubmitted: id=%d promoter=%d", qual.id, promoter.id)
    return qual


# ============================================================================
# Get Review History
# ============================================================================
async def get_reviews(
    db: AsyncSession,
    user_id: int,
    qualification_id: int,
) -> dict:
    """Return the review history for a qualification (approve/reject actions logged in AuditLog)."""
    promoter = await _get_promoter(db, user_id)
    qual = await _get_promoter_qualification(db, qualification_id, promoter.id)

    # Read from AuditLog for review actions
    from ..models.audit import AuditLog

    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "qualification",
            AuditLog.entity_id == str(qualification_id),
        )
        .order_by(AuditLog.created_at.asc())
    )
    logs = result.scalars().all()

    items = []
    for log in logs:
        action = "approve" if "approved" in (log.action or "").lower() else "reject"
        detail_str = None
        if log.detail and isinstance(log.detail, dict):
            detail_str = log.detail.get("comment", "")
        items.append({
            "reviewId": str(log.id),
            "reviewerName": "管理员",
            "action": action,
            "actionLabel": ACTION_LABELS.get(action, action),
            "comment": detail_str,
            "reviewedAt": log.created_at.isoformat() if log.created_at else None,
        })

    return {"items": items}


# ============================================================================
# Save Draft
# ============================================================================
async def save_draft(
    db: AsyncSession,
    user_id: int,
    data: DraftRequest,
) -> Qualification:
    """Create or update a draft qualification. Draft does not trigger review."""
    promoter = await _get_promoter(db, user_id)

    if data.qualificationType not in ("individual", "enterprise"):
        raise BadRequestException(
            message=f"Invalid qualification type: {data.qualificationType}"
        )

    qual_type = QualificationType(data.qualificationType)

    # Cannot draft while an active qualification exists for this type
    result = await db.execute(
        select(Qualification).where(
            Qualification.promoter_id == promoter.id,
            Qualification.qualification_type == qual_type,
            Qualification.status.in_([QualStatus.REVIEWING, QualStatus.APPROVED]),
        )
    )
    existing = result.scalars().first()
    if existing is not None:
        raise ConflictException(
            message="A qualification record is already under review or approved for this type"
        )

    # Upsert: update existing draft or create new
    draft_result = await db.execute(
        select(Qualification).where(
            Qualification.promoter_id == promoter.id,
            Qualification.qualification_type == qual_type,
            Qualification.status == QualStatus.DRAFT,
        )
    )
    draft = draft_result.scalars().first()

    if draft is not None:
        # Update existing draft
        if data.fileId is not None:
            draft.file_id = data.fileId
        if data.fileName is not None:
            draft.file_name = data.fileName
        if data.fileType is not None:
            draft.file_type = data.fileType
        if data.fileSize is not None:
            draft.file_size = data.fileSize
        draft.updated_at = datetime.now(timezone.utc)
        db.add(draft)
    else:
        draft = Qualification(
            promoter_id=promoter.id,
            qualification_type=qual_type,
            status=QualStatus.DRAFT,
            file_id=data.fileId,
            file_name=data.fileName,
            file_type=data.fileType,
            file_size=data.fileSize,
        )
        db.add(draft)

    await db.flush()
    await db.refresh(draft)
    return draft


# ============================================================================
# Admin: List Pending Qualifications
# ============================================================================
async def list_pending(
    db: AsyncSession,
    status_filter: Optional[str] = None,
) -> dict:
    """Admin: list qualifications with optional status filter. Default: reviewing."""
    if status_filter:
        try:
            status_enum = QualStatus(status_filter)
        except ValueError:
            raise BadRequestException(message=f"Invalid status filter: {status_filter}")
        stmt = select(Qualification).where(Qualification.status == status_enum)
    else:
        stmt = select(Qualification).where(Qualification.status == QualStatus.REVIEWING)

    stmt = stmt.order_by(Qualification.submitted_at.asc())
    result = await db.execute(stmt)
    qualifications = result.scalars().all()

    items = [_qualification_to_item(q) for q in qualifications]
    return {"items": items}


# ============================================================================
# Admin: Review Qualification
# ============================================================================
async def admin_review(
    db: AsyncSession,
    qualification_id: int,
    data: ReviewRequest,
    admin_id: int,
) -> Qualification:
    """Approve or reject a qualification. Updates promoter status accordingly."""
    result = await db.execute(
        select(Qualification).where(Qualification.id == qualification_id)
    )
    qual = result.scalars().first()
    if qual is None:
        raise NotFoundException(message="Qualification record not found")

    # Only reviewing qualifications can be reviewed
    if qual.status != QualStatus.REVIEWING:
        raise BadRequestException(
            message=f"Cannot review qualification with status: {qual.status.value}"
        )

    action = data.action.lower()
    if action not in ("approve", "reject"):
        raise BadRequestException(
            message=f"Invalid review action: {data.action}. Must be 'approve' or 'reject'"
        )

    now = datetime.now(timezone.utc)

    if action == "approve":
        qual.status = QualStatus.APPROVED
        qual.approved_at = now
    else:
        qual.status = QualStatus.REJECTED
        qual.rejected_reason = data.comment

    qual.updated_at = now
    db.add(qual)

    # Update promoter status
    promoter_result = await db.execute(
        select(Promoter).where(Promoter.id == qual.promoter_id)
    )
    promoter = promoter_result.scalars().first()
    if promoter is not None:
        promoter.qualification_status = qual.status.value
        db.add(promoter)

    # Create audit log entry
    from ..models.audit import AuditLog

    audit = AuditLog(
        user_id=admin_id,
        action=f"qualification.{action}d",
        entity_type="qualification",
        entity_id=str(qualification_id),
        detail={"comment": data.comment} if data.comment else None,
    )
    db.add(audit)

    await db.flush()
    await db.refresh(qual)

    logger.info(
        "Qualification %s: id=%d by admin=%d", action, qualification_id, admin_id
    )
    return qual


# ============================================================================
# Expiry Check
# ============================================================================
async def check_expiry(db: AsyncSession) -> int:
    """Find qualifications approaching or past expiry and update their status.

    Returns the number of qualifications updated.
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    warning_threshold = now + timedelta(days=30)

    updated = 0

    # Mark expired: expires_at < now
    result = await db.execute(
        select(Qualification).where(
            Qualification.status == QualStatus.APPROVED,
            Qualification.expires_at.isnot(None),
            Qualification.expires_at < now,
        )
    )
    expired = result.scalars().all()
    for q in expired:
        q.status = QualStatus.EXPIRED
        q.updated_at = now
        db.add(q)
        updated += 1

    # Mark expiring: expires_at within 30 days
    result = await db.execute(
        select(Qualification).where(
            Qualification.status == QualStatus.APPROVED,
            Qualification.expires_at.isnot(None),
            Qualification.expires_at.between(now, warning_threshold),
        )
    )
    expiring = result.scalars().all()
    for q in expiring:
        q.status = QualStatus.EXPIRING
        q.updated_at = now
        db.add(q)
        updated += 1

    if updated > 0:
        logger.info("Expiry check: updated %d qualification(s)", updated)

    return updated


# ============================================================================
# Serialization helpers
# ============================================================================
def _qualification_to_item(qual: Qualification) -> dict:
    """Serialize a Qualification model to a response dict."""
    status_val = qual.status.value if hasattr(qual.status, "value") else str(qual.status)
    qual_type_val = (
        qual.qualification_type.value
        if hasattr(qual.qualification_type, "value")
        else str(qual.qualification_type)
    )

    return {
        "qualificationId": str(qual.id),
        "qualificationType": qual_type_val,
        "status": status_val,
        "statusLabel": get_status_label(status_val),
        "fileName": qual.file_name,
        "fileType": qual.file_type,
        "fileSize": qual.file_size,
        "fileId": qual.file_id,
        "version": qual.version,
        "rejectedReason": qual.rejected_reason,
        "submittedAt": qual.submitted_at.isoformat() if qual.submitted_at else None,
        "approvedAt": qual.approved_at.isoformat() if qual.approved_at else None,
        "createdAt": qual.created_at.isoformat() if qual.created_at else None,
        "updatedAt": qual.updated_at.isoformat() if qual.updated_at else None,
    }
