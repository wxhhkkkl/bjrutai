"""APScheduler tasks for data synchronization.

T116a: sync_bind_users_job — polls getBindUser every 60 seconds (coalesce=True)
T116b: sync_user_bills_job — processes bill fetch queue after new bindings
T116d: retry_failed_sync_job — retries failed sync operations every 10 minutes
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import async_session
from ..models.binding import Customer
from ..services.sync_service import _get_state, _update_state, get_sync_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# T116a: Bind user polling — every 60 seconds
# ---------------------------------------------------------------------------
async def sync_bind_users_job():
    """Poll Rutai getBindUser endpoint and import new customers.

    Runs every 60 seconds. Uses coalesce=True to skip if previous
    invocation is still running.
    """
    svc = get_sync_service()

    async with async_session() as db:
        try:
            result = await svc.poll_bind_users(db)
            await db.commit()
            logger.info(
                "Bind user sync completed: processed=%s imported=%s pages=%s",
                result.get("processed"),
                result.get("imported"),
                result.get("pages"),
            )
        except Exception as exc:
            await db.rollback()
            logger.error("Bind user sync failed: %s", exc)


# ---------------------------------------------------------------------------
# T116b: User bill fetch — triggered after new bindings
# ---------------------------------------------------------------------------
async def sync_user_bills_job():
    """Fetch bills for all bound customers that need updating.

    Processes the bill fetch queue: queries all customers with
    rutai_user_id set and fetches their bills.
    """
    svc = get_sync_service()

    async with async_session() as db:
        try:
            # Find customers with Rutai user IDs
            result = await db.execute(
                select(Customer).where(
                    Customer.rutai_user_id.isnot(None),
                    Customer.rutai_user_id != "",
                )
            )
            customers = result.scalars().all()

            total_created = 0
            total_skipped = 0
            total_refunds = 0

            for customer in customers:
                try:
                    bill_result = await svc.fetch_user_bill(db, customer.rutai_user_id)
                    total_created += bill_result.get("created", 0)
                    total_skipped += bill_result.get("skipped", 0)
                    total_refunds += bill_result.get("refunds_processed", 0)
                except Exception as exc:
                    logger.warning(
                        "Bill sync failed for user %s: %s",
                        customer.rutai_user_id,
                        exc,
                    )

            await db.commit()
            logger.info(
                "User bill sync completed: created=%s skipped=%s refunds=%s users=%s",
                total_created,
                total_skipped,
                total_refunds,
                len(customers),
            )
        except Exception as exc:
            await db.rollback()
            logger.error("User bill sync failed: %s", exc)


async def trigger_bill_sync_for_new_bindings(db: AsyncSession):
    """Helper: sync bills for newly-bound customers (used after polling)."""
    svc = get_sync_service()

    # Find customers without bill data (rough heuristic)
    result = await db.execute(
        select(Customer).where(
            Customer.rutai_user_id.isnot(None),
            Customer.rutai_user_id != "",
        )
    )
    customers = result.scalars().all()

    for customer in customers:
        try:
            await svc.fetch_user_bill(db, customer.rutai_user_id)
        except Exception as exc:
            logger.warning(
                "Bill sync for new binding %s failed: %s",
                customer.rutai_user_id,
                exc,
            )


# ---------------------------------------------------------------------------
# T116d: Retry failed sync — every 10 minutes
# ---------------------------------------------------------------------------
async def retry_failed_sync_job():
    """Retry failed sync operations every 10 minutes.

    Resets failure count and attempts a fresh bind user poll.
    """
    state = _get_state()
    if state["failure_count"] == 0:
        return

    logger.info("Retrying failed sync (failure_count=%s)", state["failure_count"])

    # Reset state for retry
    _update_state(failure_count=0, pending_retries=0)

    svc = get_sync_service()

    async with async_session() as db:
        try:
            result = await svc.poll_bind_users(db)
            await db.commit()
            logger.info("Retry sync succeeded: %s", result)
        except Exception as exc:
            await db.rollback()
            _update_state(
                failure_count=state["failure_count"] + 1,
                pending_retries=1,
            )
            logger.error("Retry sync failed: %s", exc)
