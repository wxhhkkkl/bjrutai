"""Contribution query service: overview, trend, composition, list, detail.

Queries contribution records for individual promoters. All monetary amounts
are expressed as contribution points only -- no raw money values are exposed.
"""

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import NotFoundException
from ..models.bill import Bill
from ..models.contribution import (
    ContributionCategory,
    ContributionRecord,
    ContributionStatus,
)
from ..models.hierarchy import Promoter
from ..models.user import User


# ---------------------------------------------------------------------------
# Category display labels
# ---------------------------------------------------------------------------
CATEGORY_LABELS = {
    "binding": "绑定贡献",
    "service": "服务贡献",
    "followup": "跟进贡献",
    "bill": "消费贡献",
    "adjustment": "调整贡献",
}


class ContributionQueryService:
    """Query service for promoter contribution views."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _sum_points(records: list[ContributionRecord]) -> str:
        """Sum points from a list of contribution records, excluding reversed/cancelled."""
        total = Decimal("0")
        for r in records:
            if r.status in (ContributionStatus.REVERSED, ContributionStatus.CANCELLED):
                continue
            total += Decimal(r.points)
        return str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @staticmethod
    async def _get_promoter(db: AsyncSession, user_id: int) -> Promoter:
        """Get promoter by user_id, raising 404 if not found."""
        result = await db.execute(
            select(Promoter).where(Promoter.user_id == user_id)
        )
        promoter = result.scalars().first()
        if promoter is None:
            raise NotFoundException(message="Promoter not found")
        return promoter

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------
    async def get_overview(
        self,
        db: AsyncSession,
        user_id: int,
        month: str,
    ) -> dict:
        """Get contribution overview for a promoter.

        Returns monthlyPoints, totalPoints, growthRate, and statusCounts.
        """
        promoter = await self._get_promoter(db, user_id)

        # Monthly contributions
        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.promoter_id == promoter.id,
                func.strftime("%Y-%m", ContributionRecord.occurred_at) == month,
            )
        )
        monthly_records = result.scalars().all()

        monthly_points = self._sum_points(monthly_records)
        monthly_points_dec = Decimal(monthly_points)

        # Total contributions (all time)
        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.promoter_id == promoter.id,
            )
        )
        all_records = result.scalars().all()
        total_points = self._sum_points(all_records)

        # Growth rate: compare with previous month
        prev_month = _previous_month(month)
        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.promoter_id == promoter.id,
                func.strftime("%Y-%m", ContributionRecord.occurred_at) == prev_month,
            )
        )
        prev_records = result.scalars().all()
        prev_points = Decimal(self._sum_points(prev_records))

        growth_rate = None
        if prev_points > 0 and monthly_points_dec > 0:
            growth_rate = float(
                ((monthly_points_dec - prev_points) / prev_points * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )

        # Status counts for the month
        status_counts = {}
        for r in monthly_records:
            s = r.status.value if hasattr(r.status, "value") else str(r.status)
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "monthlyPoints": monthly_points,
            "totalPoints": total_points,
            "growthRate": growth_rate,
            "statusCounts": status_counts,
        }

    # ------------------------------------------------------------------
    # Trend
    # ------------------------------------------------------------------
    async def get_trend(
        self,
        db: AsyncSession,
        user_id: int,
        period: str = "6m",
    ) -> dict:
        """Get monthly contribution trend for the last N months.

        Returns categories (month labels) and values (points per month).
        """
        promoter = await self._get_promoter(db, user_id)

        # Parse period
        num_months = _parse_period(period)

        # Generate month labels (past N months including current)
        months = _generate_month_labels(num_months)

        # Query all records for the promoter
        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.promoter_id == promoter.id,
            )
        )
        all_records = result.scalars().all()

        # Aggregate by month
        month_points: dict[str, Decimal] = {m: Decimal("0") for m in months}
        for r in all_records:
            if r.status in (ContributionStatus.REVERSED, ContributionStatus.CANCELLED):
                continue
            m = r.occurred_at.strftime("%Y-%m")
            if m in month_points:
                month_points[m] += Decimal(r.points)

        categories = months
        values = [
            str(month_points[m].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            for m in months
        ]

        return {
            "categories": categories,
            "values": values,
        }

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------
    async def get_composition(
        self,
        db: AsyncSession,
        user_id: int,
        month: str,
    ) -> dict:
        """Get contribution composition breakdown by category for a month.

        Returns list of categories with label, points, and percent.
        """
        promoter = await self._get_promoter(db, user_id)

        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.promoter_id == promoter.id,
                func.strftime("%Y-%m", ContributionRecord.occurred_at) == month,
            )
        )
        monthly_records = result.scalars().all()

        # Aggregate by category
        cat_points: dict[str, Decimal] = {}
        for r in monthly_records:
            if r.status in (ContributionStatus.REVERSED, ContributionStatus.CANCELLED):
                continue
            c = r.category.value if hasattr(r.category, "value") else str(r.category)
            cat_points[c] = cat_points.get(c, Decimal("0")) + Decimal(r.points)

        total = sum(cat_points.values(), Decimal("0"))

        categories = []
        for cat, pts in sorted(cat_points.items()):
            percent = float((pts / total * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if total > 0 else 0.0
            categories.append({
                "label": CATEGORY_LABELS.get(cat, cat),
                "category": cat,
                "points": str(pts.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "percent": percent,
            })

        return {"categories": categories}

    # ------------------------------------------------------------------
    # List (cursor-paginated)
    # ------------------------------------------------------------------
    async def list_details(
        self,
        db: AsyncSession,
        user_id: int,
        month: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        cursor: Optional[str] = None,
        page_size: int = 20,
    ) -> dict:
        """List contribution records with cursor pagination and filters."""
        promoter = await self._get_promoter(db, user_id)

        conditions = [ContributionRecord.promoter_id == promoter.id]

        if month:
            conditions.append(func.strftime("%Y-%m", ContributionRecord.occurred_at) == month)
        if status:
            conditions.append(ContributionRecord.status == status)
        if category:
            conditions.append(ContributionRecord.category == category)
        if cursor:
            conditions.append(ContributionRecord.id < int(cursor))

        query = (
            select(ContributionRecord)
            .where(and_(*conditions))
            .order_by(ContributionRecord.id.desc())
            .limit(page_size + 1)
        )

        result = await db.execute(query)
        records = result.scalars().all()

        has_more = len(records) > page_size
        if has_more:
            records = records[:page_size]

        items = []
        for r in records:
            items.append({
                "id": r.id,
                "title": r.title,
                "points": r.points,
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "category": r.category.value if hasattr(r.category, "value") else str(r.category),
                "sourceType": r.source_type,
                "occurredAt": r.occurred_at.isoformat() if r.occurred_at else None,
                "settledAt": r.settled_at.isoformat() if r.settled_at else None,
            })

        next_cursor = str(records[-1].id) if has_more and records else None

        return {
            "items": items,
            "nextCursor": next_cursor,
            "hasMore": has_more,
        }

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------
    async def get_detail(
        self,
        db: AsyncSession,
        contribution_id: int,
    ) -> dict:
        """Get full detail of a contribution record including calculation info."""
        result = await db.execute(
            select(ContributionRecord).where(ContributionRecord.id == contribution_id)
        )
        record = result.scalars().first()
        if record is None:
            raise NotFoundException(message="Contribution record not found")

        # Build calculation info from the record and its bill
        calculation_base = None
        calculation_description = None

        if record.bill_id:
            bill_result = await db.execute(
                select(Bill).where(Bill.id == record.bill_id)
            )
            bill = bill_result.scalars().first()
            if bill:
                # Convert cents to yuan string
                base_yuan = Decimal(bill.paid_amount_cent) / Decimal(100)
                calculation_base = str(base_yuan.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        # Build calculation description
        coefficient = record.rule_version or "1.0"
        if calculation_base and record.points:
            calculation_description = f"({calculation_base} x {coefficient}) = {record.points}"
        elif record.points:
            calculation_description = f"Points: {record.points}"

        return {
            "id": record.id,
            "title": record.title,
            "points": record.points,
            "status": record.status.value if hasattr(record.status, "value") else str(record.status),
            "category": record.category.value if hasattr(record.category, "value") else str(record.category),
            "sourceType": record.source_type,
            "sourceId": record.source_id,
            "calculationBase": calculation_base,
            "coefficient": coefficient,
            "calculationDescription": calculation_description,
            "adjustmentReason": record.adjustment_reason,
            "occurredAt": record.occurred_at.isoformat() if record.occurred_at else None,
            "settledAt": record.settled_at.isoformat() if record.settled_at else None,
            "createdAt": record.created_at.isoformat() if record.created_at else None,
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------
def _previous_month(month: str) -> str:
    """Return the previous month string (e.g. '2026-06' -> '2026-05')."""
    year, mon = month.split("-")
    y, m = int(year), int(mon)
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def _parse_period(period: str) -> int:
    """Parse period string like '6m', '12m', '3m' to number of months."""
    if period.endswith("m"):
        try:
            n = int(period[:-1])
            return max(1, min(n, 24))  # clamp 1-24
        except ValueError:
            pass
    return 6  # default


def _generate_month_labels(num_months: int) -> list[str]:
    """Generate month labels for the past N months (including current)."""
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
