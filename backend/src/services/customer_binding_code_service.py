"""Patient-facing customer binding code validation and claim flow."""

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import BadRequestException, ConflictException, NotFoundException
from ..integrations.wechat_client import get_wechat_client
from ..models.binding import (
    BindingRequest,
    BindingRequestStatus,
    BindingStatus,
    Customer,
    MatchLevel,
    SourceType,
)
from ..models.consent import ConsentRecord, ConsentScene, EvidenceType, SubjectType
from ..models.distributor import Distributor, DistributorStatus
from ..models.organization import Organization, OrgStatus
from ..models.promotion import PromotionCode, PromotionCodeStatus
from ..models.user import ActivationStatus, User, UserType
from .binding_service import _mask_phone, _normalize_phone


async def _valid_code(db: AsyncSession, ref_token: str):
    result = await db.execute(
        select(PromotionCode, Distributor, User, Organization)
        .join(Distributor, Distributor.id == PromotionCode.distributor_id)
        .join(User, User.id == Distributor.user_id)
        .join(Organization, Organization.id == Distributor.org_id)
        .where(PromotionCode.ref_token == ref_token)
    )
    row = result.first()
    if row is None:
        raise NotFoundException(message="客户绑定码不存在或已失效")
    code, distributor, user, organization = row
    now = datetime.utcnow()
    expired = bool(code.expires_at and code.expires_at.replace(tzinfo=None) <= now)
    if (
        code.status != PromotionCodeStatus.AVAILABLE
        or expired
        or distributor.status != DistributorStatus.ACTIVE
        or user.activation_status != ActivationStatus.ACTIVE
        or organization.status != OrgStatus.ACTIVE
    ):
        raise BadRequestException(message="客户绑定码已失效，请联系发送人重新分享")
    return code, distributor, user, organization


async def get_code_info(
    db: AsyncSession, ref_token: str, *, record_scan: bool = True
) -> dict:
    code, distributor, user, organization = await _valid_code(db, ref_token)
    if record_scan:
        code.scan_count += 1
        db.add(code)
        await db.flush()
    return {
        "distributorName": user.name or "业务员",
        "organizationName": organization.name,
        "status": "available",
    }


async def claim_customer(
    db: AsyncSession,
    ref_token: str,
    *,
    phone_code: str,
    name: Optional[str],
    consent_confirmed: bool,
) -> dict:
    if not consent_confirmed:
        raise BadRequestException(message="请先同意客户资料授权后再绑定")
    code, distributor, distributor_user, organization = await _valid_code(db, ref_token)
    phone = _normalize_phone(await get_wechat_client().get_phone_number(phone_code))
    patient_user = (
        await db.execute(
            select(User)
            .where(User.phone == phone, User.user_type == UserType.PERSONAL)
            .with_for_update()
        )
    ).scalars().first()
    customer_matchers = [
        Customer.phone_normalized == phone,
        Customer.phone == phone,
    ]
    if patient_user is not None:
        customer_matchers.append(Customer.user_id == patient_user.id)
    customer = (
        await db.execute(
            select(Customer)
            .where(or_(*customer_matchers))
            .order_by(Customer.id.asc())
            .with_for_update()
        )
    ).scalars().first()

    if customer is not None and customer.distributor_id != distributor.id:
        raise ConflictException(
            code=40023,
            message="该手机号对应客户已归属其他业务员，请联系后台处理",
        )
    created = customer is None
    was_bound = False
    if customer is None:
        customer = Customer(
            user_id=patient_user.id if patient_user else None,
            distributor_id=distributor.id,
            name=name.strip() if name and name.strip() else None,
            phone=phone,
            phone_normalized=phone,
            phone_masked=_mask_phone(phone),
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.utcnow(),
            version=1,
        )
        db.add(customer)
        await db.flush()
        await db.refresh(customer)
    else:
        was_bound = customer.binding_status == BindingStatus.BOUND
        if patient_user and customer.user_id is None:
            customer.user_id = patient_user.id
        if name and name.strip():
            customer.name = name.strip()
        customer.phone = phone
        customer.phone_normalized = phone
        customer.phone_masked = _mask_phone(phone)
        customer.binding_status = BindingStatus.BOUND
        customer.bound_at = customer.bound_at or datetime.utcnow()
        customer.version += 1
        db.add(customer)
        await db.flush()

    existing_request = (
        await db.execute(
            select(BindingRequest).where(
                BindingRequest.customer_id == customer.id,
                BindingRequest.distributor_id == distributor.id,
                BindingRequest.source_type == SourceType.SCAN,
                BindingRequest.ref_token == ref_token,
            )
        )
    ).scalars().first()
    if existing_request is None:
        consent = ConsentRecord(
            customer_id=customer.id,
            subject_type=SubjectType.CUSTOMER,
            scene=ConsentScene.BINDING,
            agreement_versions={"customer_binding": "1.0"},
            scopes={"phone": True, "customer_attribution": True},
            confirmed=True,
            evidence_type=EvidenceType.CLICK,
            status="active",
        )
        db.add(consent)
        await db.flush()
        binding_request = BindingRequest(
            customer_id=customer.id,
            distributor_id=distributor.id,
            submitted_by=distributor.user_id,
            customer_name=customer.name,
            phone_masked=customer.phone_masked,
            source_type=SourceType.SCAN,
            ref_token=ref_token,
            consent_record_id=consent.id,
            status=BindingRequestStatus.PENDING_MATCH,
            match_level=MatchLevel.NONE,
        )
        db.add(binding_request)
    if created:
        code.lead_count += 1
    if created or not was_bound:
        code.bind_count += 1
    db.add(code)
    await db.flush()

    return {
        "customerId": str(customer.id),
        "phone": customer.phone_masked,
        "bindingStatus": "bound",
        "rutaiMatchStatus": "pending_match",
        "distributorName": distributor_user.name or "业务员",
        "organizationName": organization.name,
    }
