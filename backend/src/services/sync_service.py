"""Sync service: polling bind users, fetching bills, idempotent upsert, refund handling.

Coordinates with RutaiClient for API calls. 业绩贡献 = 消费金额，直接由
Bill.paid_amount_cent 汇总，无需额外贡献记录。
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.exceptions import ValidationException
from ..integrations.rutai_client import RutaiApiError, RutaiClient, get_rutai_client
from ..models.bill import Bill, TransactionStatus
from ..models.binding import (
    BindingRequest,
    BindingRequestStatus,
    BindingStatus,
    Customer,
    MatchLevel,
    SourceType,
)
from ..models.consent import ConsentRecord, ConsentScene
from ..models.customer_change_log import CustomerChangeLog
from ..models.distributor import Distributor
from ..models.followup import FollowupRecord
from ..models.organization import Organization
from ..models.notification import Notification, NotificationCategory
from ..models.promotion import PromotionCode
from .binding_service import MAX_RETRY_COUNT, RETRY_INTERVAL_MINUTES, _mask_phone, _normalize_phone
from .performance_period_service import bump_unfrozen_periods, period_for_datetime

settings = get_settings()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level sync state (shared across SyncService instances)
# ---------------------------------------------------------------------------
_sync_state: dict[str, Any] = {
    "last_bind_user_poll": None,       # datetime of last successful getBindUser
    "last_bill_sync": None,            # datetime of last successful bill sync
    "last_success": None,              # datetime of last overall success
    "failure_count": 0,                # consecutive failure count
    "pending_retries": 0,              # count of pending retries
    "is_polling": False,               # whether polling is active
    "circuit_breaker_open": False,     # whether circuit breaker is tripped
    "last_cursor": None,               # last successful bind user cursor
}
_state_lock = threading.Lock()

_MATCHABLE_BINDING_REQUEST_STATUSES = (
    BindingRequestStatus.PENDING_MATCH,
    BindingRequestStatus.MATCHING,
    BindingRequestStatus.RETRYING,
    BindingRequestStatus.NO_CONSUME,
    BindingRequestStatus.MANUAL_REVIEW,
    BindingRequestStatus.ABNORMAL,
    BindingRequestStatus.BOUND,
)


def _authorized_scan_requests(now: datetime):
    return (
        select(BindingRequest)
        .join(ConsentRecord, ConsentRecord.id == BindingRequest.consent_record_id)
        .where(
            BindingRequest.source_type == SourceType.SCAN,
            BindingRequest.ref_token.isnot(None),
            ConsentRecord.customer_id == BindingRequest.customer_id,
            ConsentRecord.scene == ConsentScene.BINDING,
            ConsentRecord.confirmed.is_(True),
            ConsentRecord.status == "active",
            ConsentRecord.scopes["phone"].as_boolean().is_(True),
            ConsentRecord.scopes["customer_attribution"].as_boolean().is_(True),
            or_(ConsentRecord.expires_at.is_(None), ConsentRecord.expires_at > now),
        )
    )


def _update_state(**kwargs) -> None:
    """Thread-safe update of sync state."""
    with _state_lock:
        _sync_state.update(kwargs)


def _get_state() -> dict:
    """Thread-safe copy of sync state."""
    with _state_lock:
        return dict(_sync_state)


# ---------------------------------------------------------------------------
# SyncService
# ---------------------------------------------------------------------------
class SyncService:
    """Orchestrates data sync between Rutai API and local database."""

    def __init__(self) -> None:
        self._rutai_client: Optional[RutaiClient] = None

    @property
    def _client(self) -> RutaiClient:
        if self._rutai_client is None:
            self._rutai_client = get_rutai_client()
        return self._rutai_client

    async def pending_scan_customers(self, db: AsyncSession, limit: int = 10) -> list[int]:
        """Find customers with an authorized scan ready for a matching attempt."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = (
            _authorized_scan_requests(now)
            .with_only_columns(BindingRequest.customer_id)
            .join(Customer, Customer.id == BindingRequest.customer_id)
            .where(
                Customer.binding_status == BindingStatus.BOUND,
                Customer.distributor_id == BindingRequest.distributor_id,
                Customer.phone_masked == BindingRequest.phone_masked,
                BindingRequest.status == BindingRequestStatus.PENDING_MATCH,
                or_(BindingRequest.next_retry_at.is_(None), BindingRequest.next_retry_at <= now),
            )
            .group_by(BindingRequest.customer_id)
            .order_by(func.min(BindingRequest.id))
            .limit(limit)
        )
        return list((await db.scalars(query)).all())

    async def submit_scan_match(self, db: AsyncSession, customer_id: int) -> None:
        """Submit one match per customer and apply its outcome to repeat scans."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        requests = (await db.scalars(
            _authorized_scan_requests(now)
            .where(
                BindingRequest.customer_id == customer_id,
                BindingRequest.status.in_(_MATCHABLE_BINDING_REQUEST_STATUSES),
            )
            .order_by(BindingRequest.id)
            .with_for_update()
        )).all()
        customer = await db.get(Customer, customer_id, with_for_update=True)
        if customer is None or customer.binding_status != BindingStatus.BOUND:
            return

        requests = [
            request for request in requests
            if request.distributor_id == customer.distributor_id
            and request.phone_masked == customer.phone_masked
        ]
        waiting = [request for request in requests if request.status == BindingRequestStatus.PENDING_MATCH]
        if not waiting:
            return

        # Use the original request ID on retries and share its outcome with later scans.
        request = next(
            row for row in requests
            if row.status in (
                BindingRequestStatus.PENDING_MATCH, BindingRequestStatus.MATCHING,
                BindingRequestStatus.RETRYING, BindingRequestStatus.BOUND,
            ) or row.retry_count > 0
        )
        status, level, reason = request.status, request.match_level, request.failure_reason
        retry_at = request.next_retry_at
        rutai_id = customer.rutai_user_id
        if rutai_id and not rutai_id.startswith("hrb_mock_"):
            status, reason, retry_at = BindingRequestStatus.BOUND, None, None
        elif status == BindingRequestStatus.BOUND or rutai_id:
            status, reason, retry_at = BindingRequestStatus.MANUAL_REVIEW, "缺少有效的儒泰用户 ID", None
        elif status == BindingRequestStatus.PENDING_MATCH and (retry_at is None or retry_at <= now):
            try:
                phone = _normalize_phone(customer.phone_normalized or customer.phone)
                if _mask_phone(phone) != request.phone_masked:
                    raise ValidationException(message="扫码手机号与当前档案不一致")
            except ValidationException:
                status, reason, retry_at = BindingRequestStatus.MANUAL_REVIEW, "扫码手机号无法核实", None
            else:
                request.retry_count += 1
                try:
                    result = await asyncio.wait_for(self._client.bind_bj_user(
                        request_id=str(request.id),
                        patient_name="",
                        patient_phone=phone,
                        id_card="",
                        medical_account="",
                        family_phone="",
                        source="BJTR",
                        ref_token=request.ref_token,
                    ), timeout=30)
                except (TimeoutError, RutaiApiError, ValueError):
                    result = {}
                if not isinstance(result, dict):
                    result = {}

                outcome = result.get("match_status")
                external_id = str(result.get("hrb_user_id") or "").strip()
                returned_request_id = result.get("request_id") or result.get("binding_request_id")
                if outcome == "matched" and returned_request_id and str(returned_request_id) != str(request.id):
                    status, reason, retry_at = BindingRequestStatus.MANUAL_REVIEW, "儒泰返回的申请编号不一致", None
                elif outcome == "matched" and external_id and not external_id.startswith("hrb_mock_"):
                    await self._import_customer(db, {
                        **result,
                        "request_id": str(request.id),
                        "ref_token": result.get("ref_token") or request.ref_token,
                        "phone_masked": result.get("phone_masked") or request.phone_masked,
                        "hrb_user_id": external_id,
                    })
                    if request.status == BindingRequestStatus.BOUND:
                        return
                    status, reason, retry_at = BindingRequestStatus.MANUAL_REVIEW, "儒泰匹配结果与本地档案存在冲突", None
                elif outcome == "pending":
                    status, reason, retry_at = BindingRequestStatus.MATCHING, None, None
                elif outcome == "no_match":
                    has_bill = await db.scalar(select(Bill.id).where(Bill.customer_id == customer_id).limit(1))
                    status = BindingRequestStatus.MANUAL_REVIEW if has_bill is not None else BindingRequestStatus.NO_CONSUME
                    reason = "已有消费记录，需核对儒泰账号" if has_bill is not None else "儒泰未匹配到客户"
                    level, retry_at = MatchLevel.NONE, None
                else:
                    reason = "儒泰匹配接口暂未返回有效结果"
                    if request.retry_count >= MAX_RETRY_COUNT:
                        status, retry_at = BindingRequestStatus.ABNORMAL, None
                    else:
                        retry_at = now + timedelta(minutes=RETRY_INTERVAL_MINUTES)

        for row in waiting:
            if (row.status, row.match_level, row.failure_reason, row.next_retry_at) == (status, level, reason, retry_at):
                continue
            row.status, row.match_level = status, level
            row.failure_reason, row.next_retry_at = reason, retry_at
            if status == BindingRequestStatus.BOUND:
                row.rutai_user_id_masked = rutai_id
                row.bound_at = customer.bound_at or now
            row.version += 1

    # ------------------------------------------------------------------
    # Alert notification helper
    # ------------------------------------------------------------------
    async def _send_alert(
        self,
        db: AsyncSession,
        title: str,
        summary: str,
    ) -> None:
        """Send an alert notification to admin users about sync failures."""
        try:
            from ..models.user import User, UserType

            # Notifications belong to users, while the admin console has a
            # separate AdminAccount table.  Resolve actual user records by
            # admin role instead of reusing an unrelated admin_account id.
            admin_result = await db.execute(
                select(User).where(
                    User.user_type.in_([UserType.ADMIN, UserType.FINANCE, UserType.OPS]),
                    User.activation_status == "active",
                )
            )
            admins = admin_result.scalars().all()

            for admin in admins:
                notification = Notification(
                    user_id=admin.id,
                    category=NotificationCategory.SYSTEM,
                    title=title,
                    summary=summary,
                )
                db.add(notification)
            await db.flush()
        except Exception:
            pass  # alert failure must not break sync

    # ------------------------------------------------------------------
    # getBindUser polling
    # ------------------------------------------------------------------
    async def poll_bind_users(
        self,
        db: AsyncSession,
    ) -> dict:
        """Poll Rutai for new bound users and import them as Customers.

        Uses cursor-based pagination to process all available pages.
        New users trigger subsequent bill fetching.

        Returns:
            Dict with processed, imported, pages counts.
        """
        if _sync_state["is_polling"]:
            return {"status": "skipped", "message": "Poll already in progress"}

        _update_state(is_polling=True)

        try:
            total_processed = 0
            total_imported = 0
            page_count = 0
            cursor: Optional[str] = _sync_state.get("last_cursor")

            while True:
                page_count += 1
                try:
                    response = await self._client.get_bind_user(
                        cursor=cursor,
                        source="BJTR",
                        db_session=db,
                    )
                except Exception:
                    _update_state(
                        failure_count=_sync_state["failure_count"] + 1,
                        is_polling=False,
                    )
                    self._check_alert_threshold(db)
                    raise

                _update_state(failure_count=0)

                items = response.get("items", [])
                total_processed += len(items)

                for item in items:
                    hrb_user_id = item.get("hrb_user_id")
                    if hrb_user_id:
                        imported = await self._import_customer(db, item)
                        if imported:
                            total_imported += 1

                has_more = response.get("has_more", False)
                cursor = response.get("next_cursor")

                if not has_more or not cursor:
                    break

            now = datetime.now(timezone.utc)
            _update_state(
                last_bind_user_poll=now,
                last_success=now,
                last_cursor=cursor,
                is_polling=False,
            )

            return {
                "processed": total_processed,
                "imported": total_imported,
                "pages": page_count,
            }

        except Exception:
            _update_state(is_polling=False)
            raise

    async def _find_binding_requests(
        self, db: AsyncSession, item: dict
    ) -> Optional[list[BindingRequest]]:
        """Resolve a Rutai bind-user result to its originating local request."""
        request_id = item.get("request_id") or item.get("binding_request_id")
        if request_id is not None:
            try:
                parsed_id = int(request_id)
            except (TypeError, ValueError):
                parsed_id = None
            if parsed_id is not None:
                result = await db.execute(
                    select(BindingRequest)
                    .where(BindingRequest.id == parsed_id)
                    .with_for_update()
                )
                request = result.scalars().first()
                if request is not None:
                    return [request]

        ref_token = item.get("ref_token")
        if not ref_token:
            return []

        query = select(BindingRequest).where(BindingRequest.ref_token == str(ref_token))
        phone_masked = item.get("phone_masked")
        if phone_masked:
            query = query.where(BindingRequest.phone_masked == str(phone_masked))
        result = await db.execute(query.with_for_update())
        requests = result.scalars().all()
        if not requests:
            return []
        if len(requests) > 1 and not phone_masked:
            logger.warning(
                "Cannot reconcile Rutai user %s: ref token matches multiple requests without a phone key",
                item.get("hrb_user_id"),
            )
            return None

        matchable = [
            request
            for request in requests
            if request.status in _MATCHABLE_BINDING_REQUEST_STATUSES
        ]
        if not matchable:
            return requests[:1]
        identities = {(request.customer_id, request.distributor_id) for request in matchable}
        if len(identities) > 1 or (len(matchable) > 1 and None in {item[0] for item in identities}):
            logger.warning(
                "Cannot reconcile Rutai user %s: ref token and masked phone match multiple local customers",
                item.get("hrb_user_id"),
            )
            return None
        return matchable

    async def _merge_imported_customer(
        self,
        db: AsyncSession,
        imported: Customer,
        local: Customer,
        distributor_id: int,
        phone_masked: Optional[str],
        request_correlated: bool,
    ) -> bool:
        """Merge a prior sync-created duplicate into a correlated local customer.

        Only an unowned Rutai import with a matching distributor and phone may be
        merged. Related bills and audit/follow-up records are moved before deleting
        the duplicate so no business history is discarded.
        """
        if imported.id == local.id:
            return True
        if (
            imported.distributor_id != distributor_id
            or local.distributor_id not in (None, distributor_id)
            or imported.user_id is not None
            or imported.binding_status != BindingStatus.BOUND
            or imported.name is not None
            or imported.phone is not None
            or imported.phone_normalized is not None
            or imported.id_card_encrypted is not None
            or imported.id_card_masked is not None
            or imported.medical_account_encrypted is not None
            or imported.family_phone is not None
            or imported.note is not None
            or local.rutai_user_id not in (None, imported.rutai_user_id)
            or local.binding_status == BindingStatus.UNBOUND
            or phone_masked and local.phone_masked and local.phone_masked != phone_masked
            or phone_masked and imported.phone_masked and imported.phone_masked != phone_masked
            or imported.phone_masked and local.phone_masked and imported.phone_masked != local.phone_masked
            or (
                not request_correlated
                and (
                    not phone_masked
                    or imported.phone_masked != phone_masked
                    or local.phone_masked != phone_masked
                )
            )
        ):
            return False

        duplicate_requests_result = await db.execute(
            select(BindingRequest).where(BindingRequest.customer_id == imported.id)
        )
        if any(
            request.status == BindingRequestStatus.BOUND
            and request.rutai_user_id_masked not in (None, imported.rutai_user_id)
            for request in duplicate_requests_result.scalars().all()
        ):
            return False

        if local.distributor_id is None:
            local.distributor_id = distributor_id
        for field in (
            "name",
            "phone",
            "phone_normalized",
            "phone_masked",
            "id_card_encrypted",
            "id_card_masked",
            "medical_account_encrypted",
            "family_phone",
            "note",
        ):
            if getattr(local, field) is None:
                setattr(local, field, getattr(imported, field))

        for model in (Bill, ConsentRecord, FollowupRecord, CustomerChangeLog):
            await db.execute(
                update(model)
                .where(model.customer_id == imported.id)
                .values(customer_id=local.id)
            )

        linked_result = await db.execute(
            select(BindingRequest).where(BindingRequest.customer_id == imported.id)
        )
        for linked_request in linked_result.scalars().all():
            linked_request.customer_id = local.id

        await db.delete(imported)
        await db.flush()
        return True

    async def _import_customer(self, db: AsyncSession, item: dict) -> bool:
        """Reconcile a Rutai match with its original local customer and request.

        Returns True only when a new customer record had to be created.
        """
        raw_hrb_user_id = item.get("hrb_user_id")
        if not raw_hrb_user_id:
            return False
        hrb_user_id = str(raw_hrb_user_id)
        phone_masked = str(item.get("phone_masked") or "") or None
        ref_token = str(item.get("ref_token") or "") or None

        now = datetime.utcnow()
        marked_at = item.get("marked_at")
        if marked_at:
            try:
                parsed = datetime.fromisoformat(str(marked_at).replace("Z", "+00:00"))
                now = (
                    parsed.astimezone(timezone.utc).replace(tzinfo=None)
                    if parsed.tzinfo
                    else parsed
                )
            except (TypeError, ValueError):
                pass

        match_level = None
        try:
            match_level = MatchLevel(str(item.get("bind_method") or item.get("match_level")))
        except ValueError:
            pass

        binding_requests = await self._find_binding_requests(db, item)
        if binding_requests is None:
            return False
        if any(
            request.status not in _MATCHABLE_BINDING_REQUEST_STATUSES
            for request in binding_requests
        ):
            logger.info(
                "Skip late Rutai result for closed binding request(s): user=%s",
                hrb_user_id,
            )
            return False
        if ref_token and any(
            request.ref_token and request.ref_token != ref_token
            for request in binding_requests
        ):
            logger.warning(
                "Cannot reconcile Rutai user %s: request ID and ref token disagree",
                hrb_user_id,
            )
            return False
        if any(
            request.status == BindingRequestStatus.BOUND
            and request.rutai_user_id_masked not in (None, hrb_user_id)
            for request in binding_requests
        ):
            logger.warning(
                "Cannot reconcile Rutai user %s: matched request already records another Rutai user ID",
                hrb_user_id,
            )
            return False
        if phone_masked and any(
            request.phone_masked and request.phone_masked != phone_masked
            for request in binding_requests
        ):
            logger.warning(
                "Cannot reconcile Rutai user %s: matched request phone does not match Rutai phone",
                hrb_user_id,
            )
            return False
        distributor_ids = {request.distributor_id for request in binding_requests}
        if len(distributor_ids) > 1:
            logger.warning(
                "Cannot reconcile Rutai user %s: matched requests belong to different distributors",
                hrb_user_id,
            )
            return False
        distributor_id = next(iter(distributor_ids), None)

        if distributor_id is None and ref_token:
            promotion_result = await db.execute(
                select(PromotionCode).where(PromotionCode.ref_token == ref_token)
            )
            promotion_code = promotion_result.scalars().first()
            if promotion_code is not None:
                distributor_id = promotion_code.distributor_id

        if distributor_id is None:
            # A missing/unknown external ref_token must remain unassigned instead of
            # being incorrectly attributed to an arbitrary promoter.
            return False

        linked_customer_ids = {
            request.customer_id for request in binding_requests if request.customer_id is not None
        }
        if len(linked_customer_ids) > 1:
            logger.warning(
                "Cannot reconcile Rutai user %s: matched requests point to different local customers",
                hrb_user_id,
            )
            return False

        local_customer = None
        if linked_customer_ids:
            local_result = await db.execute(
                select(Customer)
                .where(Customer.id == next(iter(linked_customer_ids)))
                .with_for_update()
            )
            local_customer = local_result.scalars().first()

        if local_customer is None and phone_masked:
            local_result = await db.execute(
                select(Customer)
                .where(
                    Customer.distributor_id == distributor_id,
                    Customer.phone_masked == phone_masked,
                    Customer.rutai_user_id.is_(None),
                    Customer.binding_status != BindingStatus.UNBOUND,
                )
                .with_for_update()
            )
            local_candidates = local_result.scalars().all()
            if len(local_candidates) == 1:
                local_customer = local_candidates[0]
            elif len(local_candidates) > 1:
                logger.warning(
                    "Cannot reconcile Rutai user %s: multiple pending customers share the same owner and masked phone",
                    hrb_user_id,
                )
                return False

        existing_result = await db.execute(
            select(Customer)
            .where(Customer.rutai_user_id == hrb_user_id)
            .with_for_update()
        )
        existing_customer = existing_result.scalars().first()

        if local_customer is None and existing_customer is None and not phone_masked and not binding_requests:
            # Without the original request or a phone key, creating a second local
            # customer could duplicate an already-entered customer.
            logger.warning(
                "Skip Rutai user %s import: no request or masked phone available for safe correlation",
                hrb_user_id,
            )
            return False

        created = False
        if local_customer is None and existing_customer is None:
            local_customer = Customer(
                distributor_id=distributor_id,
                rutai_user_id=hrb_user_id,
                phone_masked=phone_masked,
                binding_status=BindingStatus.BOUND,
                bound_at=now,
            )
            db.add(local_customer)
            await db.flush()
            created = True
        elif local_customer is None:
            # The Rutai user was already imported; do not make another copy.
            local_customer = existing_customer
        if (
            local_customer.distributor_id not in (None, distributor_id)
            or local_customer.rutai_user_id not in (None, hrb_user_id)
            or local_customer.binding_status == BindingStatus.UNBOUND
            or (
                phone_masked
                and local_customer.phone_masked
                and local_customer.phone_masked != phone_masked
            )
        ):
            logger.warning(
                "Cannot reconcile Rutai user %s: local customer %s conflicts with the request",
                hrb_user_id,
                local_customer.id,
            )
            return False

        related_result = await db.execute(
            select(BindingRequest)
            .where(
                BindingRequest.customer_id == local_customer.id,
                BindingRequest.distributor_id == distributor_id,
                BindingRequest.status.in_(_MATCHABLE_BINDING_REQUEST_STATUSES),
            )
            .with_for_update()
        )
        related_requests = {request.id: request for request in related_result.scalars().all()}
        for request in binding_requests:
            if request.customer_id in (None, local_customer.id):
                related_requests[request.id] = request

        if any(
            request.status == BindingRequestStatus.BOUND
            and request.rutai_user_id_masked not in (None, hrb_user_id)
            for request in related_requests.values()
        ):
            logger.warning(
                "Cannot reconcile Rutai user %s: local binding request already records another Rutai user ID",
                hrb_user_id,
            )
            return False

        merged_duplicate = False
        if existing_customer is not None and existing_customer.id != local_customer.id:
            merged = await self._merge_imported_customer(
                db,
                existing_customer,
                local_customer,
                distributor_id,
                phone_masked,
                bool(binding_requests),
            )
            if not merged:
                logger.warning(
                    "Cannot merge duplicate Rutai customer %s into local customer %s due to ownership or identity conflict",
                    existing_customer.id,
                    local_customer.id,
                )
                return False
            merged_duplicate = True

            # Include any requests previously attached to the imported duplicate.
            merged_requests_result = await db.execute(
                select(BindingRequest).where(
                    BindingRequest.customer_id == local_customer.id,
                    BindingRequest.distributor_id == distributor_id,
                    BindingRequest.status.in_(_MATCHABLE_BINDING_REQUEST_STATUSES),
                )
            )
            related_requests.update({
                request.id: request for request in merged_requests_result.scalars().all()
            })

        customer_changed = (
            merged_duplicate
            or local_customer.distributor_id != distributor_id
            or local_customer.rutai_user_id != hrb_user_id
            or local_customer.binding_status != BindingStatus.BOUND
            or local_customer.bound_at is None
            or bool(phone_masked and not local_customer.phone_masked)
        )
        local_customer.distributor_id = distributor_id
        local_customer.rutai_user_id = hrb_user_id
        local_customer.binding_status = BindingStatus.BOUND
        local_customer.bound_at = local_customer.bound_at or now
        if phone_masked and not local_customer.phone_masked:
            local_customer.phone_masked = phone_masked
        if not created and customer_changed:
            local_customer.version += 1

        for request in related_requests.values():
            request.customer_id = local_customer.id
            request.status = BindingRequestStatus.BOUND
            request.rutai_user_id_masked = hrb_user_id
            request.bound_at = request.bound_at or now
            request.failure_reason = None
            request.next_retry_at = None
            if match_level is not None:
                request.match_level = match_level

        await db.flush()
        logger.info(
            "Reconciled Rutai user %s with local customer %s and %s binding request(s)",
            hrb_user_id,
            local_customer.id,
            len(related_requests),
        )
        return created

    def _check_alert_threshold(self, db: AsyncSession) -> None:
        """Check if failure threshold is exceeded and send alert."""
        state = _get_state()
        if state["failure_count"] >= 5:
            asyncio.create_task(
                self._send_alert(
                    db,
                    title="数据同步异常",
                    summary=f"连续 {state['failure_count']} 次拉取绑定用户数据失败，请检查 Rutai API 连接。",
                )
            )

    # ------------------------------------------------------------------
    # getUserBill sync
    # ------------------------------------------------------------------
    async def fetch_user_bill(
        self,
        db: AsyncSession,
        hrb_user_id: str,
    ) -> dict:
        """Fetch bills for a specific Rutai user and upsert into local DB.

        Uses transaction_id as idempotency key. New bills trigger
        contribution calculation. Refunded bills trigger reversals.

        Args:
            db: Database session.
            hrb_user_id: The Rutai user ID to fetch bills for.

        Returns:
            Dict with created, skipped, updated, refunds_processed counts.
        """
        created = 0
        skipped = 0
        updated = 0
        refunds_processed = 0
        cursor: Optional[str] = None

        while True:
            try:
                response = await self._client.get_user_bill(
                    hrb_user_id=hrb_user_id,
                    cursor=cursor,
                    db_session=db,
                )
            except Exception:
                _update_state(failure_count=_sync_state["failure_count"] + 1)
                raise

            _update_state(failure_count=0)

            items = response.get("items", [])
            for item in items:
                result = await self._process_bill(db, hrb_user_id, item)
                if result == "created":
                    created += 1
                elif result == "skipped":
                    skipped += 1
                elif result == "updated":
                    updated += 1
                elif result == "refund_processed":
                    refunds_processed += 1

            has_more = response.get("has_more", False)
            cursor = response.get("next_cursor")
            if not has_more or not cursor:
                break

        now = datetime.now(timezone.utc)
        _update_state(last_bill_sync=now, last_success=now)

        return {
            "created": created,
            "skipped": skipped,
            "updated": updated,
            "refunds_processed": refunds_processed,
        }

    async def _process_bill(
        self,
        db: AsyncSession,
        hrb_user_id: str,
        item: dict,
    ) -> str:
        """Process a single bill item: insert, update, or handle refund.

        Returns one of: 'created', 'skipped', 'updated', 'refund_processed'.
        """
        transaction_id = item.get("transaction_id")
        if not transaction_id:
            return "skipped"

        # Check if bill already exists
        result = await db.execute(
            select(Bill).where(Bill.transaction_id == transaction_id)
        )
        existing_bill = result.scalars().first()

        transaction_status = item.get("transaction_status", "paid")
        is_refund = transaction_status in ("refunded", "partially_refunded")

        if existing_bill is not None:
            if is_refund and existing_bill.transaction_status != TransactionStatus.REFUNDED:
                # Process refund. An identical polling response must not dirty
                # the same month repeatedly.
                new_status = (
                    TransactionStatus.REFUNDED
                    if transaction_status == "refunded"
                    else TransactionStatus.PARTIALLY_REFUNDED
                )
                new_refund = item.get("refund_amount_cent", 0)
                if (
                    existing_bill.transaction_status == new_status
                    and existing_bill.refund_amount_cent == new_refund
                ):
                    return "skipped"
                await bump_unfrozen_periods(
                    db, [period_for_datetime(existing_bill.transaction_time)]
                )
                existing_bill.transaction_status = new_status
                existing_bill.refund_amount_cent = new_refund
                existing_bill.updated_at = datetime.now(timezone.utc)
                db.add(existing_bill)
                await db.flush()

                return "refund_processed"

            # Update existing bill fields if changed
            new_paid = item.get("paid_amount_cent", 0)
            new_total = item.get("total_amount_cent", 0)
            new_discount = item.get("discount_amount_cent", 0)
            new_refund = item.get("refund_amount_cent", 0)
            updated = (
                existing_bill.paid_amount_cent != new_paid
                or existing_bill.total_amount_cent != new_total
                or existing_bill.discount_amount_cent != new_discount
                or existing_bill.refund_amount_cent != new_refund
            )

            if updated:
                await bump_unfrozen_periods(
                    db, [period_for_datetime(existing_bill.transaction_time)]
                )
                existing_bill.paid_amount_cent = new_paid
                existing_bill.total_amount_cent = new_total
                existing_bill.discount_amount_cent = new_discount
                existing_bill.refund_amount_cent = new_refund
                existing_bill.updated_at = datetime.now(timezone.utc)
                db.add(existing_bill)
                await db.flush()
                return "updated"
            return "skipped"

        # Find customer by rutai_user_id
        cust_result = await db.execute(
            select(Customer).where(Customer.rutai_user_id == hrb_user_id)
        )
        customer = cust_result.scalars().first()

        # Do not create a bill that cannot be attributed to a customer and
        # distributor. The next scheduled sync can retry after bind-user sync
        # imports the corresponding customer.
        if customer is None:
            logger.warning(
                "Skip bill %s: no local customer for Rutai user %s",
                transaction_id,
                hrb_user_id,
            )
            return "skipped"

        # Parse transaction_time
        tx_time_str = item.get("transaction_time")
        tx_time = datetime.now(timezone.utc)
        if tx_time_str:
            try:
                # Try ISO format first
                tx_time = datetime.fromisoformat(tx_time_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                try:
                    tx_time = datetime.strptime(tx_time_str, "%Y-%m-%d %H:%M:%S")
                    tx_time = tx_time.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

        # Determine transaction status
        status_str = item.get("transaction_status", "paid")
        try:
            tx_status = TransactionStatus(status_str)
        except ValueError:
            tx_status = TransactionStatus.PAID

        bill = Bill(
            customer_id=customer.id,
            rutai_user_id=hrb_user_id,
            transaction_id=transaction_id,
            transaction_time=tx_time,
            consultation_fee_cent=item.get("consultation_fee_cent", 0),
            medicine_fee_cent=item.get("medicine_fee_cent", 0),
            total_amount_cent=item.get("total_amount_cent", 0),
            discount_amount_cent=item.get("discount_amount_cent", 0),
            paid_amount_cent=item.get("paid_amount_cent", 0),
            refund_amount_cent=item.get("refund_amount_cent", 0),
            transaction_status=tx_status,
        )
        await bump_unfrozen_periods(db, [period_for_datetime(tx_time)])
        db.add(bill)
        await db.flush()
        await db.refresh(bill)

        # Notify the distributor who owns the customer when a new bill is
        # imported.  The notification is tied to the same local bill view so
        # it can be opened directly from the message center.
        owner_result = await db.execute(
            select(Distributor.user_id).where(Distributor.id == customer.distributor_id)
        )
        owner_user_id = owner_result.scalar()
        if owner_user_id:
            status_label = "消费退款" if is_refund else "新增消费记录"
            db.add(Notification(
                user_id=owner_user_id,
                category=NotificationCategory.BILL,
                title=status_label,
                summary=f"客户{customer.name or '客户'}有一笔消费记录已同步",
                target="/pages/contribution-detail/index",
            ))

        if is_refund:
            return "refund_processed"

        return "created"

    # 退款处理：账单 transaction_status 已更新为 refunded/partially_refunded，
    # 消费金额口径（consumption_by_distributor）自动排除，无需冲正记录。

    # ------------------------------------------------------------------
    # Manual retry endpoints
    # ------------------------------------------------------------------
    async def retry_bind_users(self, db: AsyncSession) -> dict:
        """Manual trigger for getBindUser polling retry."""
        state = _get_state()
        if state["is_polling"]:
            raise Exception("Sync already in progress")
        result = await self.poll_bind_users(db)
        return {"status": "accepted", "message": "Bind user sync triggered", **result}

    async def retry_user_bill(self, db: AsyncSession, user_id: str) -> dict:
        """Manual retry bill fetch for a specific user."""
        # Check if user exists
        result = await db.execute(
            select(Customer).where(Customer.rutai_user_id == user_id)
        )
        customer = result.scalars().first()
        if customer is None:
            raise Exception("User not found")

        result_data = await self.fetch_user_bill(db, user_id)
        return {"status": "accepted", "user_id": user_id, **result_data}

    # ------------------------------------------------------------------
    # Daily reconciliation
    # ------------------------------------------------------------------
    async def daily_reconciliation(
        self,
        db: AsyncSession,
        bill_date: Optional[str] = None,
    ) -> dict:
        """Compare Rutai bill data with local records for a given date.

        Calls get_all_users_bill for the date and flags discrepancies.

        Args:
            db: Database session.
            bill_date: Date string YYYY-MM-DD. Defaults to yesterday.

        Returns:
            Dict with matched, missing_local, missing_remote counts.
        """
        from datetime import date, timedelta

        if bill_date is None:
            yesterday = date.today() - timedelta(days=1)
            bill_date = yesterday.strftime("%Y-%m-%d")

        matched = 0
        missing_local = 0
        cursor: Optional[str] = None

        while True:
            response = await self._client.get_all_users_bill(
                bill_date=bill_date,
                cursor=cursor,
                source="BJTR",
                db_session=db,
            )

            items = response.get("items", [])
            for item in items:
                transaction_id = item.get("transaction_id")
                if not transaction_id:
                    missing_local += 1
                    continue

                result = await db.execute(
                    select(Bill).where(Bill.transaction_id == transaction_id)
                )
                local_bill = result.scalars().first()
                if local_bill is None:
                    missing_local += 1
                else:
                    matched += 1

            has_more = response.get("has_more", False)
            cursor = response.get("next_cursor")
            if not has_more or not cursor:
                break

        return {
            "bill_date": bill_date,
            "matched": matched,
            "missing_local": missing_local,
        }

    # ------------------------------------------------------------------
    # Sync status
    # ------------------------------------------------------------------
    async def get_sync_status(self) -> dict:
        """Return current polling status, last success time, failure count."""
        state = _get_state()
        return {
            "last_success": state["last_success"].isoformat() if state["last_success"] else None,
            "failure_count": state["failure_count"],
            "pending_retries": state["pending_retries"],
            "is_polling": state["is_polling"],
            "circuit_breaker_open": state["circuit_breaker_open"],
            "last_bind_user_poll": (
                state["last_bind_user_poll"].isoformat()
                if state["last_bind_user_poll"]
                else None
            ),
            "last_bill_sync": (
                state["last_bill_sync"].isoformat()
                if state["last_bill_sync"]
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_sync_service: Optional[SyncService] = None


def get_sync_service() -> SyncService:
    """Return a module-level singleton SyncService."""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service
