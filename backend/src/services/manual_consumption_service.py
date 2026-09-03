"""Business logic for admin-entered customer consumption."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    ValidationException,
)
from ..models.audit import AuditLog
from ..models.bill import Bill, TransactionStatus
from ..models.binding import BindingStatus, Customer
from ..models.distributor import Distributor, DistributorStatus
from ..models.organization import Organization, OrgStatus
from ..models.user import AdminAccount, User
from ..schemas.admin_contribution import ManualConsumptionCreateRequest


def _mask_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    if len(phone) < 7:
        return "*" * len(phone)
    return phone[:3] + "****" + phone[-4:]


def _mask_id_card(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) < 8:
        return "*" * len(value)
    return value[:3] + "***********" + value[-4:]


def _fingerprint(data: ManualConsumptionCreateRequest) -> str:
    normalized = {
        "customerId": str(int(data.customer_id)),
        "customerVersion": data.customer_version,
        "consumedAt": data.consumed_at.astimezone(timezone.utc).isoformat(),
        "amountCent": data.amount_cent,
        "note": data.note,
    }
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _record_no() -> str:
    return f"MANUAL-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


async def search_eligible_customers(
    db: AsyncSession,
    *,
    keyword: str,
    page_size: int = 20,
) -> dict:
    keyword = keyword.strip()
    if not keyword or len(keyword) > 100:
        raise ValidationException(message="请输入客户姓名、手机号或身份证号")

    pattern = f"%{keyword}%"
    exact_rank = case(
        (Customer.phone == keyword, 0),
        (Customer.id_card_encrypted == keyword, 0),
        (Customer.name == keyword, 0),
        else_=1,
    )
    stmt = (
        select(Customer, Distributor, User.name, Organization)
        .join(Distributor, Distributor.id == Customer.distributor_id)
        .join(User, User.id == Distributor.user_id)
        .join(Organization, Organization.id == Distributor.org_id)
        .where(
            Customer.binding_status == BindingStatus.BOUND,
            Distributor.status == DistributorStatus.ACTIVE,
            Organization.status == OrgStatus.ACTIVE,
            or_(
                Customer.name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Customer.phone_masked.ilike(pattern),
                Customer.id_card_encrypted.ilike(pattern),
                Customer.id_card_masked.ilike(pattern),
            ),
        )
        .order_by(exact_rank, Customer.id.desc())
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()
    return {
        "items": [
            {
                "customerId": str(customer.id),
                "customerVersion": customer.version,
                "name": customer.name,
                "phoneMasked": customer.phone_masked or _mask_phone(customer.phone),
                "idCardMasked": customer.id_card_masked
                or _mask_id_card(customer.id_card_encrypted),
                "distributorId": str(distributor.id),
                "personName": person_name,
                "orgId": str(organization.id),
                "orgName": organization.name,
            }
            for customer, distributor, person_name, organization in rows
        ]
    }


async def _load_existing(
    db: AsyncSession, admin_id: int, idempotency_key: str
) -> Optional[Bill]:
    return (
        (
            await db.execute(
                select(Bill).where(
                    Bill.created_by_admin_id == admin_id,
                    Bill.idempotency_key == idempotency_key,
                )
            )
        )
        .scalars()
        .first()
    )


async def _serialize_bill(db: AsyncSession, bill: Bill, *, replayed: bool) -> dict:
    customer = (
        (await db.execute(select(Customer).where(Customer.id == bill.customer_id)))
        .scalars()
        .first()
    )
    occurred = bill.transaction_time
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    return {
        "id": str(bill.id),
        "recordNo": bill.transaction_id,
        "customerId": str(bill.customer_id),
        "customerName": customer.name if customer else None,
        "phoneMasked": (
            customer.phone_masked or _mask_phone(customer.phone) if customer else None
        ),
        "distributorId": str(bill.attributed_distributor_id),
        "personName": bill.attributed_person_name,
        "orgId": str(bill.attributed_org_id),
        "orgName": bill.attributed_org_name,
        "amountCent": bill.paid_amount_cent,
        "status": bill.transaction_status.value,
        "source": bill.source,
        "consumedAt": occurred.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "replayed": replayed,
    }


async def create_manual_consumption(
    db: AsyncSession,
    *,
    data: ManualConsumptionCreateRequest,
    admin_id: int,
    admin_username: Optional[str],
    idempotency_key: str,
    ip_address: Optional[str] = None,
) -> dict:
    if not idempotency_key or len(idempotency_key) > 128:
        raise BadRequestException(message="缺少或无效的 Idempotency-Key")
    if data.consumed_at.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValidationException(message="消费时间不能晚于当前时间")

    fingerprint = _fingerprint(data)
    existing = await _load_existing(db, admin_id, idempotency_key)
    if existing:
        if existing.submission_fingerprint != fingerprint:
            raise ConflictException(message="幂等键已用于不同的消费内容", code=40922)
        return await _serialize_bill(db, existing, replayed=True)

    customer_id = int(data.customer_id)
    row = (
        await db.execute(
            select(Customer, Distributor, User.name, Organization)
            .join(Distributor, Distributor.id == Customer.distributor_id)
            .join(User, User.id == Distributor.user_id)
            .join(Organization, Organization.id == Distributor.org_id)
            .where(Customer.id == customer_id)
        )
    ).first()
    if row is None:
        exists = (
            await db.execute(select(Customer.id).where(Customer.id == customer_id))
        ).scalar_one_or_none()
        if exists is None:
            raise NotFoundException(message="客户不存在")
        raise ConflictException(message="该客户当前不可录入消费", code=40921)

    customer, distributor, person_name, organization = row
    if customer.version != data.customer_version:
        raise ConflictException(message="客户资料或归属已变化，请重新选择客户", code=40920)
    if (
        customer.binding_status != BindingStatus.BOUND
        or distributor.status != DistributorStatus.ACTIVE
        or organization.status != OrgStatus.ACTIVE
    ):
        raise ConflictException(message="该客户当前不可录入消费", code=40921)

    if not admin_username:
        admin_username = (
            await db.execute(select(AdminAccount.username).where(AdminAccount.id == admin_id))
        ).scalar_one_or_none()
    if not admin_username:
        raise NotFoundException(message="管理员账号不存在")

    bill = Bill(
        customer_id=customer.id,
        rutai_user_id=customer.rutai_user_id,
        transaction_id=_record_no(),
        transaction_time=data.consumed_at.astimezone(timezone.utc).replace(tzinfo=None),
        consultation_fee_cent=0,
        medicine_fee_cent=0,
        total_amount_cent=data.amount_cent,
        discount_amount_cent=0,
        paid_amount_cent=data.amount_cent,
        refund_amount_cent=0,
        transaction_status=TransactionStatus.PAID,
        source="manual",
        attributed_distributor_id=distributor.id,
        attributed_person_name=person_name,
        attributed_org_id=organization.id,
        attributed_org_name=organization.name,
        entry_note=data.note,
        created_by_admin_id=admin_id,
        idempotency_key=idempotency_key,
        submission_fingerprint=fingerprint,
    )

    try:
        async with db.begin_nested():
            db.add(bill)
            await db.flush()
            db.add(
                AuditLog(
                    user_id=None,
                    action="manual_consumption_create",
                    entity_type="bill",
                    entity_id=str(bill.id),
                    detail={
                        "adminId": admin_id,
                        "adminUsername": admin_username,
                        "customerId": customer.id,
                        "distributorId": distributor.id,
                        "orgId": organization.id,
                        "amountCent": data.amount_cent,
                        "source": "manual",
                    },
                    ip_address=ip_address,
                )
            )
            await db.flush()
    except IntegrityError:
        existing = await _load_existing(db, admin_id, idempotency_key)
        if existing and existing.submission_fingerprint == fingerprint:
            return await _serialize_bill(db, existing, replayed=True)
        if existing:
            raise ConflictException(message="幂等键已用于不同的消费内容", code=40922)
        raise

    return await _serialize_bill(db, bill, replayed=False)
