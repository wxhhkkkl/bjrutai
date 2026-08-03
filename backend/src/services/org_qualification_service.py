"""Organization qualification service (US2)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, NotFoundException
from ..models.org_qualification import (
    OrgQualStatus,
    OrganizationQualification,
)
from ..schemas.org_qualification import (
    OrgQualificationCreate,
    OrgQualificationReview,
)
from . import organization_service


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO/date string into a naive UTC datetime (matching DB storage)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None


def _to_dict(q: OrganizationQualification) -> dict:
    return {
        "qualificationId": str(q.id),
        "orgId": str(q.org_id),
        "legalEntityName": q.legal_entity_name,
        "qualificationTypes": q.qualification_types or [],
        "fileUrls": q.file_urls or [],
        "validFrom": q.valid_from.isoformat() if q.valid_from else None,
        "validUntil": q.valid_until.isoformat() if q.valid_until else None,
        "status": q.status.value if hasattr(q.status, "value") else str(q.status),
        "reviewComment": q.review_comment,
        "reviewedBy": str(q.reviewed_by) if q.reviewed_by else None,
        "reviewedAt": q.reviewed_at.isoformat() if q.reviewed_at else None,
        "createdAt": q.created_at.isoformat() if q.created_at else None,
    }


async def _get_qualification_or_404(db: AsyncSession, qid: int) -> OrganizationQualification:
    result = await db.execute(
        select(OrganizationQualification).where(OrganizationQualification.id == qid)
    )
    q = result.scalars().first()
    if q is None:
        raise NotFoundException(message="Organization qualification not found")
    return q


async def list_qualifications(db: AsyncSession, org_id: int) -> list[dict]:
    """List org qualifications (latest first)."""
    await organization_service._get_org_or_404(db, org_id)
    result = await db.execute(
        select(OrganizationQualification)
        .where(OrganizationQualification.org_id == org_id)
        .order_by(OrganizationQualification.created_at.desc())
    )
    return [_to_dict(q) for q in result.scalars().all()]


async def create_qualification(
    db: AsyncSession,
    org_id: int,
    data: OrgQualificationCreate,
    operator_id: Optional[int] = None,
) -> dict:
    """Upload a new org qualification (status=reviewing)."""
    await organization_service._get_org_or_404(db, org_id)

    valid_from = _parse_dt(data.valid_from)
    valid_until = _parse_dt(data.valid_until)
    if data.valid_until is not None and valid_until is None:
        raise BadRequestException(message="validUntil must be a valid date")
    if valid_until is None:
        # 未提供有效期 → 默认远期（迁移数据同样以 2099-12-31 兜底）
        valid_until = _parse_dt("2099-12-31")
    if valid_from is not None and valid_until < valid_from:
        raise BadRequestException(message="validUntil must not be earlier than validFrom")

    q = OrganizationQualification(
        org_id=org_id,
        legal_entity_name=data.legal_entity_name,
        qualification_types=data.qualification_types,
        credit_code=data.credit_code,
        file_urls=data.file_urls,
        valid_from=valid_from,
        valid_until=valid_until,
        status=OrgQualStatus.REVIEWING,
    )
    db.add(q)
    await db.flush()
    await db.refresh(q)
    return _to_dict(q)


async def review_qualification(
    db: AsyncSession,
    qualification_id: int,
    data: OrgQualificationReview,
    reviewer_id: Optional[int] = None,
) -> dict:
    """Approve or reject an org qualification."""
    q = await _get_qualification_or_404(db, qualification_id)

    action = data.action
    if action not in {"approve", "reject"}:
        raise BadRequestException(message="action must be approve or reject")
    if action == "reject" and not data.comment:
        raise BadRequestException(message="rejection requires a comment")

    q.status = OrgQualStatus.APPROVED if action == "approve" else OrgQualStatus.REJECTED
    q.review_comment = data.comment
    q.reviewed_by = reviewer_id
    q.reviewed_at = datetime.utcnow()
    db.add(q)
    await db.flush()
    await db.refresh(q)
    return _to_dict(q)


async def get_history(db: AsyncSession, org_id: int) -> list[dict]:
    """Return qualification submission/review history for an org (US2-AC6)."""
    return await list_qualifications(db, org_id)
