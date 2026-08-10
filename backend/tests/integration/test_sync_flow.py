"""Integration tests for data sync flow.

Tests the end-to-end sync pipeline using a real test database:
- getBindUser polling: mock new users → auto-import → trigger getUserBill
- getUserBill sync: mock bills → idempotent insert → contribution calculation

TDD: These tests are written FIRST and are expected to FAIL until the
implementation is complete.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from src.models.bill import Bill, TransactionStatus
from src.models.binding import Customer
from src.models.distributor import Distributor
from src.models.organization import Organization
from src.models.hierarchy import NodeType
from src.models.user import User, UserType, ActivationStatus
from tests.conftest import (
    seed_hierarchy_node,
    seed_promotion_code,
    seed_promoter,
    seed_user,
)


# =========================================================================
# getBindUser polling
# =========================================================================
class TestBindUserPolling:
    """Test the getBindUser polling → auto-import → bill fetch trigger."""

    @pytest.mark.asyncio
    async def test_new_bindings_auto_import_customers(self, db_session):
        """When getBindUser returns new users, they are imported as Customers."""
        from src.services.sync_service import SyncService

        # Setup: create a promoter and hierarchy node
        node_id = await seed_hierarchy_node(
            db_session, name="L1", node_type="headquarters", level=1
        )
        user_id = await seed_user(
            db_session, openid="wx_promoter_001", user_type="promoter", name="推销员A"
        )
        distributor_id = await seed_promoter(
            db_session, user_id=user_id, node_id=node_id
        )
        await seed_promotion_code(
            db_session, distributor_id=distributor_id, ref_token="ref_token_abc"
        )

        svc = SyncService()

        # Mock the RutaiClient
        mock_client = MagicMock()
        mock_bindings = {
            "items": [
                {
                    "hrb_user_id": "hrb_001",
                    "phone_masked": "138****1234",
                    "marked_status": "bound",
                    "bind_method": "exact",
                    "ref_token": "ref_token_abc",
                    "marked_at": "2026-07-15T10:00:00Z",
                },
                {
                    "hrb_user_id": "hrb_002",
                    "phone_masked": "139****5678",
                    "marked_status": "bound",
                    "bind_method": "fuzzy",
                    "ref_token": "unknown_ref_token",
                    "marked_at": "2026-07-15T11:00:00Z",
                },
            ],
            "next_cursor": None,
            "has_more": False,
        }
        mock_client.get_bind_user = AsyncMock(return_value=mock_bindings)
        svc._rutai_client = mock_client

        result = await svc.poll_bind_users(db_session)

        assert result["processed"] == 2
        assert result["imported"] == 1

        # Verify customers were created
        q = select(Customer).where(Customer.rutai_user_id.in_(["hrb_001", "hrb_002"]))
        exec_result = await db_session.execute(q)
        customers = exec_result.scalars().all()
        assert len(customers) == 1

    @pytest.mark.asyncio
    async def test_bind_user_polling_pagination(self, db_session):
        """getBindUser with pagination processes all pages."""
        from src.services.sync_service import SyncService

        node_id = await seed_hierarchy_node(
            db_session, name="L1", node_type="headquarters", level=1
        )
        user_id = await seed_user(db_session, openid="wx_promo", user_type="promoter")
        await seed_promoter(db_session, user_id=user_id, node_id=node_id)

        svc = SyncService()

        mock_client = MagicMock()
        page1 = {
            "items": [
                {"hrb_user_id": "hrb_page1_001", "phone_masked": "1****", "marked_status": "bound",
                 "bind_method": "exact", "ref_token": "rt1", "marked_at": "2026-07-15T10:00:00Z"},
            ],
            "next_cursor": "cursor_page2",
            "has_more": True,
        }
        page2 = {
            "items": [
                {"hrb_user_id": "hrb_page2_001", "phone_masked": "2****", "marked_status": "bound",
                 "bind_method": "exact", "ref_token": "rt2", "marked_at": "2026-07-15T11:00:00Z"},
            ],
            "next_cursor": None,
            "has_more": False,
        }
        mock_client.get_bind_user = AsyncMock(side_effect=[page1, page2])
        svc._rutai_client = mock_client

        result = await svc.poll_bind_users(db_session)

        assert result["processed"] == 2
        assert result["pages"] == 2

    @pytest.mark.asyncio
    async def test_existing_customer_not_duplicated(self, db_session):
        """Already-imported customers are not duplicated."""
        from src.services.sync_service import SyncService

        node_id = await seed_hierarchy_node(
            db_session, name="L1", node_type="headquarters", level=1
        )
        user_id = await seed_user(db_session, openid="wx_promo2", user_type="promoter")
        distributor_id = await seed_promoter(db_session, user_id=user_id, node_id=node_id)
        await seed_promotion_code(
            db_session, distributor_id=distributor_id, ref_token="rt_new"
        )

        # Pre-create a customer
        from src.models.binding import BindingStatus, Customer
        customer = Customer(
            distributor_id=distributor_id,
            rutai_user_id="hrb_existing",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        svc = SyncService()

        mock_client = MagicMock()
        mock_bindings = {
            "items": [
                {"hrb_user_id": "hrb_existing", "phone_masked": "138****0000",
                 "marked_status": "bound", "bind_method": "exact", "ref_token": "rt_existing",
                 "marked_at": "2026-07-15T10:00:00Z"},
                {"hrb_user_id": "hrb_new_001", "phone_masked": "138****1111",
                 "marked_status": "bound", "bind_method": "exact", "ref_token": "rt_new",
                 "marked_at": "2026-07-15T11:00:00Z"},
            ],
            "next_cursor": None,
            "has_more": False,
        }
        mock_client.get_bind_user = AsyncMock(return_value=mock_bindings)
        svc._rutai_client = mock_client

        result = await svc.poll_bind_users(db_session)

        assert result["imported"] == 1  # Only the new one
        assert result["processed"] == 2  # Both processed

        # Verify only one extra customer
        q = select(Customer)
        exec_result = await db_session.execute(q)
        all_customers = exec_result.scalars().all()
        assert len(all_customers) == 2  # original + new


# =========================================================================
# getUserBill sync
# =========================================================================
class TestUserBillSync:
    """Test getUserBill sync → idempotent insert → contribution calculation."""

    @pytest.mark.asyncio
    async def test_bill_idempotent_insert_by_transaction_id(self, db_session):
        """Bills with the same transaction_id are not duplicated (idempotency)."""
        from src.services.sync_service import SyncService

        # Setup
        node_id = await seed_hierarchy_node(
            db_session, name="L1", node_type="headquarters", level=1
        )
        user_id = await seed_user(db_session, openid="wx_bill_test", user_type="promoter")
        distributor_id = await seed_promoter(db_session, user_id=user_id, node_id=node_id)

        from src.models.binding import BindingStatus, Customer
        customer = Customer(
            distributor_id=distributor_id,
            rutai_user_id="hrb_bill_001",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        svc = SyncService()

        mock_client = MagicMock()
        mock_bills = {
            "items": [
                {
                    "transaction_id": "txn_unique_001",
                    "transaction_time": "2026-07-15 10:30:00",
                    "consultation_fee_cent": 5000,
                    "medicine_fee_cent": 3000,
                    "total_amount_cent": 8000,
                    "discount_amount_cent": 0,
                    "paid_amount_cent": 8000,
                    "refund_amount_cent": 0,
                    "transaction_status": "paid",
                },
            ],
            "next_cursor": None,
            "has_more": False,
        }
        mock_client.get_user_bill = AsyncMock(return_value=mock_bills)
        svc._rutai_client = mock_client

        # First sync: creates the bill
        result1 = await svc.fetch_user_bill(db_session, "hrb_bill_001")
        assert result1["created"] == 1

        # Second sync with same data: should be idempotent
        result2 = await svc.fetch_user_bill(db_session, "hrb_bill_001")
        assert result2["created"] == 0
        assert result2["skipped"] == 1

        # Verify only one bill in DB
        q = select(Bill).where(Bill.transaction_id == "txn_unique_001")
        exec_result = await db_session.execute(q)
        bills = exec_result.scalars().all()
        assert len(bills) == 1

    @pytest.mark.asyncio
    async def test_bill_sync_creates_paid_bill(self, db_session):
        """Fetching bills creates a paid Bill that counts toward 消费金额."""
        from src.services.sync_service import SyncService

        # Setup promoter, customer, hierarchy
        node_id = await seed_hierarchy_node(
            db_session, name="L1", node_type="headquarters", level=1
        )
        user_id = await seed_user(db_session, openid="wx_contrib_test", user_type="promoter")
        distributor_id = await seed_promoter(db_session, user_id=user_id, node_id=node_id)

        from src.models.binding import BindingStatus, Customer
        customer = Customer(
            distributor_id=distributor_id,
            rutai_user_id="hrb_contrib_001",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        svc = SyncService()

        mock_client = MagicMock()
        mock_bills = {
            "items": [
                {
                    "transaction_id": "txn_contrib_001",
                    "transaction_time": "2026-07-15 10:30:00",
                    "consultation_fee_cent": 20000,
                    "medicine_fee_cent": 50000,
                    "total_amount_cent": 70000,
                    "discount_amount_cent": 0,
                    "paid_amount_cent": 70000,
                    "refund_amount_cent": 0,
                    "transaction_status": "paid",
                },
            ],
            "next_cursor": None,
            "has_more": False,
        }
        mock_client.get_user_bill = AsyncMock(return_value=mock_bills)
        svc._rutai_client = mock_client

        result = await svc.fetch_user_bill(db_session, "hrb_contrib_001")

        assert result["created"] == 1

        q = select(Bill).where(Bill.transaction_id == "txn_contrib_001")
        bill = (await db_session.execute(q)).scalars().first()
        assert bill is not None
        assert bill.paid_amount_cent == 70000
        assert bill.transaction_status == TransactionStatus.PAID

        # 消费金额（业绩贡献 = 消费金额）
        from src.services.consumption_service import consumption_by_distributor
        assert await consumption_by_distributor(db_session, [distributor_id], "2026-07") == {distributor_id: 70000}

    @pytest.mark.asyncio
    async def test_refund_bill_updates_status_and_excludes_consumption(self, db_session):
        """A refunded bill updates transaction_status and is excluded from 消费金额."""
        from src.services.sync_service import SyncService

        # Setup
        node_id = await seed_hierarchy_node(
            db_session, name="L1", node_type="headquarters", level=1
        )
        user_id = await seed_user(db_session, openid="wx_refund_test", user_type="promoter")
        distributor_id = await seed_promoter(db_session, user_id=user_id, node_id=node_id)

        from src.models.binding import BindingStatus, Customer
        customer = Customer(
            distributor_id=distributor_id,
            rutai_user_id="hrb_refund_001",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        svc = SyncService()

        mock_client = MagicMock()
        # First: create the bill (paid)
        initial_bills = {
            "items": [
                {
                    "transaction_id": "txn_refund_test_001",
                    "transaction_time": "2026-07-15 10:00:00",
                    "paid_amount_cent": 10000,
                    "total_amount_cent": 10000,
                    "consultation_fee_cent": 10000,
                    "medicine_fee_cent": 0,
                    "discount_amount_cent": 0,
                    "refund_amount_cent": 0,
                    "transaction_status": "paid",
                },
            ],
            "next_cursor": None,
            "has_more": False,
        }
        # Second: same bill now refunded
        refunded_bills = {
            "items": [
                {
                    "transaction_id": "txn_refund_test_001",
                    "transaction_time": "2026-07-15 10:00:00",
                    "paid_amount_cent": 10000,
                    "total_amount_cent": 10000,
                    "consultation_fee_cent": 10000,
                    "medicine_fee_cent": 0,
                    "discount_amount_cent": 0,
                    "refund_amount_cent": 10000,
                    "transaction_status": "refunded",
                },
            ],
            "next_cursor": None,
            "has_more": False,
        }
        mock_client.get_user_bill = AsyncMock(side_effect=[initial_bills, refunded_bills])
        svc._rutai_client = mock_client

        # First sync: creates bill
        await svc.fetch_user_bill(db_session, "hrb_refund_001")

        # Second sync: processes refund
        result = await svc.fetch_user_bill(db_session, "hrb_refund_001")

        assert result["refunds_processed"] >= 1 or result["updated"] >= 1

        # Verify bill is now marked as refunded
        q = select(Bill).where(Bill.transaction_id == "txn_refund_test_001")
        exec_result = await db_session.execute(q)
        bill = exec_result.scalars().first()
        assert bill.transaction_status == TransactionStatus.REFUNDED
        assert bill.refund_amount_cent == 10000

        # 退款账单不计入消费金额
        from src.services.consumption_service import consumption_by_distributor
        assert (await consumption_by_distributor(db_session, [distributor_id], "2026-07")).get(distributor_id, 0) == 0
