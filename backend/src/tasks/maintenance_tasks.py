"""APScheduler tasks for system maintenance.

T116c: qualification_expiry_check_job — runs daily at 09:00.
T191:  idempotency_cleanup_job — runs hourly to clean expired idempotency keys.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from ..core.database import async_session
from ..models.idempotency import IdempotencyKey
from ..models.notification import Notification, NotificationCategory
from ..models.qualification import QualStatus, Qualification
from ..models.org_qualification import OrgQualStatus, OrganizationQualification

logger = logging.getLogger(__name__)


async def qualification_expiry_check_job():
    """Check for qualifications expiring within 30 days and send notifications.

    Runs daily at 09:00 via CronTrigger.
    """
    logger.info("Starting qualification expiry check")

    async with async_session() as db:
        try:
            now = datetime.now(timezone.utc)
            cutoff = now + timedelta(days=30)

            # Find approved qualifications expiring within 30 days
            result = await db.execute(
                select(Qualification).where(
                    Qualification.status == QualStatus.APPROVED,
                    Qualification.expires_at.isnot(None),
                    Qualification.expires_at <= cutoff,
                    Qualification.expires_at > now,
                )
            )
            expiring = result.scalars().all()

            notifications_sent = 0
            for qual in expiring:
                days_left = (qual.expires_at - now).days

                # Send notification to the promoter
                notification = Notification(
                    user_id=qual.promoter_id,
                    category=NotificationCategory.QUALIFICATION,
                    title="资质即将过期",
                    summary=(
                        f"您的资质即将在 {days_left} 天后过期（过期日期："
                        f"{qual.expires_at.strftime('%Y-%m-%d')}）。"
                        f"请及时更新资质信息。"
                    ),
                )
                db.add(notification)
                notifications_sent += 1

            # ── Org qualification expiry (T043) ──────────────────────────
            # Org qualifications have no direct user to notify; log warnings
            # and rely on get_org_business_blocked_reasons() to pause the
            # org's business once expired (FR-008).
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
                "Qualification expiry check completed: expiring=%s notifications=%s org_expiring=%s",
                len(expiring),
                notifications_sent,
                org_expiring,
            )
        except Exception as exc:
            await db.rollback()
            logger.error("Qualification expiry check failed: %s", exc)


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
