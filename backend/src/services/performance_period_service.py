"""Single-period coordination; does not modify existing settlement results."""

import re
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..models.bill import Bill
from ..models.binding import Customer
from ..models.mall_consumption import MallConsumption
from ..models.performance_evidence import PerformancePeriodVersion
from ..models.performance_settlement import PerformanceSettlement, SettlementStatus


def period_for_datetime(value: datetime) -> str:
    """Return the legacy UTC bill period for a timestamp."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime("%Y-%m")


async def periods_for_distributors(db, distributor_ids: Iterable[int]) -> set[str]:
    """Find source months whose current personal attribution uses these people."""
    identities = set()
    for identity in distributor_ids:
        try:
            normalized = int(identity)
        except (TypeError, ValueError):
            continue
        if normalized > 0:
            identities.add(normalized)
    identities = sorted(identities)
    if not identities:
        return set()

    effective_distributor = func.coalesce(Bill.attributed_distributor_id, Customer.distributor_id)
    bill_times = (
        (
            await db.execute(
                select(Bill.transaction_time)
                .join(Customer, Customer.id == Bill.customer_id)
                .where(effective_distributor.in_(identities))
            )
        )
        .scalars()
        .all()
    )
    periods = {period_for_datetime(value) for value in bill_times if value is not None}
    mall_periods = (
        (
            await db.execute(
                select(MallConsumption.business_period).where(
                    MallConsumption.attributed_distributor_id.in_(identities),
                    MallConsumption.status == "assigned",
                )
            )
        )
        .scalars()
        .all()
    )
    periods.update(period for period in mall_periods if period)
    return periods


async def bump_unfrozen_periods(db, periods: Iterable[str]) -> set[str]:
    """Lock source months in calendar order and advance only mutable revisions.

    Callers must invoke this before writing the related source, rule, or
    organization rows. Reviewed/frozen periods keep their evidence revision.
    """
    changed: set[str] = set()
    for period in sorted(set(periods)):
        row = await lock_period(db, period)
        if row.status != "open":
            continue
        settlement_status = await db.scalar(
            select(PerformanceSettlement.status).where(PerformanceSettlement.period == period)
        )
        if settlement_status == SettlementStatus.REVIEWED:
            row.status = "frozen"
            continue
        row.revision += 1
        changed.add(period)
    await db.flush()
    return changed


async def bump_distributor_periods(db, distributor_ids: Iterable[int]) -> set[str]:
    periods = await periods_for_distributors(db, distributor_ids)
    return await bump_unfrozen_periods(db, periods)


async def lock_period(db, period):
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", period):
        raise ValueError("invalid performance period")
    query = select(PerformancePeriodVersion).where(PerformancePeriodVersion.period == period)
    # Atomic upsert takes the write lock directly. Multiple duplicate INSERT
    # losers must not retain shared locks and then try to upgrade together.
    if db.get_bind().dialect.name == "mysql":
        statement = mysql_insert(PerformancePeriodVersion).values(
            period=period, revision=0, status="open"
        )
        statement = statement.on_duplicate_key_update(period=period)
    else:
        statement = sqlite_insert(PerformancePeriodVersion).values(
            period=period, revision=0, status="open"
        )
        statement = statement.on_conflict_do_nothing(index_elements=["period"])
    await db.execute(statement)
    return (
        await db.execute(query.with_for_update().execution_options(populate_existing=True))
    ).scalar_one()


async def bump_period(db, period):
    await bump_unfrozen_periods(db, [period])
    row = await db.get(PerformancePeriodVersion, period, populate_existing=True)
    return row
