"""APScheduler task for monthly performance settlement.

T116e: monthly_settlement_job — runs on the 1st of each month at 00:05.
Compute commissions for the previous month from performance rules
(业绩贡献 = 消费金额，直接按账单统计，无需贡献记录结算).
"""

import logging
from datetime import datetime, timezone

from ..core.database import async_session

logger = logging.getLogger(__name__)


async def monthly_settlement_job():
    """Monthly commission settlement task.

    Triggered on day 1 of each month at 00:05 via CronTrigger.
    """
    # Determine previous month
    now = datetime.now(timezone.utc)
    if now.month == 1:
        period = f"{now.year - 1}-12"
    else:
        period = f"{now.year}-{now.month - 1:02d}"

    logger.info("Starting monthly settlement for period %s", period)

    async with async_session() as db:
        # FR-013: compute commissions from performance rules after settlement.
        try:
            from ..services.commission_service import compute_commission
            from ..services.report_service import ReportService

            result = await compute_commission(db, period)
            # 010 FR-005: auto-generated settlement report record for the period
            await ReportService.ensure_settlement_report(db, period, "pending")
            await db.commit()
            logger.info("Commission computed for period %s: %s", period, result)
        except Exception as exc:
            await db.rollback()
            logger.error("Commission computation failed for period %s: %s", period, exc)
