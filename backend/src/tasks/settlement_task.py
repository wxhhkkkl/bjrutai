"""APScheduler task for monthly contribution settlement.

T116e: monthly_settlement_job — runs on the 1st of each month at 00:05.
Processes pending contributions in batches using SELECT FOR UPDATE SKIP LOCKED.
"""

import logging
from datetime import datetime, timezone

from ..core.database import async_session
from ..services.contribution_service import ContributionService

logger = logging.getLogger(__name__)


async def monthly_settlement_job():
    """Monthly contribution settlement task.

    Triggered on day 1 of each month at 00:05 via CronTrigger.
    Settles all pending contributions from the previous month.
    """
    # Determine previous month
    now = datetime.now(timezone.utc)
    if now.month == 1:
        period = f"{now.year - 1}-12"
    else:
        period = f"{now.year}-{now.month - 1:02d}"

    logger.info("Starting monthly settlement for period %s", period)

    svc = ContributionService()

    async with async_session() as db:
        try:
            result = await svc.batch_settle(db, month=period, batch_size=500)
            await db.commit()
            logger.info(
                "Monthly settlement completed: period=%s settled=%s total=%s",
                period,
                result.get("settled_count"),
                result.get("total_processed"),
            )
        except Exception as exc:
            await db.rollback()
            logger.error("Monthly settlement failed for period %s: %s", period, exc)
            raise
