"""Customer and followup endpoints (T170-T171).

GET    /customers                          – list with status filter, keyword search, cursor pagination
GET    /customers/{id}                     – detail (CustomerDetail)
PATCH  /customers/{id}                     – update with changeReason, returns reviewRequired flag
GET    /customers/{id}/service-records     – service records list
GET    /customers/{id}/binding-history     – binding/unbind/transfer history
GET    /customers/{id}/contributions       – customer's contribution records
GET    /customers/{id}/followups           – followup records list
POST   /customers/{id}/followups           – create followup
POST   /customers/{id}/followup-drafts     – save followup draft
PUT    /followups/{id}                     – update followup with version
PUT    /followups/{id}/reminder            – update reminder
POST   /followups/{id}/complete            – complete reminder
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ...api.deps import get_current_user, get_db
from ...core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from ...models.binding import (
    BindingChangeLog,
    BindingRequest,
    BindingStatus,
    Customer,
    OperationType,
)
from ...models.contribution import ContributionRecord
from ...models.followup import FollowupMethod, FollowupRecord, FollowupResult, ReminderStatus
from ...models.distributor import Distributor
from ...models.user import User, UserType

router = APIRouter(prefix="/customers", tags=["customers"])

# Separate router for followup operations not nested under /customers/{id}
followups_router = APIRouter(prefix="/followups", tags=["followups"])


def _ok(data=None) -> dict:
    return {
        "code": 0,
        "message": "success",
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────
def _mask_phone(phone: Optional[str]) -> Optional[str]:
    """Mask middle digits of a phone number: 138****1234."""
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-4:]


def _get_promoter_id_from_payload(payload: dict) -> int:
    """Extract distributor_id from JWT payload (looks up Distributor by user_id)."""
    return int(payload["sub"])


async def _get_user(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise NotFoundException(message="User not found")
    return user


async def _get_promoter(db: AsyncSession, user_id: int) -> Distributor:
    result = await db.execute(
        select(Distributor).where(Distributor.user_id == user_id)
    )
    promoter = result.scalars().first()
    if promoter is None:
        raise NotFoundException(message="Distributor not found")
    return promoter


async def _get_customer(db: AsyncSession, customer_id: int) -> Customer:
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalars().first()
    if customer is None:
        raise NotFoundException(message="Customer not found")
    return customer


# ──────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────
class CustomerUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=20)
    note: Optional[str] = Field(None, max_length=500)
    familyPhone: Optional[str] = Field(None, max_length=20)
    changeReason: Optional[str] = Field(None, max_length=500, description="Required for sensitive field changes")


class FollowupCreateRequest(BaseModel):
    method: str = Field(..., description="phone, wechat, visit, other")
    result: Optional[str] = Field("pending", description="successful, failed, pending, no_answer")
    content: Optional[str] = Field(None, max_length=2000)
    reminderAt: Optional[str] = Field(None, description="ISO datetime for reminder")


class FollowupUpdateRequest(BaseModel):
    method: Optional[str] = Field(None)
    result: Optional[str] = Field(None)
    content: Optional[str] = Field(None, max_length=2000)
    version: int = Field(..., ge=1)


class FollowupReminderRequest(BaseModel):
    reminderAt: Optional[str] = Field(None, description="ISO datetime")
    enabled: bool = False


class FollowupDraftRequest(BaseModel):
    method: Optional[str] = Field(None)
    content: Optional[str] = Field(None, max_length=2000)


# ──────────────────────────────────────────────────────────────────
# GET /customers
# ──────────────────────────────────────────────────────────────────
@router.get("")
async def list_customers(
    status: Optional[str] = Query(None, description="binding status: bound, unbound, pending"),
    keyword: Optional[str] = Query(None, description="Search by name or phone"),
    cursor: Optional[str] = Query(None, description="Pagination cursor (last ID)"),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """List customers with cursor pagination, status filter, keyword search."""
    user_id = int(payload["sub"])
    user_type = payload.get("user_type", "promoter")

    # Build query
    query = select(Customer).options(joinedload(Customer.distributor).joinedload(Distributor.user))

    # Admins see all, promoters see only their own
    if user_type != "admin":
        promoter = await _get_promoter(db, user_id)
        query = query.where(Customer.distributor_id == promoter.id)

    if status:
        try:
            bs = getattr(BindingStatus, status.upper(), None)
            if bs:
                query = query.where(Customer.binding_status == bs)
        except (AttributeError, KeyError):
            pass

    if keyword:
        kw = f"%{keyword}%"
        query = query.where(
            (Customer.name.ilike(kw)) |
            (Customer.phone.ilike(kw)) |
            (Customer.phone_masked.ilike(kw))
        )

    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.where(Customer.id < cursor_id)
        except (ValueError, TypeError):
            pass

    query = query.order_by(desc(Customer.id)).limit(pageSize + 1)

    result = await db.execute(query)
    rows = result.unique().scalars().all()

    has_more = len(rows) > pageSize
    items = rows[:pageSize]

    next_cursor = str(items[-1].id) if has_more and items else None

    data_items = []
    for c in items:
        p = c.distributor
        promoter_name = ""
        if p and p.user:
            promoter_name = p.user.name or ""

        data_items.append({
            "id": str(c.id),
            "name": c.name,
            "phone": _mask_phone(c.phone),
            "phoneMasked": c.phone_masked or _mask_phone(c.phone),
            "bindingStatus": c.binding_status.value if hasattr(c.binding_status, "value") else str(c.binding_status),
            "promoterName": promoter_name,
            "promoterId": str(c.distributor_id) if c.distributor_id else None,
            "note": c.note,
            "updatedAt": c.updated_at.isoformat() if c.updated_at else None,
        })

    return _ok({
        "items": data_items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    })


# ──────────────────────────────────────────────────────────────────
# GET /customers/{id}
# ──────────────────────────────────────────────────────────────────
@router.get("/{customer_id}")
async def get_customer_detail(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get full customer detail with counts."""
    result = await db.execute(
        select(Customer)
        .options(
            joinedload(Customer.distributor).joinedload(Distributor.user),
            joinedload(Customer.bills),
            joinedload(Customer.followup_records),
            joinedload(Customer.consent_records),
        )
        .where(Customer.id == customer_id)
    )
    customer = result.unique().scalars().first()
    if customer is None:
        raise NotFoundException(message="Customer not found")

    # Access checks: admins see all, promoters see their own
    user_type = payload.get("user_type", "promoter")
    if user_type != "admin":
        user_id = int(payload["sub"])
        promoter = await _get_promoter(db, user_id)
        if customer.distributor_id != promoter.id:
            raise ForbiddenException(message="Forbidden")

    # Counts
    service_count = len(customer.bills) if customer.bills else 0
    followup_count = len(customer.followup_records) if customer.followup_records else 0

    # Monthly contribution (current month)
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    contrib_result = await db.execute(
        select(func.sum(ContributionRecord.points), func.count(ContributionRecord.id))
        .where(
            ContributionRecord.customer_id == customer_id,
            ContributionRecord.occurred_at >= month_start,
        )
    )
    monthly_row = contrib_result.one_or_none()
    monthly_contribution = float(monthly_row[0]) if monthly_row and monthly_row[0] else 0.0
    monthly_count = monthly_row[1] if monthly_row else 0

    # Total contribution
    total_result = await db.execute(
        select(func.sum(ContributionRecord.points), func.count(ContributionRecord.id))
        .where(ContributionRecord.customer_id == customer_id)
    )
    total_row = total_result.one_or_none()
    total_contribution = float(total_row[0]) if total_row and total_row[0] else 0.0

    p = customer.distributor
    promoter_name = ""
    if p and p.user:
        promoter_name = p.user.name or ""

    return _ok({
        "id": str(customer.id),
        "name": customer.name,
        "phone": _mask_phone(customer.phone),
        "phoneMasked": customer.phone_masked or _mask_phone(customer.phone),
        "idCardMasked": customer.id_card_masked,
        "bindingStatus": customer.binding_status.value if hasattr(customer.binding_status, "value") else str(customer.binding_status),
        "promoterId": str(customer.distributor_id) if customer.distributor_id else None,
        "promoterName": promoter_name,
        "rutaiUserId": customer.rutai_user_id,
        "note": customer.note,
        "familyPhone": customer.family_phone,
        "boundAt": customer.bound_at.isoformat() if customer.bound_at else None,
        "version": customer.version,
        "serviceCount": service_count,
        "followupCount": followup_count,
        "monthlyContribution": monthly_contribution,
        "monthlyContributionCount": monthly_count,
        "totalContribution": total_contribution,
        "createdAt": customer.created_at.isoformat() if customer.created_at else None,
        "updatedAt": customer.updated_at.isoformat() if customer.updated_at else None,
    })


# ──────────────────────────────────────────────────────────────────
# PATCH /customers/{id}
# ──────────────────────────────────────────────────────────────────
@router.patch("/{customer_id}")
async def update_customer(
    customer_id: int,
    body: CustomerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Update a customer's fields. Sensitive fields (phone) require changeReason."""
    customer = await _get_customer(db, customer_id)

    # Access checks
    user_type = payload.get("user_type", "promoter")
    if user_type != "admin":
        user_id = int(payload["sub"])
        promoter = await _get_promoter(db, user_id)
        if customer.distributor_id != promoter.id:
            raise ForbiddenException(message="Forbidden")

    review_required = False

    # Sensitive fields require changeReason
    if body.phone is not None:
        if not body.changeReason:
            raise BadRequestException(message="Sensitive field changes require a changeReason")
        customer.phone = body.phone
        customer.phone_masked = _mask_phone(body.phone)
        review_required = True

    if body.name is not None:
        customer.name = body.name
    if body.note is not None:
        customer.note = body.note
    if body.familyPhone is not None:
        customer.family_phone = body.familyPhone

    customer.version += 1
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    return _ok({
        "id": str(customer.id),
        "name": customer.name,
        "phone": _mask_phone(customer.phone),
        "note": customer.note,
        "familyPhone": customer.family_phone,
        "version": customer.version,
        "reviewRequired": review_required,
        "updatedAt": customer.updated_at.isoformat() if customer.updated_at else None,
    })


# ──────────────────────────────────────────────────────────────────
# GET /customers/{id}/service-records
# ──────────────────────────────────────────────────────────────────
@router.get("/{customer_id}/service-records")
async def get_service_records(
    customer_id: int,
    cursor: Optional[str] = Query(None),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """List service records (bills) for a customer."""
    from ...models.bill import Bill
    customer = await _get_customer(db, customer_id)

    query = select(Bill).where(Bill.customer_id == customer_id)
    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.where(Bill.id < cursor_id)
        except (ValueError, TypeError):
            pass

    query = query.order_by(desc(Bill.id)).limit(pageSize + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > pageSize
    items = rows[:pageSize]
    next_cursor = str(items[-1].id) if has_more and items else None

    data_items = []
    for b in items:
        data_items.append({
            "id": str(b.id),
            "billNo": b.bill_no if hasattr(b, "bill_no") else None,
            "title": getattr(b, "title", None),
            "amount": getattr(b, "amount", None),
            "status": getattr(b, "status", None),
            "serviceDate": None,
            "createdAt": b.created_at.isoformat() if b.created_at else None,
        })

    return _ok({
        "items": data_items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    })


# ──────────────────────────────────────────────────────────────────
# GET /customers/{id}/binding-history
# ──────────────────────────────────────────────────────────────────
@router.get("/{customer_id}/binding-history")
async def get_binding_history(
    customer_id: int,
    cursor: Optional[str] = Query(None),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get binding/unbind/transfer history for a customer."""
    customer = await _get_customer(db, customer_id)

    # Get binding requests for this customer
    query = select(BindingRequest).where(BindingRequest.customer_id == customer_id)
    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.where(BindingRequest.id < cursor_id)
        except (ValueError, TypeError):
            pass

    query = query.order_by(desc(BindingRequest.id)).limit(pageSize + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > pageSize
    items = rows[:pageSize]
    next_cursor = str(items[-1].id) if has_more and items else None

    data_items = []
    for br in items:
        # Also fetch change logs
        logs_result = await db.execute(
            select(BindingChangeLog)
            .where(BindingChangeLog.binding_request_id == br.id)
            .order_by(desc(BindingChangeLog.created_at))
        )
        logs = logs_result.scalars().all()
        log_items = []
        for log in logs:
            log_items.append({
                "id": str(log.id),
                "operationType": log.operation_type.value if hasattr(log.operation_type, "value") else str(log.operation_type),
                "previousPromoterId": str(log.previous_promoter_id) if log.previous_promoter_id else None,
                "newPromoterId": str(log.new_promoter_id) if log.new_promoter_id else None,
                "reason": log.reason,
                "createdAt": log.created_at.isoformat() if log.created_at else None,
            })

        data_items.append({
            "id": str(br.id),
            "status": br.status.value if hasattr(br.status, "value") else str(br.status),
            "sourceType": br.source_type.value if hasattr(br.source_type, "value") else str(br.source_type),
            "boundAt": br.bound_at.isoformat() if br.bound_at else None,
            "changeLogs": log_items,
            "createdAt": br.created_at.isoformat() if br.created_at else None,
            "updatedAt": br.updated_at.isoformat() if br.updated_at else None,
        })

    return _ok({
        "items": data_items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    })


# ──────────────────────────────────────────────────────────────────
# GET /customers/{id}/contributions
# ──────────────────────────────────────────────────────────────────
@router.get("/{customer_id}/contributions")
async def get_customer_contributions(
    customer_id: int,
    cursor: Optional[str] = Query(None),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Get a customer's contribution records."""
    customer = await _get_customer(db, customer_id)

    query = select(ContributionRecord).where(ContributionRecord.customer_id == customer_id)
    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.where(ContributionRecord.id < cursor_id)
        except (ValueError, TypeError):
            pass

    query = query.order_by(desc(ContributionRecord.id)).limit(pageSize + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > pageSize
    items = rows[:pageSize]
    next_cursor = str(items[-1].id) if has_more and items else None

    data_items = []
    for cr in items:
        data_items.append({
            "id": str(cr.id),
            "title": cr.title,
            "points": cr.points,
            "status": cr.status.value if hasattr(cr.status, "value") else str(cr.status),
            "category": cr.category.value if hasattr(cr.category, "value") else str(cr.category),
            "occurredAt": cr.occurred_at.isoformat() if cr.occurred_at else None,
            "settledAt": cr.settled_at.isoformat() if cr.settled_at else None,
        })

    return _ok({
        "items": data_items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    })


# ──────────────────────────────────────────────────────────────────
# GET /customers/{id}/followups
# ──────────────────────────────────────────────────────────────────
@router.get("/{customer_id}/followups")
async def get_followups(
    customer_id: int,
    cursor: Optional[str] = Query(None),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """List followup records for a customer."""
    customer = await _get_customer(db, customer_id)

    query = select(FollowupRecord).where(FollowupRecord.customer_id == customer_id)
    if cursor:
        try:
            cursor_id = int(cursor)
            query = query.where(FollowupRecord.id < cursor_id)
        except (ValueError, TypeError):
            pass

    query = query.order_by(desc(FollowupRecord.created_at)).limit(pageSize + 1)
    result = await db.execute(query)
    rows = result.scalars().all()

    has_more = len(rows) > pageSize
    items = rows[:pageSize]
    next_cursor = str(items[-1].id) if has_more and items else None

    data_items = []
    for fr in items:
        data_items.append({
            "id": str(fr.id),
            "doctorId": str(fr.doctor_id),
            "method": fr.method.value if hasattr(fr.method, "value") else str(fr.method),
            "result": fr.result.value if hasattr(fr.result, "value") else str(fr.result),
            "content": fr.content,
            "reminderEnabled": fr.reminder_enabled,
            "reminderAt": fr.reminder_at.isoformat() if fr.reminder_at else None,
            "reminderStatus": fr.reminder_status.value if hasattr(fr.reminder_status, "value") else str(fr.reminder_status),
            "version": fr.version,
            "createdAt": fr.created_at.isoformat() if fr.created_at else None,
        })

    return _ok({
        "items": data_items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    })


# ──────────────────────────────────────────────────────────────────
# POST /customers/{id}/followups
# ──────────────────────────────────────────────────────────────────
@router.post("/{customer_id}/followups")
async def create_followup(
    customer_id: int,
    body: FollowupCreateRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Create a followup record for a customer."""
    customer = await _get_customer(db, customer_id)
    user_id = int(payload["sub"])

    # Validate method
    try:
        method = getattr(FollowupMethod, body.method.upper())
    except (AttributeError, KeyError):
        raise BadRequestException(message=f"Invalid method: {body.method}. Valid: phone, wechat, visit, other")

    reminder_at = None
    if body.reminderAt:
        try:
            reminder_at = datetime.fromisoformat(body.reminderAt.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise BadRequestException(message="Invalid reminderAt format")

    followup = FollowupRecord(
        customer_id=customer_id,
        doctor_id=user_id,
        method=method,
        result=FollowupResult.PENDING,
        content=body.content,
        reminder_enabled=body.reminderAt is not None,
        reminder_at=reminder_at,
        reminder_status=ReminderStatus.PENDING,
        version=1,
    )
    db.add(followup)
    await db.commit()
    await db.refresh(followup)

    return _ok({
        "id": str(followup.id),
        "customerId": str(followup.customer_id),
        "method": followup.method.value,
        "result": followup.result.value,
        "content": followup.content,
        "reminderEnabled": followup.reminder_enabled,
        "reminderAt": followup.reminder_at.isoformat() if followup.reminder_at else None,
        "version": followup.version,
        "createdAt": followup.created_at.isoformat() if followup.created_at else None,
    })


# ──────────────────────────────────────────────────────────────────
# POST /customers/{id}/followup-drafts
# ──────────────────────────────────────────────────────────────────
@router.post("/{customer_id}/followup-drafts")
async def save_followup_draft(
    customer_id: int,
    body: FollowupDraftRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Save a followup draft for a customer. Uses PENDING result to mark as draft."""
    customer = await _get_customer(db, customer_id)
    user_id = int(payload["sub"])

    method = FollowupMethod.OTHER
    if body.method:
        try:
            method = getattr(FollowupMethod, body.method.upper())
        except (AttributeError, KeyError):
            pass

    draft = FollowupRecord(
        customer_id=customer_id,
        doctor_id=user_id,
        method=method,
        result=FollowupResult.PENDING,
        content=body.content,
        reminder_enabled=False,
        version=1,
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)

    return _ok({
        "id": str(draft.id),
        "customerId": str(draft.customer_id),
        "content": draft.content,
        "isDraft": True,
        "createdAt": draft.created_at.isoformat() if draft.created_at else None,
    })


# =============================================================================
# Followups router (standalone, not nested under /customers/{id})
# =============================================================================


# ──────────────────────────────────────────────────────────────────
# PUT /followups/{id}
# ──────────────────────────────────────────────────────────────────
@followups_router.put("/{followup_id}")
async def update_followup(
    followup_id: int,
    body: FollowupUpdateRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Update a followup record with version-based optimistic locking."""
    result = await db.execute(
        select(FollowupRecord).where(FollowupRecord.id == followup_id)
    )
    followup = result.scalars().first()
    if followup is None:
        raise NotFoundException(message="Followup not found")

    # Optimistic locking
    if body.version != followup.version:
        raise ConflictException(
            message="Followup has been modified. Please refresh and retry.",
            code=40901,
        )

    if body.method:
        try:
            followup.method = getattr(FollowupMethod, body.method.upper())
        except (AttributeError, KeyError):
            raise BadRequestException(message=f"Invalid method: {body.method}")
    if body.result:
        try:
            followup.result = getattr(FollowupResult, body.result.upper())
        except (AttributeError, KeyError):
            raise BadRequestException(message=f"Invalid result: {body.result}")
    if body.content is not None:
        followup.content = body.content

    followup.version += 1
    db.add(followup)
    await db.commit()
    await db.refresh(followup)

    return _ok({
        "id": str(followup.id),
        "method": followup.method.value,
        "result": followup.result.value,
        "content": followup.content,
        "version": followup.version,
        "updatedAt": followup.updated_at.isoformat() if followup.updated_at else None,
    })


# ──────────────────────────────────────────────────────────────────
# PUT /followups/{id}/reminder
# ──────────────────────────────────────────────────────────────────
@followups_router.put("/{followup_id}/reminder")
async def update_followup_reminder(
    followup_id: int,
    body: FollowupReminderRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Update the reminder settings for a followup."""
    result = await db.execute(
        select(FollowupRecord).where(FollowupRecord.id == followup_id)
    )
    followup = result.scalars().first()
    if followup is None:
        raise NotFoundException(message="Followup not found")

    followup.reminder_enabled = body.enabled
    if body.reminderAt:
        try:
            followup.reminder_at = datetime.fromisoformat(body.reminderAt.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise BadRequestException(message="Invalid reminderAt format")
    else:
        followup.reminder_at = None

    followup.reminder_status = ReminderStatus.PENDING if body.enabled else ReminderStatus.CANCELLED
    db.add(followup)
    await db.commit()

    return _ok({
        "id": str(followup.id),
        "reminderEnabled": followup.reminder_enabled,
        "reminderAt": followup.reminder_at.isoformat() if followup.reminder_at else None,
        "reminderStatus": followup.reminder_status.value,
    })


# ──────────────────────────────────────────────────────────────────
# POST /followups/{id}/complete
# ──────────────────────────────────────────────────────────────────
@followups_router.post("/{followup_id}/complete")
async def complete_followup(
    followup_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_user),
) -> dict:
    """Mark a followup reminder as completed."""
    result = await db.execute(
        select(FollowupRecord).where(FollowupRecord.id == followup_id)
    )
    followup = result.scalars().first()
    if followup is None:
        raise NotFoundException(message="Followup not found")

    followup.reminder_status = ReminderStatus.SENT
    followup.result = FollowupResult.SUCCESSFUL
    db.add(followup)
    await db.commit()

    return _ok({
        "id": str(followup.id),
        "reminderStatus": "sent",
        "result": "successful",
        "completedAt": datetime.now(timezone.utc).isoformat(),
    })
