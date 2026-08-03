"""APScheduler tasks for system maintenance.

T116c: qualification_expiry_check_job — runs daily at 09:00.
T191:  idempotency_cleanup_job — runs hourly to clean expired idempotency keys.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from ..core.database import async_session
from ..models.idempotency import IdempotencyKey
from ..models.org_qualification import OrgQualStatus, OrganizationQualification

logger = logging.getLogger(__name__)


async def qualification_expiry_check_job():
    """Check org qualifications expiring within 30 days (FR-008, T043).

    Runs daily at 09:00 via CronTrigger. Org qualifications have no direct
    user to notify; log warnings and rely on
    get_org_business_blocked_reasons() to pause the org's business once
    expired.
    """
    logger.info("Starting org qualification expiry check")

    async with async_session() as db:
        try:
            now = datetime.now(timezone.utc)
            cutoff = now + timedelta(days=30)

            org_expiring = 0
            org_result = await db.execute(
                select(OrganizationQualification).where(
                    OrganizationQualification.status == OrgQualStatus.APPROVED,
                    OrganizationQualification.valid_until.isnot(None),
                    OrganizationQualification.valid_until <= cutoff,
                    OrganizationQualification.valid_until > now,
                )
            )
            for org_qual in org_result.scalars().all():
                org_expiring += 1
                logger.warning(
                    "Org qualification %s for org %s expiring on %s",
                    org_qual.id,
                    org_qual.org_id,
                    org_qual.valid_until.strftime("%Y-%m-%d"),
                )

            await db.commit()
            logger.info(
                "Org qualification expiry check completed: org_expiring=%s",
                org_expiring,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("Org qualification expiry check failed: %s", exc)


async def idempotency_cleanup_job():
    """Clean up expired idempotency keys older than 24 hours (T191).

    Runs hourly via IntervalTrigger.
    """
    logger.info("Starting idempotency key cleanup")

    async with async_session() as db:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

            result = await db.execute(
                delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff)
            )
            await db.commit()

            deleted_count = result.rowcount
            logger.info(
                "Idempotency cleanup completed: deleted=%d keys older than %s",
                deleted_count,
                cutoff.isoformat(),
            )
        except Exception as exc:
            await db.rollback()
            logger.error("Idempotency cleanup failed: %s", exc)
