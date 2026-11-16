"""Compatibility entry points for the unified contribution projection.

Legacy bills retain their paid-amount, attribution and refund semantics. Mall
orders remain a distinct source and contribute only their goods performance
base in the Beijing payment month.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


def period_start_end(period: str) -> tuple[datetime, datetime]:
    """'YYYY-MM' -> [start, end) datetimes."""
    year, month = (int(x) for x in period.split("-"))
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def _current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


async def consumption_by_distributor(
    db: AsyncSession,
    distributor_ids: list[int],
    period: Optional[str] = None,
    organization_ids: Optional[set[int]] = None,
) -> dict[int, int]:
    """{distributor_id: total paid consumption in cents} for a period
    (or all-time when period is None), excluding refunded/cancelled bills."""
    from .consumption_projection_service import ConsumptionProjectionService

    return await ConsumptionProjectionService().aggregate_by_distributor(
        db,
        distributor_ids,
        month=period,
        organization_ids=organization_ids,
    )


async def consumption_by_organization(
    db: AsyncSession,
    organization_ids: set[int],
    period: Optional[str] = None,
) -> dict[int, int]:
    """Aggregate consumption by immutable manual snapshot or current sync owner org."""
    from .consumption_projection_service import ConsumptionProjectionService

    return await ConsumptionProjectionService().aggregate_by_organization(
        db, organization_ids, month=period
    )


async def consumption_by_customer(
    db: AsyncSession,
    customer_ids: list[int],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict[int, int]:
    """{customer_id: total paid consumption in cents}, excluding refunded/cancelled."""
    from .consumption_projection_service import ConsumptionProjectionService

    return await ConsumptionProjectionService().aggregate_by_customer(
        db, customer_ids, start=start, end=end
    )
