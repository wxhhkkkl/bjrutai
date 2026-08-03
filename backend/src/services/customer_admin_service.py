"""Admin customer management service (US1-US4).

Covers: org-scoped customer list, manual customer creation with hospital
binding match (FR-008), sensitive-field profile updates with audit (FR-010),
and promoter reassignment with full change history (FR-011/FR-012).

Output masking (宪法 IV v2.0.0): phone / id_card / medical_account are stored
plaintext but every API response exposes only masked values.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import (
    AppException,
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ..models.audit import AuditLog
from ..models.binding import (
    BindingRequest,
    BindingRequestStatus,
    BindingStatus,
    Customer,
    MatchLevel,
    SourceType,
)
from ..models.customer_change_log import ChangeOperationType, CustomerChangeLog
from ..models.distributor import Distributor
from ..models.organization import Organization
from ..models.user import User
from . import distributor_service, organization_service


# ---------------------------------------------------------------------------
# Masking helpers
# ---------------------------------------------------------------------------
def _mask_phone(phone: Optional[str]) -> Optional[str]:
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-4:]


def _mask_id_card(id_card: Optional[str]) -> Optional[str]:
    if not id_card or len(id_card) < 8:
        return id_card
    return id_card[:3] + "***********" + id_card[-4:]


def _mask_medical_account(account: Optional[str]) -> Optional[str]:
    if not account or len(account) < 8:
        return account
    return account[:4] + "****" + account[-4:]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------
async def _get_customer_or_404(db: AsyncSession, customer_id: int) -> Customer:
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalars().first()
    if customer is None:
        raise NotFoundException(message="客户不存在")
    return customer


async def _get_distributor_or_404(db: AsyncSession, distributor_id: int) -> Distributor:
    result = await db.execute(select(Distributor).where(Distributor.id == distributor_id))
    d = result.scalars().first()
    if d is None:
        raise NotFoundException(message="推广员不存在")
    return d


async def _distributor_name(db: AsyncSession, distributor_id: Optional[int]) -> Optional[str]:
    if distributor_id is None:
        return None
    result = await db.execute(
        select(User.name)
        .join(Distributor, Distributor.user_id == User.id)
        .where(Distributor.id == distributor_id)
    )
    return result.scalars().first()


async def _org_name(db: AsyncSession, org_id: Optional[int]) -> Optional[str]:
    if org_id is None:
        return None
    result = await db.execute(select(Organization.name).where(Organization.id == org_id))
    return result.scalars().first()


async def _operator_name(db: AsyncSession, operator_id: Optional[int]) -> Optional[str]:
    if operator_id is None:
        return None
    result = await db.execute(select(User.name).where(User.id == operator_id))
    return result.scalars().first()


def _binding_status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


# ---------------------------------------------------------------------------
# Change-log persistence & serialization
# ---------------------------------------------------------------------------
async def _log_distributor_change(
    db: AsyncSession,
    customer_id: int,
    operation_type: ChangeOperationType,
    previous: Optional[int],
    new: Optional[int],
    operator_id: int,
    reason: str,
) -> None:
    log = CustomerChangeLog(
        customer_id=customer_id,
        operation_type=operation_type,
        previous_distributor_id=previous,
        new_distributor_id=new,
        operator_id=operator_id,
        reason=reason,
    )
    db.add(log)
    await db.flush()


async def _change_log_to_dict(db: AsyncSession, log: CustomerChangeLog) -> dict:
    return {
        "id": str(log.id),
        "operationType": log.operation_type.value if hasattr(log.operation_type, "value") else str(log.operation_type),
        "previousDistributorId": str(log.previous_distributor_id) if log.previous_distributor_id else None,
        "previousPromoterName": await _distributor_name(db, log.previous_distributor_id),
        "newDistributorId": str(log.new_distributor_id) if log.new_distributor_id else None,
        "newPromoterName": await _distributor_name(db, log.new_distributor_id),
        "operatorName": await _operator_name(db, log.operator_id),
        "reason": log.reason,
        "createdAt": log.created_at.isoformat() if log.created_at else None,
    }


def _customer_summary(c: Customer, promoter_name, org_id, org_name) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "phoneMasked": _mask_phone(c.phone),
        "idCardMasked": c.id_card_masked or _mask_id_card(c.id_card_encrypted),
        "bindingStatus": _binding_status_value(c.binding_status),
        "distributorId": str(c.distributor_id) if c.distributor_id else None,
        "promoterName": promoter_name,
        "orgId": str(org_id) if org_id else None,
        "orgName": org_name,
        "note": c.note,
        "updatedAt": c.updated_at.isoformat() if c.updated_at else None,
    }


# ---------------------------------------------------------------------------
# US1: Org-scoped customer list
# ---------------------------------------------------------------------------
async def list_customers_by_org(
    db: AsyncSession,
    org_id: int,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Return customers whose promoter belongs to *org_id*'s subtree (FR-003)."""
    org_ids = {org_id}
    subtree = await organization_service.get_subtree(db, org_id)
    org_ids |= distributor_service._collect_org_ids(subtree)

    filters = [Distributor.org_id.in_(org_ids)]
    if status:
        try:
            bs = BindingStatus(status)
        except ValueError:
            raise BadRequestException(message=f"无效的绑定状态: {status}")
        filters.append(Customer.binding_status == bs)
    if keyword:
        kw = f"%{keyword}%"
        filters.append(
            or_(Customer.name.ilike(kw), Customer.phone.ilike(kw), Customer.phone_masked.ilike(kw))
        )

    query = (
        select(Customer, Distributor.org_id)
        .join(Distributor, Distributor.id == Customer.distributor_id)
        .where(*filters)
    )
    count_stmt = select(Customer.id).join(Distributor, Distributor.id == Customer.distributor_id).where(*filters)
    total = len((await db.execute(count_stmt)).scalars().all())

    rows = (
        await db.execute(
            query.order_by(Customer.id.desc()).limit(page_size).offset((page - 1) * page_size)
        )
    ).all()

    items = []
    for c, c_org_id in rows:
        items.append(_customer_summary(c, await _distributor_name(db, c.distributor_id), c_org_id, await _org_name(db, c_org_id)))

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    }


# ---------------------------------------------------------------------------
# US2: Manual customer creation + hospital match
# ---------------------------------------------------------------------------
async def create_manual_customer(
    db: AsyncSession,
    data,
    operator_id: int,
    rutai_client=None,
) -> dict:
    """Create a customer profile and immediately attempt hospital binding match (FR-008)."""
    if not data.id_card or len(data.id_card) != 18:
        raise BadRequestException(message="身份证号格式不正确")

    dup = await db.execute(select(Customer.id).where(Customer.id_card_encrypted == data.id_card))
    if dup.scalars().first() is not None:
        raise ConflictException(message="该身份证号已建档")

    try:
        distributor_id = int(data.distributor_id)
    except (ValueError, TypeError):
        raise BadRequestException(message="无效的推广员")
    distributor = await _get_distributor_or_404(db, distributor_id)
    if not await distributor_service.is_distributor_selectable(db, distributor):
        raise AppException(code=40020, message="推广员不存在或不可开展业务", status_code=400)

    now = datetime.utcnow()
    customer = Customer(
        distributor_id=distributor.id,
        name=data.name,
        phone=data.phone,
        phone_masked=_mask_phone(data.phone),
        id_card_encrypted=data.id_card,
        id_card_masked=_mask_id_card(data.id_card),
        medical_account_encrypted=data.medical_account,
        family_phone=data.family_phone,
        note=data.note,
        binding_status=BindingStatus.PENDING,
        version=1,
    )
    db.add(customer)
    await db.flush()
    await db.refresh(customer)

    await _log_distributor_change(
        db, customer.id, ChangeOperationType.CREATED,
        previous=None, new=distributor.id, operator_id=operator_id, reason="手工录入建档",
    )

    # Anchor binding request (source=manual) to store match result / failure reason.
    binding_req = BindingRequest(
        customer_id=customer.id,
        distributor_id=distributor.id,
        submitted_by=operator_id,
        customer_name=data.name,
        phone_masked=_mask_phone(data.phone),
        id_card_masked=_mask_id_card(data.id_card),
        source_type=SourceType.MANUAL,
        ref_token=str(uuid.uuid4()),
        status=BindingRequestStatus.PENDING_MATCH,
    )
    db.add(binding_req)
    await db.flush()
    await db.refresh(binding_req)

    if rutai_client is None:
        from ..integrations.rutai_client import get_rutai_client
        rutai_client = get_rutai_client()

    match_level = MatchLevel.NONE
    hrb_user_id = None
    failure_reason = None
    match_status = "error"
    try:
        result = await rutai_client.bind_bj_user(
            request_id=str(binding_req.id),
            patient_name=data.name or "",
            patient_phone=data.phone or "",
            id_card=data.id_card or "",
            medical_account=data.medical_account or "",
            family_phone=data.family_phone or "",
            source="BJTR",
            ref_token=binding_req.ref_token,
        )
        match_status = result.get("match_status", "no_match")
        hrb_user_id = result.get("hrb_user_id")
        try:
            match_level = MatchLevel(result.get("match_level", "none"))
        except ValueError:
            match_level = MatchLevel.NONE
    except Exception as exc:
        failure_reason = str(exc)

    if match_status == "matched":
        customer.binding_status = BindingStatus.BOUND
        customer.rutai_user_id = hrb_user_id
        customer.bound_at = now
        binding_req.status = BindingRequestStatus.BOUND
        binding_req.match_level = match_level
        binding_req.rutai_user_id_masked = hrb_user_id
        binding_req.bound_at = now
    elif match_status == "pending":
        binding_req.status = BindingRequestStatus.MATCHING
        binding_req.match_level = match_level
        binding_req.failure_reason = None
    elif match_status == "no_match":
        binding_req.status = BindingRequestStatus.NO_CONSUME
        binding_req.match_level = match_level
        binding_req.failure_reason = "医院未匹配到该客户"
    else:
        binding_req.status = BindingRequestStatus.ABNORMAL
        binding_req.match_level = match_level
        binding_req.failure_reason = failure_reason or "医院接口异常"

    db.add(customer)
    db.add(binding_req)
    await db.flush()
    await db.refresh(customer)

    promoter_name = await _distributor_name(db, distributor.id)
    org_id = distributor.org_id
    summary = _customer_summary(customer, promoter_name, org_id, await _org_name(db, org_id))
    summary.update({
        "rutaiUserId": customer.rutai_user_id,
        "boundAt": customer.bound_at.isoformat() if customer.bound_at else None,
        "matchResult": {"matched": match_status == "matched", "failureReason": binding_req.failure_reason},
    })
    return summary


# ---------------------------------------------------------------------------
# US3: Customer detail + sensitive-field update
# ---------------------------------------------------------------------------
async def get_customer_detail(db: AsyncSession, customer_id: int) -> dict:
    customer = await _get_customer_or_404(db, customer_id)

    from ..models.bill import Bill
    from ..models.followup import FollowupRecord

    service_count = len((await db.execute(select(Bill.id).where(Bill.customer_id == customer_id))).scalars().all())
    followup_count = len(
        (await db.execute(select(FollowupRecord.id).where(FollowupRecord.customer_id == customer_id))).scalars().all()
    )

    dist = await _get_distributor_or_404(db, customer.distributor_id)
    org_id = dist.org_id
    return {
        "id": str(customer.id),
        "name": customer.name,
        "phoneMasked": _mask_phone(customer.phone),
        "idCardMasked": customer.id_card_masked or _mask_id_card(customer.id_card_encrypted),
        "medicalAccountMasked": _mask_medical_account(customer.medical_account_encrypted),
        "familyPhone": customer.family_phone,
        "bindingStatus": _binding_status_value(customer.binding_status),
        "rutaiUserId": customer.rutai_user_id,
        "boundAt": customer.bound_at.isoformat() if customer.bound_at else None,
        "distributorId": str(customer.distributor_id) if customer.distributor_id else None,
        "promoterName": await _distributor_name(db, customer.distributor_id),
        "orgId": str(org_id) if org_id else None,
        "orgName": await _org_name(db, org_id),
        "note": customer.note,
        "serviceCount": service_count,
        "followupCount": followup_count,
        "createdAt": customer.created_at.isoformat() if customer.created_at else None,
        "updatedAt": customer.updated_at.isoformat() if customer.updated_at else None,
    }


async def update_customer_profile(
    db: AsyncSession, customer_id: int, data, operator_id: int
) -> dict:
    """Update a customer's profile. Sensitive fields require changeReason + audit (FR-010)."""
    customer = await _get_customer_or_404(db, customer_id)

    sensitive_fields: list[str] = []

    if data.phone is not None:
        if not data.change_reason:
            raise BadRequestException(message="修改敏感字段必须填写修改原因")
        customer.phone = data.phone
        customer.phone_masked = _mask_phone(data.phone)
        sensitive_fields.append("phone")

    if data.id_card is not None:
        if not data.change_reason:
            raise BadRequestException(message="修改敏感字段必须填写修改原因")
        if len(data.id_card) != 18:
            raise BadRequestException(message="身份证号格式不正确")
        dup = await db.execute(
            select(Customer.id).where(
                Customer.id_card_encrypted == data.id_card,
                Customer.id != customer.id,
            )
        )
        if dup.scalars().first() is not None:
            raise ConflictException(message="该身份证号已建档")
        customer.id_card_encrypted = data.id_card
        customer.id_card_masked = _mask_id_card(data.id_card)
        sensitive_fields.append("idCard")

    if data.medical_account is not None:
        if not data.change_reason:
            raise BadRequestException(message="修改敏感字段必须填写修改原因")
        customer.medical_account_encrypted = data.medical_account
        sensitive_fields.append("medicalAccount")

    if data.name is not None:
        customer.name = data.name
    if data.family_phone is not None:
        customer.family_phone = data.family_phone
    if data.note is not None:
        customer.note = data.note

    if sensitive_fields:
        audit = AuditLog(
            user_id=operator_id,
            action="update_customer_sensitive",
            entity_type="Customer",
            entity_id=str(customer.id),
            detail={"fields": sensitive_fields, "reason": data.change_reason},
        )
        db.add(audit)

    customer.version += 1
    db.add(customer)
    await db.flush()
    await db.refresh(customer)

    dist = await _get_distributor_or_404(db, customer.distributor_id)
    return _customer_summary(customer, await _distributor_name(db, customer.distributor_id), dist.org_id, await _org_name(db, dist.org_id))


# ---------------------------------------------------------------------------
# US4: Promoter reassignment + change history
# ---------------------------------------------------------------------------
async def transfer_customer(
    db: AsyncSession, customer_id: int, data, operator_id: int
) -> dict:
    """Reassign a customer's promoter. Does NOT change hospital binding status."""
    customer = await _get_customer_or_404(db, customer_id)

    try:
        new_distributor_id = int(data.new_distributor_id)
    except (ValueError, TypeError):
        raise BadRequestException(message="无效的推广员")

    new_distributor = await _get_distributor_or_404(db, new_distributor_id)
    if not await distributor_service.is_distributor_selectable(db, new_distributor):
        raise AppException(code=40020, message="新推广员不存在或不可开展业务", status_code=400)
    if new_distributor.id == customer.distributor_id:
        raise BadRequestException(message="不能更改为当前推广员")

    previous_distributor_id = customer.distributor_id
    customer.distributor_id = new_distributor.id
    customer.version += 1
    db.add(customer)
    await db.flush()

    await _log_distributor_change(
        db, customer.id, ChangeOperationType.TRANSFER,
        previous=previous_distributor_id, new=new_distributor.id,
        operator_id=operator_id, reason=data.reason,
    )
    audit = AuditLog(
        user_id=operator_id,
        action="transfer_customer",
        entity_type="Customer",
        entity_id=str(customer.id),
        detail={
            "previous_distributor_id": previous_distributor_id,
            "new_distributor_id": new_distributor.id,
            "reason": data.reason,
        },
    )
    db.add(audit)
    await db.flush()

    return {
        "customerId": str(customer.id),
        "previousDistributorId": str(previous_distributor_id),
        "previousPromoterName": await _distributor_name(db, previous_distributor_id),
        "newDistributorId": str(new_distributor.id),
        "newPromoterName": await _distributor_name(db, new_distributor.id),
        "transferredAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }


async def get_change_logs(db: AsyncSession, customer_id: int) -> dict:
    """Return the full promoter change history for a customer (FR-012)."""
    await _get_customer_or_404(db, customer_id)
    result = await db.execute(
        select(CustomerChangeLog)
        .where(CustomerChangeLog.customer_id == customer_id)
        .order_by(CustomerChangeLog.created_at.desc())
    )
    logs = result.scalars().all()
    return {"items": [await _change_log_to_dict(db, log) for log in logs]}
