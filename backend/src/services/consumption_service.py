"""消费金额（业绩贡献）共享计算 helper —— 全系统唯一口径。

业绩贡献 = 消费金额：某分销员在周期内其绑定客户的 PAID 账单 `paid_amount_cent`
之和（分，整数），排除 REFUNDED/CANCELLED。与绩效规则/绩效计算（006/008）
同口径。部分退款（PARTIALLY_REFUNDED）按全额计入（与绩效计算一致）。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.bill import Bill, TransactionStatus
from ..models.binding import Customer
from ..models.distributor import Distributor


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
    if not distributor_ids:
        return {}
    start, end = (period_start_end(period) if period else (None, None))
    effective_distributor = func.coalesce(
        Bill.attributed_distributor_id, Customer.distributor_id
    )
    effective_organization = func.coalesce(
        Bill.attributed_org_id, Distributor.org_id
    )
    stmt = (
        select(effective_distributor, func.coalesce(func.sum(Bill.paid_amount_cent), 0))
        .select_from(Customer)
        .join(Bill, Bill.customer_id == Customer.id)
        .join(Distributor, Distributor.id == Customer.distributor_id)
        .where(
            effective_distributor.in_(distributor_ids),
            Bill.transaction_status.notin_([TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]),
        )
    )
    if organization_ids is not None:
        stmt = stmt.where(effective_organization.in_(organization_ids))
    if start is not None:
        stmt = stmt.where(Bill.transaction_time >= start, Bill.transaction_time < end)
    stmt = stmt.group_by(effective_distributor)
    result = await db.execute(stmt)
    return {int(did): int(amount) for did, amount in result.all()}


async def consumption_by_organization(
    db: AsyncSession,
    organization_ids: set[int],
    period: Optional[str] = None,
) -> dict[int, int]:
    """Aggregate consumption by immutable manual snapshot or current sync owner org."""
    if not organization_ids:
        return {}
    start, end = (period_start_end(period) if period else (None, None))
    effective_organization = func.coalesce(Bill.attributed_org_id, Distributor.org_id)
    stmt = (
        select(effective_organization, func.coalesce(func.sum(Bill.paid_amount_cent), 0))
        .select_from(Customer)
        .join(Bill, Bill.customer_id == Customer.id)
        .join(Distributor, Distributor.id == Customer.distributor_id)
        .where(
            effective_organization.in_(organization_ids),
            Bill.transaction_status.notin_(
                [TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]
            ),
        )
    )
    if start is not None:
        stmt = stmt.where(Bill.transaction_time >= start, Bill.transaction_time < end)
    stmt = stmt.group_by(effective_organization)
    result = await db.execute(stmt)
    return {int(org_id): int(amount) for org_id, amount in result.all()}


async def consumption_by_customer(
    db: AsyncSession,
    customer_ids: list[int],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict[int, int]:
    """{customer_id: total paid consumption in cents}, excluding refunded/cancelled."""
    if not customer_ids:
        return {}
    stmt = (
        select(Bill.customer_id, func.coalesce(func.sum(Bill.paid_amount_cent), 0))
        .where(
            Bill.customer_id.in_(customer_ids),
            Bill.transaction_status.notin_([TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]),
        )
    )
    if start is not None:
        stmt = stmt.where(Bill.transaction_time >= start, Bill.transaction_time < end)
    stmt = stmt.group_by(Bill.customer_id)
    result = await db.execute(stmt)
    return {int(cid): int(amount) for cid, amount in result.all()}
