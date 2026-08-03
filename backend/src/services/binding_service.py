"""Binding Service — core business logic for customer binding management.

Covers:
- Distributor selection for doctors
- Binding request submission with Rutai API integration
- Binding request listing/detail/summary
- Retry, customer info correction
- Admin unbind and transfer with audit logging
"""

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.exceptions import (
    AppException,
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from ..integrations.rutai_client import RutaiClient, get_rutai_client
from ..models.binding import (
    BindingChangeLog,
    BindingRequest,
    BindingRequestStatus,
    BindingStatus,
    Customer,
    MatchLevel,
    OperationType,
    SourceType,
)
from ..models.consent import ConsentRecord, ConsentScene
from ..models.distributor import Distributor
from ..models.org_qualification import OrgQualStatus, OrganizationQualification
from . import distributor_service
from ..models.user import User

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BINDING_EXPIRY_DAYS: int = 7
MAX_RETRY_COUNT: int = 3
RETRY_INTERVAL_MINUTES: int = 10
RETRYABLE_STATUSES: set[str] = {
    BindingRequestStatus.ABNORMAL.value,
    BindingRequestStatus.MANUAL_REVIEW.value,
    BindingRequestStatus.NO_CONSUME.value,
}


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------
def _encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> str:
    pad = 4 - len(cursor) % 4
    if pad != 4:
        cursor += "=" * pad
    return base64.urlsafe_b64decode(cursor.encode()).decode()


def _build_cursor_from_id_ts(item_id: int, ts: datetime) -> str:
    return _encode_cursor(json.dumps({"i": item_id, "t": ts.isoformat()}))


# ---------------------------------------------------------------------------
# Status labels (Chinese)
# ---------------------------------------------------------------------------
STATUS_LABELS: dict[str, str] = {
    BindingRequestStatus.PENDING_MATCH.value: "等待匹配",
    BindingRequestStatus.MATCHING.value: "匹配中",
    BindingRequestStatus.BOUND.value: "已绑定",
    BindingRequestStatus.NO_CONSUME.value: "无消费记录",
    BindingRequestStatus.RETRYING.value: "重试中",
    BindingRequestStatus.MANUAL_REVIEW.value: "人工审核",
    BindingRequestStatus.ABNORMAL.value: "异常",
    BindingRequestStatus.UNBOUND.value: "已解绑",
    BindingRequestStatus.TRANSFERRED.value: "已转移",
}

MATCH_LEVEL_LABELS: dict[str, str] = {
    MatchLevel.EXACT.value: "精确匹配",
    MatchLevel.FUZZY.value: "模糊匹配",
    MatchLevel.NONE.value: "未匹配",
}


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


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class BindingService:
    """Async service for all binding operations."""

    def __init__(self, rutai_client: Optional[RutaiClient] = None) -> None:
        self._rutai = rutai_client

    @property
    def rutai(self) -> RutaiClient:
        """Lazily obtain the Rutai client. When an explicit client is injected
        (e.g. in tests), use it. Otherwise, call the factory each time to avoid
        stale caching issues with mocked singletons."""
        if self._rutai is not None:
            return self._rutai
        return get_rutai_client()

    # ==================================================================
    # Selectable Promoters
    # ==================================================================

    async def get_selectable_promoters(
        self,
        db: AsyncSession,
        *,
        keyword: Optional[str] = None,
        cursor: Optional[str] = None,
        page_size: int = 20,
        doctor_user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Return promoters that the given doctor can select for binding.

        Only returns active promoters whose qualifications are approved.
        Results are sorted by bindingCount descending, then displayName,
        with promoters in the same org node appearing first.
        """
        page_size = max(1, min(page_size, 100))

        # Base query: active promoters with approved qualifications
        base_query = (
            select(
                Distributor.id,
                User.id.label("user_id"),
                User.name,
                User.phone_masked,
                User.avatar_url,
                func.count(Customer.id).label("binding_count"),
            )
            .join(User, User.id == Distributor.user_id)
            .outerjoin(Customer, Customer.distributor_id == Distributor.id)
            .join(
                OrganizationQualification,
                (OrganizationQualification.org_id == Distributor.org_id)
                & (OrganizationQualification.status == OrgQualStatus.APPROVED)
                & (OrganizationQualification.valid_until > datetime.now(timezone.utc)),
            )
            .where(User.activation_status == "active")
            .group_by(Distributor.id, User.id, User.name, User.phone_masked, User.avatar_url)
        )

        if keyword:
            kw = f"%{keyword}%"
            base_query = base_query.where(
                or_(User.name.ilike(kw), User.phone_masked.ilike(kw))
            )

        # Count query
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch one extra to determine hasMore
        base_query = base_query.order_by(desc("binding_count"), User.name).limit(page_size + 1)
        result = await db.execute(base_query)
        rows = result.all()

        has_more = len(rows) > page_size
        items_rows = rows[:page_size]

        items: list[dict[str, Any]] = []
        for row in items_rows:
            items.append({
                "promoterId": str(row.user_id),
                "promoterCode": None,
                "displayName": row.name,
                "avatarUrl": row.avatar_url,
                "orgNodeName": None,
                "bindingCount": row.binding_count or 0,
            })

        next_cursor: Optional[str] = None
        if has_more and items_rows:
            last_id = items_rows[-1].user_id
            next_cursor = _encode_cursor(str(last_id))

        return {
            "items": items,
            "nextCursor": next_cursor,
            "hasMore": has_more,
        }

    # ==================================================================
    # Submit Binding Request
    # ==================================================================

    async def submit_binding_request(
        self,
        db: AsyncSession,
        *,
        data: dict[str, Any],
        submitted_by: int,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new binding request and call the Rutai API to initiate matching.

        Args:
            data: Binding request data with keys:
                - promoterId (str)
                - promoterCode (str, optional)
                - customerInfo (dict, optional): name, phone, idCard, medicalAccount, familyPhone, remark
                - consentRecordId (int, optional)
                - sourceType (str, optional)
            submitted_by: The user ID of the doctor submitting the request.
            idempotency_key: Optional idempotency key for deduplication.

        Returns:
            Dict with requestId, status, statusLabel, promoterId, promoterName,
            matchLevel, submittedAt, expiresAt.
        """
        promoter_id_str = data.get("promoterId", "")
        if not promoter_id_str:
            raise ValidationException(message="promoterId is required")

        try:
            promoter_user_id = int(promoter_id_str)
        except (ValueError, TypeError):
            raise BadRequestException(message="Invalid promoterId")

        # Verify distributor exists and its org is business-available
        promoter_result = await db.execute(
            select(Distributor).where(Distributor.user_id == promoter_user_id)
        )
        promoter = promoter_result.scalars().first()
        if promoter is None or not await distributor_service.is_distributor_selectable(db, promoter):
            raise AppException(
                code=40020, message="Distributor not found or not selectable", status_code=400,
            )

        # Check if already bound to this promoter
        existing_bound = await db.execute(
            select(Customer).where(
                Customer.distributor_id == promoter.id,
                Customer.binding_status == BindingStatus.BOUND,
            )
        )
        if existing_bound.scalars().first() is not None:
            raise AppException(
                code=40022, message="You are already bound to this promoter", status_code=409,
            )

        # Check for pending request to same promoter
        existing_pending = await db.execute(
            select(BindingRequest).where(
                BindingRequest.distributor_id == promoter.id,
                BindingRequest.submitted_by == submitted_by,
                BindingRequest.status.in_([
                    BindingRequestStatus.PENDING_MATCH,
                    BindingRequestStatus.MATCHING,
                    BindingRequestStatus.RETRYING,
                    BindingRequestStatus.MANUAL_REVIEW,
                ]),
            )
        )
        if existing_pending.scalars().first() is not None:
            raise ConflictException(
                code=40021,
                message="You already have a pending binding request for this promoter",
            )

        # Get consent record if provided
        consent_record_id = data.get("consentRecordId")
        if consent_record_id:
            cr_result = await db.execute(
                select(ConsentRecord).where(
                    ConsentRecord.id == int(consent_record_id),
                )
            )
            cr = cr_result.scalars().first()
            if cr is None or not cr.confirmed:
                raise BadRequestException(
                    code=40025,
                    message="Consent record not found or not confirmed",
                )
            consent_record_id = int(consent_record_id)

        # Extract customer info
        customer_info = data.get("customerInfo") or {}
        name = customer_info.get("name", "")
        phone = customer_info.get("phone", "")
        id_card = customer_info.get("idCard", "")
        medical_account = customer_info.get("medicalAccount", "")
        family_phone = customer_info.get("familyPhone", "")
        remark = customer_info.get("remark", "")
        source_type_str = data.get("sourceType", "manual")

        # Validate that at least one identifier is provided for matching
        if not name and not phone and not id_card:
            raise ValidationException(message="At least one of name, phone, or idCard is required for customer matching")

        # Create binding request
        ref_token = str(uuid.uuid4())
        binding_req = BindingRequest(
            distributor_id=promoter.id,
            submitted_by=submitted_by,
            customer_name=name or None,
            phone_masked=_mask_phone(phone) if phone else None,
            id_card_masked=_mask_id_card(id_card) if id_card else None,
            source_type=SourceType(source_type_str),
            ref_token=ref_token,
            consent_record_id=consent_record_id,
            status=BindingRequestStatus.PENDING_MATCH,
        )
        db.add(binding_req)
        await db.flush()
        await db.refresh(binding_req)

        # Call Rutai API to match customer
        match_status = "no_match"
        match_level = MatchLevel.NONE
        hrb_user_id: Optional[str] = None
        marked_source: Optional[str] = None
        rutai_error: Optional[str] = None

        try:
            rutai_result = await self.rutai.bind_bj_user(
                request_id=str(binding_req.id),
                patient_name=name or "",
                patient_phone=phone or "",
                id_card=id_card or "",
                medical_account=medical_account or "",
                family_phone=family_phone or "",
                source="BJTR",
                ref_token=ref_token,
            )
            match_status = rutai_result.get("match_status", "no_match")
            match_level_str = rutai_result.get("match_level", "none")
            hrb_user_id = rutai_result.get("hrb_user_id")
            marked_source = rutai_result.get("marked_source")

            try:
                match_level = MatchLevel(match_level_str)
            except ValueError:
                match_level = MatchLevel.NONE
        except Exception as exc:
            rutai_error = str(exc)
            match_status = "error"
            match_level = MatchLevel.NONE

        # Update status based on Rutai response
        now = datetime.utcnow()
        if match_status == "matched":
            binding_req.status = BindingRequestStatus.BOUND
            binding_req.match_level = match_level
            binding_req.bound_at = now
            binding_req.rutai_user_id_masked = hrb_user_id
        elif match_status == "no_match":
            binding_req.status = BindingRequestStatus.NO_CONSUME
            binding_req.match_level = match_level
            binding_req.failure_reason = "Rutai: no matching user found"
        elif match_status == "pending":
            binding_req.status = BindingRequestStatus.MATCHING
            binding_req.match_level = match_level
        elif match_status == "error":
            binding_req.status = BindingRequestStatus.ABNORMAL
            binding_req.failure_reason = rutai_error
            # Do NOT set next_retry_at on initial failure — only after an actual retry
        else:
            binding_req.status = BindingRequestStatus.MATCHING
            binding_req.match_level = match_level

        await db.flush()
        await db.refresh(binding_req)

        # Create change log
        log = BindingChangeLog(
            binding_request_id=binding_req.id,
            operation_type=OperationType.BIND,
            previous_promoter_id=None,
            new_promoter_id=promoter.id,
            operator_id=submitted_by,
            reason="Binding request submitted",
        )
        db.add(log)
        await db.flush()

        # If matched, create/update Customer record
        if binding_req.status == BindingRequestStatus.BOUND and hrb_user_id:
            existing_customer_id = None
            if id_card:
                existing_result = await db.execute(
                    select(Customer.id).where(Customer.id_card_encrypted == id_card)
                )
                existing_customer_id = existing_result.scalars().first()

            if existing_customer_id is not None:
                # FR-007: reuse the existing profile (e.g. manually created 待绑定
                # customer) instead of creating a duplicate record.
                customer = await db.get(Customer, existing_customer_id)
                customer.binding_status = BindingStatus.BOUND
                customer.rutai_user_id = hrb_user_id
                customer.bound_at = now
                if not customer.id_card_encrypted and id_card:
                    customer.id_card_encrypted = id_card
                    customer.id_card_masked = _mask_id_card(id_card)
                if not customer.phone and phone:
                    customer.phone = phone
                    customer.phone_masked = _mask_phone(phone)
                if not customer.medical_account_encrypted and medical_account:
                    customer.medical_account_encrypted = medical_account
                if customer.distributor_id != promoter.id:
                    previous_distributor_id = customer.distributor_id
                    customer.distributor_id = promoter.id
                    from ..models.customer_change_log import ChangeOperationType, CustomerChangeLog

                    db.add(CustomerChangeLog(
                        customer_id=customer.id,
                        operation_type=ChangeOperationType.TRANSFER,
                        previous_distributor_id=previous_distributor_id,
                        new_distributor_id=promoter.id,
                        operator_id=submitted_by,
                        reason="绑定流程匹配成功，推广员更新",
                    ))
                customer.version += 1
                db.add(customer)
                await db.flush()
            else:
                customer = Customer(
                    distributor_id=promoter.id,
                    name=name or None,
                    phone=phone or None,
                    phone_masked=_mask_phone(phone) if phone else None,
                    id_card_encrypted=id_card or None,
                    id_card_masked=_mask_id_card(id_card) if id_card else None,
                    medical_account_encrypted=medical_account or None,
                    family_phone=family_phone,
                    rutai_user_id=hrb_user_id,
                    note=remark,
                    binding_status=BindingStatus.BOUND,
                    bound_at=now,
                    version=1,
                )
                db.add(customer)
                await db.flush()
            binding_req.customer_id = customer.id
            await db.flush()

        # Get promoter name for response
        promoter_user_result = await db.execute(
            select(User.name).where(User.id == promoter_user_id)
        )
        promoter_name = promoter_user_result.scalar()

        return {
            "requestId": str(binding_req.id),
            "status": binding_req.status.value,
            "statusLabel": STATUS_LABELS.get(binding_req.status.value, binding_req.status.value),
            "promoterId": str(promoter_user_id),
            "promoterName": promoter_name,
            "matchLevel": binding_req.match_level.value if binding_req.match_level else None,
            "submittedAt": binding_req.created_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if binding_req.created_at else now.isoformat(),
            "expiresAt": (binding_req.created_at + timedelta(days=BINDING_EXPIRY_DAYS)).strftime("%Y-%m-%dT%H:%M:%S+08:00") if binding_req.created_at else None,
        }

    # ==================================================================
    # List Binding Requests
    # ==================================================================

    async def get_binding_requests(
        self,
        db: AsyncSession,
        *,
        status: Optional[str] = None,
        role: str = "initiator",
        cursor: Optional[str] = None,
        page_size: int = 20,
        submitted_by_me: Optional[int] = None,
        keyword: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        """List binding requests with filters and cursor pagination."""
        page_size = max(1, min(page_size, 100))

        query = select(BindingRequest).options(
            selectinload(BindingRequest.distributor).selectinload(Distributor.user),
        )

        # Filter by status
        if status:
            try:
                req_status = BindingRequestStatus(status)
                query = query.where(BindingRequest.status == req_status)
            except ValueError:
                pass

        # Filter by submitted_by
        if submitted_by_me is not None:
            query = query.where(BindingRequest.submitted_by == submitted_by_me)

        # Keyword search
        if keyword:
            kw = f"%{keyword}%"
            query = query.where(
                or_(
                    BindingRequest.customer_name.ilike(kw),
                    BindingRequest.phone_masked.ilike(kw),
                )
            )

        # Cursor pagination (cursor is base64-encoded binding request id)
        if cursor:
            try:
                decoded = _decode_cursor(cursor)
                cursor_id = int(decoded)
                query = query.where(BindingRequest.id < cursor_id)
            except Exception:
                pass

        # Total count
        count_stmt = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Ordering
        if sort_order == "asc":
            query = query.order_by(BindingRequest.created_at.asc())
        else:
            query = query.order_by(BindingRequest.created_at.desc())

        query = query.limit(page_size + 1)
        result = await db.execute(query)
        binding_requests = result.scalars().all()

        has_more = len(binding_requests) > page_size
        items_list = binding_requests[:page_size]

        items: list[dict[str, Any]] = []
        submitted_by_ids = {br.submitted_by for br in items_list}
        # Batch fetch submitter users
        user_map: dict[int, User] = {}
        if submitted_by_ids:
            users_result = await db.execute(
                select(User).where(User.id.in_(submitted_by_ids))
            )
            for u in users_result.scalars():
                user_map[u.id] = u

        for br in items_list:
            proms = br.distributor
            promoter_user = proms.user if proms else None
            submitter = user_map.get(br.submitted_by)

            items.append({
                "requestId": str(br.id),
                "status": br.status.value,
                "statusLabel": STATUS_LABELS.get(br.status.value, br.status.value),
                "matchLevel": br.match_level.value if br.match_level else None,
                "initiator": {
                    "userId": str(br.submitted_by),
                    "displayName": submitter.name if submitter else None,
                    "avatarUrl": submitter.avatar_url if submitter else None,
                    "phone": submitter.phone_masked if submitter else None,
                },
                "target": {
                    "userId": str(promoter_user.id) if promoter_user else None,
                    "displayName": promoter_user.name if promoter_user else None,
                    "avatarUrl": promoter_user.avatar_url if promoter_user else None,
                    "phone": promoter_user.phone_masked if promoter_user else None,
                },
                "customerInfo": {
                    "name": br.customer_name,
                    "phone": br.phone_masked,
                    "idCard": br.id_card_masked,
                    "medicalAccount": None,
                    "familyPhone": None,
                    "remark": None,
                },
                "submittedAt": br.created_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if br.created_at else "",
                "expiresAt": (br.created_at + timedelta(days=BINDING_EXPIRY_DAYS)).strftime("%Y-%m-%dT%H:%M:%S+08:00") if br.created_at else None,
                "resolvedAt": br.bound_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if br.bound_at else None,
                "retryCount": br.retry_count,
                "failureReason": br.failure_reason,
            })

        next_cursor: Optional[str] = None
        if has_more and items_list:
            last_item = items_list[-1]
            next_cursor = _encode_cursor(str(last_item.id))

        return {
            "items": items,
            "nextCursor": next_cursor,
            "hasMore": has_more,
        }

    # ==================================================================
    # Binding Detail
    # ==================================================================

    async def get_binding_detail(
        self,
        db: AsyncSession,
        binding_request_id: int,
    ) -> dict[str, Any]:
        """Get full detail for a binding request including audit events."""
        # Use populate_existing to ensure fresh data even if the object
        # was previously loaded in the same session.
        result = await db.execute(
            select(BindingRequest)
            .options(
                selectinload(BindingRequest.distributor).selectinload(Distributor.user),
                selectinload(BindingRequest.change_logs),
            )
            .where(BindingRequest.id == binding_request_id)
            .execution_options(populate_existing=True)
        )
        br = result.scalars().first()
        if br is None:
            raise NotFoundException(code=40400, message="Binding request not found")

        promoter_user = br.distributor.user if br.distributor else None

        # Get submitter user
        submitter_result = await db.execute(
            select(User).where(User.id == br.submitted_by)
        )
        submitter = submitter_result.scalars().first()

        # Build events from change logs
        events: list[dict[str, Any]] = []
        action_labels: dict[str, str] = {
            "bind": "提交申请",
            "unbind": "解除绑定",
            "transfer": "转移绑定",
        }
        for log in sorted(br.change_logs, key=lambda l: l.created_at):
            events.append({
                "action": log.operation_type.value,
                "actionLabel": action_labels.get(log.operation_type.value, log.operation_type.value),
                "operatorId": str(log.operator_id),
                "operatorName": None,
                "timestamp": log.created_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if log.created_at else "",
            })

        return {
            "requestId": str(br.id),
            "status": br.status.value,
            "statusLabel": STATUS_LABELS.get(br.status.value, br.status.value),
            "matchLevel": br.match_level.value if br.match_level else None,
            "initiator": {
                "userId": str(br.submitted_by),
                "displayName": submitter.name if submitter else None,
                "avatarUrl": submitter.avatar_url if submitter else None,
                "phone": submitter.phone_masked if submitter else None,
            },
            "target": {
                "userId": str(promoter_user.id) if promoter_user else None,
                "displayName": promoter_user.name if promoter_user else None,
                "avatarUrl": promoter_user.avatar_url if promoter_user else None,
                "phone": promoter_user.phone_masked if promoter_user else None,
            },
            "customerInfo": {
                "name": br.customer_name,
                "phone": br.phone_masked,
                "idCard": br.id_card_masked,
                "medicalAccount": None,
                "familyPhone": None,
                "remark": None,
            },
            "events": events,
            "submittedAt": br.created_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if br.created_at else "",
            "expiresAt": (br.created_at + timedelta(days=BINDING_EXPIRY_DAYS)).strftime("%Y-%m-%dT%H:%M:%S+08:00") if br.created_at else None,
            "resolvedAt": br.bound_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if br.bound_at else None,
            "retryCount": br.retry_count,
            "failureReason": br.failure_reason,
            "version": br.version,
        }

    # ==================================================================
    # Retry Binding
    # ==================================================================

    async def retry_binding(
        self,
        db: AsyncSession,
        binding_request_id: int,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Retry a failed/abnormal binding request.

        Only retryable from ABNORMAL, MANUAL_REVIEW, or NO_CONSUME states.
        Max 3 retries with 10-minute interval between retries.
        """
        result = await db.execute(
            select(BindingRequest)
            .options(selectinload(BindingRequest.distributor).selectinload(Distributor.user))
            .where(BindingRequest.id == binding_request_id)
        )
        br = result.scalars().first()
        if br is None:
            raise NotFoundException(code=40400, message="Binding request not found")

        if br.status.value not in RETRYABLE_STATUSES:
            raise BadRequestException(
                code=40026,
                message="Can only retry abnormal, manual_review, or no_consume requests",
            )

        if br.retry_count >= MAX_RETRY_COUNT:
            raise BadRequestException(
                code=40026,
                message=f"Maximum retry count ({MAX_RETRY_COUNT}) reached",
            )

        # Check retry interval
        now = datetime.utcnow()
        if br.next_retry_at and now < br.next_retry_at:
            raise BadRequestException(
                code=40026,
                message=f"Next retry allowed at {br.next_retry_at.isoformat()}",
            )

        # Also check if user is already bound
        if br.customer_id:
            cust_result = await db.execute(
                select(Customer).where(
                    Customer.id == br.customer_id,
                    Customer.binding_status == BindingStatus.BOUND,
                )
            )
            if cust_result.scalars().first() is not None:
                raise ConflictException(
                    code=40022,
                    message="Already bound to this promoter",
                )

        # Increment retry count and set next retry
        br.retry_count += 1
        br.next_retry_at = now + timedelta(minutes=RETRY_INTERVAL_MINUTES)
        br.status = BindingRequestStatus.RETRYING

        # Call Rutai API again
        try:
            rutai_result = await self.rutai.bind_bj_user(
                request_id=str(br.id),
                patient_name=br.customer_name or "",
                patient_phone="",  # phone is masked, use what we have
                id_card="",
                medical_account="",
                family_phone="",
                source="BJTR",
                ref_token=br.ref_token or str(uuid.uuid4()),
            )
            match_status = rutai_result.get("match_status", "no_match")
            match_level_str = rutai_result.get("match_level", "none")

            try:
                br.match_level = MatchLevel(match_level_str)
            except ValueError:
                br.match_level = MatchLevel.NONE

            if match_status == "matched":
                br.status = BindingRequestStatus.BOUND
                br.bound_at = now
                br.rutai_user_id_masked = rutai_result.get("hrb_user_id")
                br.failure_reason = None
            elif match_status == "no_match":
                br.status = BindingRequestStatus.NO_CONSUME
                br.failure_reason = "Rutai: still no matching user found"
            elif match_status == "pending":
                br.status = BindingRequestStatus.MATCHING
                br.failure_reason = None
            else:
                br.status = BindingRequestStatus.ABNORMAL
                br.failure_reason = "Rutai: unknown match_status"
        except Exception as exc:
            br.status = BindingRequestStatus.ABNORMAL
            br.failure_reason = str(exc)

        await db.flush()
        await db.refresh(br)

        promoter_user = br.distributor.user if br.distributor else None

        return {
            "requestId": str(br.id),
            "status": br.status.value,
            "statusLabel": STATUS_LABELS.get(br.status.value, br.status.value),
            "promoterId": str(promoter_user.id) if promoter_user else None,
            "promoterName": promoter_user.name if promoter_user else None,
            "matchLevel": br.match_level.value if br.match_level else None,
            "submittedAt": br.created_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if br.created_at else now.isoformat(),
            "expiresAt": (now + timedelta(days=BINDING_EXPIRY_DAYS)).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        }

    # ==================================================================
    # Update Customer Info
    # ==================================================================

    async def update_customer_info(
        self,
        db: AsyncSession,
        binding_request_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update customer info on a binding request. Only allowed for pending/match requests."""
        result = await db.execute(
            select(BindingRequest).where(BindingRequest.id == binding_request_id)
        )
        br = result.scalars().first()
        if br is None:
            raise NotFoundException(code=40400, message="Binding request not found")

        # Only allow updates if not already bound/unbound/transferred
        if br.status in (BindingRequestStatus.BOUND, BindingRequestStatus.UNBOUND, BindingRequestStatus.TRANSFERRED):
            raise BadRequestException(
                code=40027,
                message="Can only update customer info for requests that are not yet bound, unbound, or transferred",
            )

        version = data.get("version", 0)
        if version != br.version:
            raise ConflictException(message="Version conflict: binding request has been modified")

        # Update fields
        if "name" in data and data["name"] is not None:
            br.customer_name = data["name"]
        if "phone" in data and data["phone"] is not None:
            br.phone_masked = _mask_phone(data["phone"])
        if "idCard" in data and data["idCard"] is not None:
            br.id_card_masked = _mask_id_card(data["idCard"])
        reason = data.get("reason")
        if reason:
            br.failure_reason = f"Info correction: {reason}"

        br.status = BindingRequestStatus.PENDING_MATCH
        br.version += 1
        br.updated_at = datetime.utcnow()

        await db.flush()
        await db.refresh(br)

        return {
            "requestId": str(br.id),
            "customerInfo": {
                "name": br.customer_name,
                "phone": br.phone_masked,
                "idCard": br.id_card_masked,
                "medicalAccount": None,
                "familyPhone": None,
                "remark": None,
            },
            "updatedAt": br.updated_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if br.updated_at else "",
        }

    # ==================================================================
    # Binding Summary
    # ==================================================================

    async def get_binding_summary(
        self,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Get binding summary counts."""
        filters: list = []
        if user_id is not None:
            filters.append(BindingRequest.submitted_by == user_id)

        # Total bindings
        total_q = select(func.count(BindingRequest.id))
        if filters:
            total_q = total_q.where(and_(*filters))
        total_result = await db.execute(total_q)
        total_bindings = total_result.scalar() or 0

        # Active/bound
        bound_q = select(func.count(BindingRequest.id)).where(
            BindingRequest.status == BindingRequestStatus.BOUND
        )
        if filters:
            bound_q = bound_q.where(and_(*filters))
        bound_result = await db.execute(bound_q)
        active_bindings = bound_result.scalar() or 0

        # Pending (pending_match + matching)
        pending_q = select(func.count(BindingRequest.id)).where(
            BindingRequest.status.in_([
                BindingRequestStatus.PENDING_MATCH,
                BindingRequestStatus.MATCHING,
                BindingRequestStatus.RETRYING,
                BindingRequestStatus.MANUAL_REVIEW,
            ])
        )
        if filters:
            pending_q = pending_q.where(and_(*filters))
        pending_result = await db.execute(pending_q)
        pending_requests = pending_result.scalar() or 0

        # Rejected / abnormal / expired (anything other than bound/pending)
        rejected_q = select(func.count(BindingRequest.id)).where(
            BindingRequest.status.in_([
                BindingRequestStatus.ABNORMAL,
                BindingRequestStatus.NO_CONSUME,
            ])
        )
        if filters:
            rejected_q = rejected_q.where(and_(*filters))
        rejected_result = await db.execute(rejected_q)
        rejected_requests = rejected_result.scalar() or 0

        # Expired (requests older than 7 days that are not resolved)
        expired_cutoff = datetime.utcnow() - timedelta(days=BINDING_EXPIRY_DAYS)
        expired_q = select(func.count(BindingRequest.id)).where(
            BindingRequest.created_at < expired_cutoff,
            BindingRequest.status.notin_([
                BindingRequestStatus.BOUND,
                BindingRequestStatus.UNBOUND,
                BindingRequestStatus.TRANSFERRED,
            ]),
        )
        if filters:
            expired_q = expired_q.where(and_(*filters))
        expired_result = await db.execute(expired_q)
        expired_requests = expired_result.scalar() or 0

        # Last binding
        last_q = select(BindingRequest.bound_at).where(
            BindingRequest.bound_at.isnot(None)
        ).order_by(BindingRequest.bound_at.desc()).limit(1)
        if filters:
            last_q = last_q.where(and_(*filters))
        last_result = await db.execute(last_q)
        last_binding_at = last_result.scalars().first()
        last_binding_at_str = last_binding_at.strftime("%Y-%m-%dT%H:%M:%S+08:00") if last_binding_at else None

        return {
            "totalBindings": total_bindings,
            "activeBindings": active_bindings,
            "pendingRequests": pending_requests,
            "rejectedRequests": rejected_requests,
            "expiredRequests": expired_requests,
            "lastBindingAt": last_binding_at_str,
        }



# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_binding_service: Optional[BindingService] = None


def get_binding_service() -> BindingService:
    global _binding_service
    if _binding_service is None:
        _binding_service = BindingService()
    return _binding_service
