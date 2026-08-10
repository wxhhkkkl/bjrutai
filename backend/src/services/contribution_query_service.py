"""消费业绩查询服务（业绩贡献 = 消费金额）：overview / trend / list / detail。

按账单（Bill.paid_amount_cent）实时统计，金额单位为分（整数）。分类构成
（composition）已随「业绩贡献值」概念移除。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import NotFoundException
from ..models.bill import Bill
from ..models.binding import Customer
from ..models.distributor import Distributor
from .consumption_service import consumption_by_distributor, period_start_end


class ConsumptionQueryService:
    """Query service for promoter 消费业绩 views."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _get_promoter(db: AsyncSession, user_id: int) -> Distributor:
        result = await db.execute(select(Distributor).where(Distributor.user_id == user_id))
        promoter = result.scalars().first()
        if promoter is None:
            raise NotFoundException(message="Distributor not found")
        return promoter

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------
    async def get_overview(self, db: AsyncSession, user_id: int, month: str) -> dict:
        """Monthly / total consumption (cents) + growth rate."""
        promoter = await self._get_promoter(db, user_id)
        monthly = (await consumption_by_distributor(db, [promoter.id], month)).get(promoter.id, 0)
        total = (await consumption_by_distributor(db, [promoter.id], None)).get(promoter.id, 0)
        prev = (await consumption_by_distributor(db, [promoter.id], _previous_month(month))).get(promoter.id, 0)

        growth_rate = None
        if prev > 0 and monthly > 0:
            growth_rate = float(((monthly - prev) / prev) * 100)
        return {
            "monthlyAmountCent": monthly,
            "totalAmountCent": total,
            "growthRate": growth_rate,
        }

    # ------------------------------------------------------------------
    # Trend
    # ------------------------------------------------------------------
    async def get_trend(self, db: AsyncSession, user_id: int, period: str = "6m") -> dict:
        """Monthly consumption trend for the last N months (cents)."""
        promoter = await self._get_promoter(db, user_id)
        months = _generate_month_labels(_parse_period(period))
        values = []
        for m in months:
            values.append((await consumption_by_distributor(db, [promoter.id], m)).get(promoter.id, 0))
        return {"categories": months, "values": values}

    # ------------------------------------------------------------------
    # List (cursor-paginated bills)
    # ------------------------------------------------------------------
    async def list_details(
        self,
        db: AsyncSession,
        user_id: int,
        month: Optional[str] = None,
        status: Optional[str] = None,
        cursor: Optional[str] = None,
        page_size: int = 20,
    ) -> dict:
        promoter = await self._get_promoter(db, user_id)
        conditions = [Customer.distributor_id == promoter.id]
        if month:
            start, end = period_start_end(month)
            conditions.append(Bill.transaction_time >= start)
            conditions.append(Bill.transaction_time < end)
        if status:
            conditions.append(Bill.transaction_status == status)
        if cursor:
            conditions.append(Bill.id < int(cursor))

        query = (
            select(Bill, Customer.name, Customer.phone_masked)
            .join(Customer, Customer.id == Bill.customer_id)
            .where(and_(*conditions))
            .order_by(Bill.id.desc())
            .limit(page_size + 1)
        )
        rows = (await db.execute(query)).all()
        has_more = len(rows) > page_size
        if has_more:
            rows = rows[:page_size]

        items = []
        for bill, cust_name, phone_masked in rows:
            items.append(_serialize_bill(bill, cust_name, phone_masked))
        next_cursor = str(rows[-1][0].id) if has_more and rows else None
        return {"items": items, "nextCursor": next_cursor, "hasMore": has_more}

    # ------------------------------------------------------------------
    # Detail (bill)
    # ------------------------------------------------------------------
    async def get_detail(self, db: AsyncSession, bill_id: int, user_id: int) -> dict:
        promoter = await self._get_promoter(db, user_id)
        row = (
            await db.execute(
                select(Bill, Customer.name, Customer.phone_masked)
                .join(Customer, Customer.id == Bill.customer_id)
                .where(Bill.id == bill_id, Customer.distributor_id == promoter.id)
            )
        ).first()
        if row is None:
            raise NotFoundException(message="消费记录不存在")
        bill, cust_name, phone_masked = row
        detail = _serialize_bill(bill, cust_name, phone_masked)
        detail["refundAmountCent"] = bill.refund_amount_cent
        return detail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _serialize_bill(
    bill: Bill,
    customer_name: Optional[str],
    phone_masked: Optional[str] = None,
) -> dict:
    return {
        "id": bill.id,
        "title": bill.transaction_id,
        "amountCent": bill.paid_amount_cent,
        "status": bill.transaction_status.value if hasattr(bill.transaction_status, "value") else str(bill.transaction_status),
        "occurredAt": bill.transaction_time.isoformat() if bill.transaction_time else None,
        "customerName": customer_name,
        "phoneMasked": phone_masked,
    }


def _previous_month(month: str) -> str:
    year, mon = month.split("-")
    y, m = int(year), int(mon)
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def _parse_period(period: str) -> int:
    if period.endswith("m"):
        try:
            n = int(period[:-1])
            return max(1, min(n, 24))
        except ValueError:
            pass
    return 6


def _generate_month_labels(num_months: int) -> list[str]:
    now = datetime.now(timezone.utc)
    months = []
    for i in range(num_months - 1, -1, -1):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}")
    return months
