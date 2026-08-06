"""Customer analysis endpoints (T176).

GET /customer-analysis?period=30d – overview counts, trend data, source distribution
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.deps import get_current_user, get_db
from ...models.binding import BindingRequest, BindingRequestStatus, BindingStatus, Customer, OperationType, SourceType
from ...models.distributor import Distributor

router = APIRouter(prefix="/customer-analysis", tags=["customer-analysis"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


async def _get_promoter(db: AsyncSession, user_id: int) -> Optional[Distributor]:
    result = await db.execute(select(Distributor).where(Distributor.user_id == user_id))
    return result.scalars().first()


def _parse_period(period: str) -> datetime:
    """Parse a period string like 7d, 30d, 90d, 1y into a start datetime."""
    now = datetime.now(timezone.utc)
    value = period[:-1]
    unit = period[-1:].lower()
    try:
        val = int(value)
    except (ValueError, TypeError):
        val = 30
        unit = "d"

    if unit == "d":
        return now - timedelta(days=val)
    elif unit == "m":
        return now - timedelta(days=val * 30)
    elif unit == "y":
        return now - timedelta(days=val * 365)
    else:
        return now - timedelta(days=30)


# ──────────────────────────────────────────────────────────────────
# GET /customer-analysis
# ──────────────────────────────────────────────────────────────────
@router.get("")
async def get_customer_analysis(
    period: str = Query("30d", description="Analysis period: 7d, 30d, 90d, 1y"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Return customer analysis overview with counts, trend data, and source distribution."""
    user_id = int(payload["sub"])
    user_type = payload.get("user_type", "promoter")
    start_date = _parse_period(period)

    if user_type == "admin":
        promoter_filter = None
    else:
        promoter = await _get_promoter(db, user_id)
        if promoter is None:
            return _ok({
                "period": period,
                "overview": {"totalCustomers": 0, "boundCustomers": 0, "newCustomers": 0},
                "trend": [],
                "sourceDistribution": [],
            })
        promoter_filter = promoter.id

    # --- Overview counts ---
    customer_base = select(func.count(Customer.id))
    if promoter_filter is not None:
        customer_base = customer_base.where(Customer.distributor_id == promoter_filter)

    total_result = await db.execute(customer_base)
    total_customers = total_result.scalar() or 0

    bound_base = select(func.count(Customer.id)).where(Customer.binding_status == BindingStatus.BOUND)
    if promoter_filter is not None:
        bound_base = bound_base.where(Customer.distributor_id == promoter_filter)
    bound_result = await db.execute(bound_base)
    bound_customers = bound_result.scalar() or 0

    new_base = select(func.count(Customer.id)).where(Customer.created_at >= start_date)
    if promoter_filter is not None:
        new_base = new_base.where(Customer.distributor_id == promoter_filter)
    new_result = await db.execute(new_base)
    new_customers = new_result.scalar() or 0

    # --- Trend data (monthly buckets within the period) ---
    trend = []
    now = datetime.now(timezone.utc)
    months_to_check = max(1, (now.year - start_date.year) * 12 + (now.month - start_date.month) + 1)
    for i in range(min(months_to_check, 12)):
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        if now.month - i <= 0:
            year_adj = (abs(now.month - i - 1) // 12) + 1
            adjusted_month = ((now.month - i - 1) % 12) + 1
            month_start = datetime(now.year - year_adj, adjusted_month, 1, tzinfo=timezone.utc)
        else:
            month_start = datetime(now.year, now.month - i, 1, tzinfo=timezone.utc)

        if now.month == 12 and i > 0:
            # End edge case for Dec
            month_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc) if i > now.month else None
        else:
            month_end = datetime(now.year, now.month - i + 1, 1, tzinfo=timezone.utc) if now.month - i + 1 <= 12 else datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)

        if month_end is None:
            continue

        # Recalculate properly
        current = now.month - i
        if current <= 0:
            current += 12
        m_start = datetime(now.year if now.month - i > 0 else now.year - 1, current, 1, tzinfo=timezone.utc)
        if current == 12:
            m_end = datetime(now.year if now.month - i > 0 else now.year, 1, 1, tzinfo=timezone.utc)
        else:
            m_end_year = now.year if now.month - i > 0 else now.year - 1
            m_end = datetime(m_end_year, current + 1, 1, tzinfo=timezone.utc)

        trend_query_base = select(func.count(Customer.id)).where(
            Customer.created_at >= m_start,
            Customer.created_at < m_end,
        )
        if promoter_filter is not None:
            trend_query_base = trend_query_base.where(Customer.distributor_id == promoter_filter)

        trend_result = await db.execute(trend_query_base)
        count = trend_result.scalar() or 0

        trend.append({
            "month": m_start.strftime("%Y-%m"),
            "newCustomers": count,
        })

    # Reverse to chronological order
    trend.reverse()

    # --- Source distribution ---
    source_query = select(
        BindingRequest.source_type,
        func.count(BindingRequest.id),
    )
    if promoter_filter is not None:
        source_query = source_query.where(BindingRequest.distributor_id == promoter_filter)
    source_query = source_query.where(
        BindingRequest.created_at >= start_date,
    ).group_by(BindingRequest.source_type)

    source_result = await db.execute(source_query)
    source_dist = []
    for row in source_result:
        st = row[0]
        source_dist.append({
            "source": st.value if hasattr(st, "value") else str(st),
            "count": row[1] or 0,
        })

    return _ok({
        "period": period,
        "overview": {
            "totalCustomers": total_customers,
            "boundCustomers": bound_customers,
            "newCustomers": new_customers,
        },
        "trend": trend,
        "sourceDistribution": source_dist,
    })
