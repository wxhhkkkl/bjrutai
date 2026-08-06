"""Workbench / dashboard endpoints (T172).

GET /workbench                   – role-based dashboard (promoter/doctor views)
GET /workbench/notices            – qualification, binding, system notices
GET /workbench/recent-bindings    – recent 5 binding records
GET /workbench/contribution-summary – monthly contribution summary
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ...api.deps import get_current_user, get_db
from ...models.binding import BindingRequest, BindingRequestStatus, BindingStatus, Customer
from ...models.bill import Bill, TransactionStatus
from ...models.distributor import Distributor
from ...models.notification import Notification, NotificationCategory
from ...models.org_qualification import OrgQualStatus, OrganizationQualification
from ...models.user import User, UserType

router = APIRouter(prefix="/workbench", tags=["workbench"])


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


# ──────────────────────────────────────────────────────────────────
# GET /workbench
# ──────────────────────────────────────────────────────────────────
@router.get("")
async def get_workbench(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Return role-based dashboard data."""
    user_id = int(payload["sub"])
    user_type = payload.get("user_type", "promoter")

    if user_type in ("admin", "finance", "ops"):
        # Admin view: system-level metrics
        total_promoters_result = await db.execute(
            select(func.count(Distributor.id))
        )
        total_promoters = total_promoters_result.scalar() or 0

        pending_qual_result = await db.execute(
            select(func.count(OrganizationQualification.id)).where(
                OrganizationQualification.status == OrgQualStatus.REVIEWING
            )
        )
        pending_qualifications = pending_qual_result.scalar() or 0

        # Sync status: pending/abnormal bindings
        abnormal_bindings_result = await db.execute(
            select(func.count(BindingRequest.id)).where(
                BindingRequest.status.in_([
                    BindingRequestStatus.ABNORMAL,
                    BindingRequestStatus.RETRYING,
                ])
            )
        )
        abnormal_bindings = abnormal_bindings_result.scalar() or 0

        # Total customers
        total_customers_result = await db.execute(
            select(func.count(Customer.id))
        )
        total_customers = total_customers_result.scalar() or 0

        return _ok({
            "role": user_type,
            "metrics": {
                "totalPromoters": total_promoters,
                "pendingQualifications": pending_qualifications,
                "abnormalBindings": abnormal_bindings,
                "totalCustomers": total_customers,
            },
            "quickLinks": [
                {"label": "组织人员管理", "path": "/org"},
                {"label": "绑定管理", "path": "/customers/binding"},
            ],
        })

    # Distributor / Doctor view
    promoter = await _get_promoter(db, user_id)
    if promoter is None:
        # Minimal workbench for users without promoter profile
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalars().first()
        return _ok({
            "role": user_type,
            "metrics": {
                "myCustomers": 0,
                "myBindings": 0,
                "myMonthlyConsumption": 0,
                "pendingFollowups": 0,
            },
            "quickLinks": [
                {"label": "客户管理", "path": "/customers"},
                {"label": "我的业绩", "path": "/contributions"},
            ],
            "welcomeMessage": f"欢迎回来，{user.name or '用户'}",
        })

    prom_id = promoter.id

    # My customers count
    customer_count_result = await db.execute(
        select(func.count(Customer.id)).where(Customer.distributor_id == prom_id)
    )
    my_customers = customer_count_result.scalar() or 0

    # My bindings this month
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    bindings_result = await db.execute(
        select(func.count(BindingRequest.id)).where(
            BindingRequest.distributor_id == prom_id,
            BindingRequest.created_at >= month_start,
        )
    )
    my_bindings = bindings_result.scalar() or 0

    # 本月消费金额（业绩贡献 = 消费金额，分）
    from ...services.consumption_service import consumption_by_distributor

    my_consumption = (await consumption_by_distributor(
        db, [prom_id], f"{now.year}-{now.month:02d}"
    )).get(prom_id, 0)

    # Pending followups
    from ...models.followup import FollowupRecord, ReminderStatus
    followup_result = await db.execute(
        select(func.count(FollowupRecord.id)).where(
            FollowupRecord.customer.has(Customer.distributor_id == prom_id),
            FollowupRecord.reminder_status == ReminderStatus.PENDING,
        )
    )
    pending_followups = followup_result.scalar() or 0

    # Welcome message
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    welcome = f"欢迎回来，{user.name or '用户'}" if user else "欢迎使用北京儒泰分销管理系统"

    return _ok({
        "role": user_type,
        "metrics": {
            "myCustomers": my_customers,
            "myBindings": my_bindings,
            "myMonthlyConsumption": my_consumption,
            "pendingFollowups": pending_followups,
        },
        "quickLinks": [
            {"label": "客户管理", "path": "/customers"},
            {"label": "我的业绩", "path": "/contributions"},
            {"label": "推广码", "path": "/promotions"},
        ],
        "welcomeMessage": welcome,
    })


# ──────────────────────────────────────────────────────────────────
# GET /workbench/notices
# ──────────────────────────────────────────────────────────────────
@router.get("/notices")
async def get_notices(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Return qualification, binding, and system notices for the current user."""
    user_id = int(payload["sub"])
    user_type = payload.get("user_type", "promoter")

    notices = []

    if user_type != "admin":
        promoter = await _get_promoter(db, user_id)
        if promoter:
            # Binding notices
            binding_result = await db.execute(
                select(BindingRequest).where(
                    BindingRequest.distributor_id == promoter.id,
                ).order_by(BindingRequest.updated_at.desc()).limit(3)
            )
            bindings = binding_result.scalars().all()
            for br in bindings:
                notices.append({
                    "type": "binding",
                    "title": f"绑定请求: {br.status.value}",
                    "summary": f"客户 {br.customer_name or '未知'} 的绑定请求状态更新",
                    "time": br.updated_at.isoformat() if br.updated_at else None,
                })

    # System notices
    sys_result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,
        ).order_by(Notification.created_at.desc()).limit(5)
    )
    sys_notifs = sys_result.scalars().all()
    for n in sys_notifs:
        notices.append({
            "type": "system",
            "title": n.title,
            "summary": n.summary,
            "time": n.created_at.isoformat() if n.created_at else None,
        })

    return _ok({
        "notices": notices,
    })


# ──────────────────────────────────────────────────────────────────
# GET /workbench/recent-bindings
# ──────────────────────────────────────────────────────────────────
@router.get("/recent-bindings")
async def get_recent_bindings(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Return recent 5 binding records for the current promoter."""
    user_id = int(payload["sub"])
    user_type = payload.get("user_type", "promoter")

    if user_type == "admin":
        query = select(BindingRequest).order_by(BindingRequest.created_at.desc()).limit(5)
    else:
        promoter = await _get_promoter(db, user_id)
        if promoter is None:
            return _ok({"items": []})
        query = (
            select(BindingRequest)
            .where(BindingRequest.distributor_id == promoter.id)
            .order_by(BindingRequest.created_at.desc())
            .limit(5)
        )

    result = await db.execute(query)
    rows = result.scalars().all()

    items = []
    for br in rows:
        items.append({
            "id": str(br.id),
            "customerName": br.customer_name or "未知",
            "phoneMasked": br.phone_masked,
            "status": br.status.value if hasattr(br.status, "value") else str(br.status),
            "sourceType": br.source_type.value if hasattr(br.source_type, "value") else str(br.source_type),
            "boundAt": br.bound_at.isoformat() if br.bound_at else None,
            "createdAt": br.created_at.isoformat() if br.created_at else None,
        })

    return _ok({"items": items})


# ──────────────────────────────────────────────────────────────────
# GET /workbench/contribution-summary
# ──────────────────────────────────────────────────────────────────
@router.get("/contribution-summary")
async def get_contribution_summary(
    month: Optional[str] = Query(None, description="YYYY-MM, defaults to current month"),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Monthly contribution summary for the current promoter."""
    user_id = int(payload["sub"])
    user_type = payload.get("user_type", "promoter")

    now = datetime.now(timezone.utc)
    if month:
        try:
            year, mon = month.split("-")
            target_month_start = datetime(int(year), int(mon), 1, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            target_month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    else:
        target_month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    if now.month == 12:
        target_month_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        target_month_end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    from ...services.consumption_service import consumption_by_distributor

    period = month or now.strftime("%Y-%m")
    paid_cond = (
        Bill.transaction_time >= target_month_start,
        Bill.transaction_time < target_month_end,
        Bill.transaction_status.notin_([TransactionStatus.REFUNDED, TransactionStatus.CANCELLED]),
    )

    if user_type == "admin":
        # Admin: total system consumption
        dist_ids = (await db.execute(select(Distributor.id))).scalars().all()
        total = sum((await consumption_by_distributor(db, list(dist_ids), period)).values())
        count = (await db.execute(
            select(func.count(Bill.id)).where(*paid_cond)
        )).scalar() or 0
        return _ok({"month": period, "totalAmountCent": total, "count": count})

    # Distributor view
    promoter = await _get_promoter(db, user_id)
    if promoter is None:
        return _ok({"month": period, "totalAmountCent": 0, "count": 0})

    total = (await consumption_by_distributor(db, [promoter.id], period)).get(promoter.id, 0)
    count = (await db.execute(
        select(func.count(Bill.id))
        .join(Customer, Customer.id == Bill.customer_id)
        .where(Customer.distributor_id == promoter.id, *paid_cond)
    )).scalar() or 0
    return _ok({"month": period, "totalAmountCent": total, "count": count})
