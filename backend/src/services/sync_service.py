"""Sync service: polling bind users, fetching bills, idempotent upsert, refund handling.

Coordinates with RutaiClient for API calls and ContributionService for
contribution calculation.
"""

import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..integrations.rutai_client import RutaiClient, get_rutai_client
from ..models.bill import Bill, TransactionStatus
from ..models.binding import BindingStatus, Customer
from ..models.distributor import Distributor
from ..models.organization import Organization
from ..models.notification import Notification, NotificationCategory
from ..services.contribution_service import ContributionService

settings = get_settings()


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
        self._contrib_svc = ContributionService()

    @property
    def _client(self) -> RutaiClient:
        if self._rutai_client is None:
            self._rutai_client = get_rutai_client()
        return self._rutai_client

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
            from ..models.user import AdminAccount, User, UserType

            # Find admin users
            admin_result = await db.execute(
                select(AdminAccount).where(AdminAccount.status == "active")
            )
            admins = admin_result.scalars().all()

            for admin in admins:
                # Find the User record linked to this admin (if any)
                # For now, create a system notification
                notification = Notification(
                    user_id=admin.id,  # admin account id as user_id
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

    async def _import_customer(self, db: AsyncSession, item: dict) -> bool:
        """Import a single bound user as a Customer if not already present.

        Returns True if a new customer was created.
        """
        hrb_user_id = item.get("hrb_user_id")
        if not hrb_user_id:
            return False

        # Check if already exists
        result = await db.execute(
            select(Customer).where(Customer.rutai_user_id == hrb_user_id)
        )
        existing = result.scalars().first()
        if existing is not None:
            return False

        # Find promoter by ref_token
        ref_token = item.get("ref_token")
        distributor_id = None
        if ref_token:
            from ..models.promotion import PromotionCode
            pc_result = await db.execute(
                select(PromotionCode).where(PromotionCode.ref_token == ref_token)
            )
            promotion_code = pc_result.scalars().first()
            if promotion_code is not None:
                distributor_id = promotion_code.distributor_id

        if distributor_id is None:
            # Find the first available promoter or a default one
            promoter_result = await db.execute(select(Distributor).limit(1))
            default_promoter = promoter_result.scalars().first()
            if default_promoter is not None:
                distributor_id = default_promoter.id
            else:
                return False

        customer = Customer(
            distributor_id=distributor_id,
            rutai_user_id=hrb_user_id,
            phone_masked=item.get("phone_masked"),
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db.add(customer)
        await db.flush()
        return True

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
                # Process refund
                existing_bill.transaction_status = (
                    TransactionStatus.REFUNDED
                    if transaction_status == "refunded"
                    else TransactionStatus.PARTIALLY_REFUNDED
                )
                existing_bill.refund_amount_cent = item.get("refund_amount_cent", 0)
                existing_bill.updated_at = datetime.now(timezone.utc)
                db.add(existing_bill)
                await db.flush()

                # Create reversal contribution
                await self._handle_refund(db, existing_bill, item)
                return "refund_processed"

            # Update existing bill fields if changed
            updated = False
            new_paid = item.get("paid_amount_cent", 0)
            new_total = item.get("total_amount_cent", 0)
            new_discount = item.get("discount_amount_cent", 0)
            new_refund = item.get("refund_amount_cent", 0)

            if existing_bill.paid_amount_cent != new_paid:
                existing_bill.paid_amount_cent = new_paid
                updated = True
            if existing_bill.total_amount_cent != new_total:
                existing_bill.total_amount_cent = new_total
                updated = True
            if existing_bill.discount_amount_cent != new_discount:
                existing_bill.discount_amount_cent = new_discount
                updated = True
            if existing_bill.refund_amount_cent != new_refund:
                existing_bill.refund_amount_cent = new_refund
                updated = True

            if updated:
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
            customer_id=customer.id if customer else 0,
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
        db.add(bill)
        await db.flush()
        await db.refresh(bill)

        # Trigger contribution calculation if this is a paid bill
        if not is_refund and tx_status == TransactionStatus.PAID:
            await self._contrib_svc.create_from_bill(db, bill)
            # Trigger up-tree aggregation
            if customer:
                await self._contrib_svc.aggregate_up_tree(
                    db,
                    distributor_id=customer.distributor_id,
                    month=tx_time.strftime("%Y-%m"),
                )

        if is_refund:
            # Record the refund but also create a reversal
            await self._handle_refund(db, bill, item)
            return "refund_processed"

        return "created"

    async def _handle_refund(
        self,
        db: AsyncSession,
        bill: Bill,
        item: dict,
    ) -> None:
        """Handle refund: find original contribution and create reversal."""
        from ..models.contribution import ContributionRecord

        # Find the original contribution for this bill
        result = await db.execute(
            select(ContributionRecord).where(
                ContributionRecord.bill_id == bill.id,
                ContributionRecord.category == "bill",
            ).order_by(ContributionRecord.id)
        )

        original = result.scalars().first()
        if original is not None:
            refund_amount = item.get("refund_amount_cent", bill.refund_amount_cent)
            if refund_amount > 0:
                await self._contrib_svc.reverse_on_refund(
                    db,
                    original_contribution_id=original.id,
                    refund_amount_cent=refund_amount,
                )

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
