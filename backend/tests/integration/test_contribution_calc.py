"""Integration tests for contribution calculation.

Tests the full contribution pipeline using a real test database:
- Personal contribution from bill data
- Up-tree aggregation L5→L4→L3→L2→L1
- Refund handling with contribution reversal
- Monthly settlement batch processing

TDD: These tests are written FIRST and are expected to FAIL until the
implementation is complete.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.contribution import (
    ContributionCategory,
    ContributionRecord,
    ContributionStatus,
    SettlementLog,
    SettlementStatus,
)
from src.models.hierarchy import HierarchyNode, NodeType, Promoter
from src.models.user import User, UserType, ActivationStatus
from tests.conftest import (
    seed_hierarchy_node,
    seed_promoter,
    seed_user,
)


# =========================================================================
# Contribution aggregation: personal → up-tree
# =========================================================================
class TestContributionAggregation:
    """Test contribution calculation and up-tree aggregation L5→L4→L3→L2→L1."""

    @pytest.mark.asyncio
    async def test_personal_contribution_from_bill(self, db_session):
        """Bill creation triggers personal contribution record with correct points."""
        from src.services.contribution_service import ContributionService

        # Setup hierarchy: L1 → L2 → L3 → L4 → L5(promoter)
        node_l1 = await seed_hierarchy_node(
            db_session, name="HQ", node_type="headquarters", level=1, parent_id=None
        )
        node_l2 = await seed_hierarchy_node(
            db_session, name="Region A", node_type="region", level=2, parent_id=node_l1
        )
        node_l3 = await seed_hierarchy_node(
            db_session, name="Branch 1", node_type="branch", level=3, parent_id=node_l2
        )
        node_l4 = await seed_hierarchy_node(
            db_session, name="Team Alpha", node_type="promoter", level=4, parent_id=node_l3
        )
        node_l5 = await seed_hierarchy_node(
            db_session, name="Promoter Zhang", node_type="promoter", level=5, parent_id=node_l4
        )

        # Create promoter at L5
        user_l5 = await seed_user(
            db_session, openid="wx_l5_promo", user_type="promoter", name="张三"
        )
        promoter_l5 = await seed_promoter(
            db_session, user_id=user_l5, node_id=node_l5
        )

        # Create customer bound to this promoter
        customer = Customer(
            promoter_id=promoter_l5,
            rutai_user_id="hrb_l5_001",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        # Create a bill
        bill = Bill(
            customer_id=customer.id,
            rutai_user_id="hrb_l5_001",
            transaction_id="txn_aggregate_001",
            transaction_time=datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc),
            paid_amount_cent=50000,  # 500 yuan
            total_amount_cent=50000,
            transaction_status=TransactionStatus.PAID,
        )
        db_session.add(bill)
        await db_session.flush()

        # Calculate contribution
        svc = ContributionService()
        record = await svc.create_from_bill(db_session, bill)

        assert record is not None
        assert record.promoter_id == promoter_l5
        assert record.points == "500.00"  # 500 yuan * 1.0 coefficient
        assert record.category == ContributionCategory.BILL
        assert record.status == ContributionStatus.PENDING
        assert record.source_id == "txn_aggregate_001"

    @pytest.mark.asyncio
    async def test_up_tree_aggregation_full_chain(self, db_session):
        """Contribution aggregates up through the entire L5→L1 chain."""
        from src.services.contribution_service import ContributionService

        # Build full hierarchy chain
        node_l1 = await seed_hierarchy_node(
            db_session, name="HQ", node_type="headquarters", level=1, parent_id=None
        )
        node_l2 = await seed_hierarchy_node(
            db_session, name="华北区", node_type="region", level=2, parent_id=node_l1
        )
        node_l3 = await seed_hierarchy_node(
            db_session, name="北京分部", node_type="branch", level=3, parent_id=node_l2
        )
        node_l4 = await seed_hierarchy_node(
            db_session, name="朝阳团队", node_type="promoter", level=4, parent_id=node_l3
        )
        node_l5 = await seed_hierarchy_node(
            db_session, name="促销员李四", node_type="promoter", level=5, parent_id=node_l4
        )

        # Create promoters at each level (L1-L5)
        user_l1 = await seed_user(db_session, openid="wx_l1", user_type="promoter", name="总部")
        user_l2 = await seed_user(db_session, openid="wx_l2", user_type="promoter", name="区域")
        user_l3 = await seed_user(db_session, openid="wx_l3", user_type="promoter", name="分部")
        user_l4 = await seed_user(db_session, openid="wx_l4", user_type="promoter", name="团队")
        user_l5 = await seed_user(db_session, openid="wx_l5", user_type="promoter", name="促销员")

        promoter_l1 = await seed_promoter(db_session, user_id=user_l1, node_id=node_l1)
        promoter_l2 = await seed_promoter(db_session, user_id=user_l2, node_id=node_l2)
        promoter_l3 = await seed_promoter(db_session, user_id=user_l3, node_id=node_l3)
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5 = await seed_promoter(db_session, user_id=user_l5, node_id=node_l5)

        # Create customer at L5
        customer = Customer(
            promoter_id=promoter_l5,
            rutai_user_id="hrb_chain_001",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        # Create bill then contribution
        bill = Bill(
            customer_id=customer.id,
            rutai_user_id="hrb_chain_001",
            transaction_id="txn_chain_001",
            transaction_time=datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc),
            paid_amount_cent=100000,  # 1000 yuan
            total_amount_cent=100000,
            transaction_status=TransactionStatus.PAID,
        )
        db_session.add(bill)
        await db_session.flush()

        svc = ContributionService()
        # Create personal contribution
        record = await svc.create_from_bill(db_session, bill)
        await db_session.flush()

        # Aggregate up-tree
        await svc.aggregate_up_tree(db_session, promoter_id=promoter_l5, month="2026-07")
        await db_session.flush()

        # Verify: personal contribution for L5 exists
        q_personal = select(ContributionRecord).where(
            ContributionRecord.promoter_id == promoter_l5,
            ContributionRecord.bill_id == bill.id,
        )
        result_personal = await db_session.execute(q_personal)
        personal_contribs = result_personal.scalars().all()
        assert len(personal_contribs) == 1
        assert personal_contribs[0].points == "1000.00"
        assert personal_contribs[0].category == ContributionCategory.BILL

        # Verify: team contribution records exist for L4, L3, L2, L1
        # These would be created by aggregate_up_tree
        for pid in [promoter_l4, promoter_l3, promoter_l2, promoter_l1]:
            q_team = select(ContributionRecord).where(
                ContributionRecord.promoter_id == pid,
                ContributionRecord.source_type == "team_aggregation",
                ContributionRecord.source_id == "month:2026-07:promoter:{}".format(promoter_l5),
            )
            result_team = await db_session.execute(q_team)
            team_contribs = result_team.scalars().all()
            assert len(team_contribs) >= 1, f"Expected team contribution for promoter {pid}"


# =========================================================================
# Refund handling
# =========================================================================
class TestRefundHandling:
    """Test contribution reversal on refund."""

    @pytest.mark.asyncio
    async def test_full_refund_reverses_contribution(self, db_session):
        """Full refund creates a reversed ContributionRecord and updates original."""
        from src.services.contribution_service import ContributionService

        # Setup
        node = await seed_hierarchy_node(
            db_session, name="Promoter Node", node_type="promoter", level=1, parent_id=None
        )
        user = await seed_user(db_session, openid="wx_refund_full", user_type="promoter")
        promoter = await seed_promoter(db_session, user_id=user, node_id=node)

        customer = Customer(
            promoter_id=promoter,
            rutai_user_id="hrb_rf_full",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        bill = Bill(
            customer_id=customer.id,
            rutai_user_id="hrb_rf_full",
            transaction_id="txn_rf_full_001",
            transaction_time=datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc),
            paid_amount_cent=80000,
            total_amount_cent=80000,
            transaction_status=TransactionStatus.PAID,
        )
        db_session.add(bill)
        await db_session.flush()

        svc = ContributionService()

        # Create initial contribution
        record = await svc.create_from_bill(db_session, bill)
        await db_session.flush()

        assert record.status == ContributionStatus.PENDING

        # Process full refund
        reversal = await svc.reverse_on_refund(
            db_session,
            original_contribution_id=record.id,
            refund_amount_cent=80000,
        )
        await db_session.flush()

        # Verify reversal record
        assert reversal is not None
        assert reversal.promoter_id == promoter
        assert reversal.bill_id == bill.id
        assert reversal.reversed_record_id == record.id
        assert reversal.status == ContributionStatus.REVERSED
        assert reversal.points == "-800.00"  # negated

        # Verify original is updated to confirmed status (already settled)
        # or remains for audit trail
        q = select(ContributionRecord).where(ContributionRecord.id == record.id)
        result = await db_session.execute(q)
        updated_original = result.scalars().first()
        assert updated_original is not None

    @pytest.mark.asyncio
    async def test_partial_refund_reverses_proportionally(self, db_session):
        """Partial refund creates proportional reversal contribution."""
        from src.services.contribution_service import ContributionService

        node = await seed_hierarchy_node(
            db_session, name="Node", node_type="promoter", level=1, parent_id=None
        )
        user = await seed_user(db_session, openid="wx_partial", user_type="promoter")
        promoter = await seed_promoter(db_session, user_id=user, node_id=node)

        customer = Customer(
            promoter_id=promoter,
            rutai_user_id="hrb_partial",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        bill = Bill(
            customer_id=customer.id,
            rutai_user_id="hrb_partial",
            transaction_id="txn_partial_001",
            transaction_time=datetime(2026, 7, 12, 11, 0, tzinfo=timezone.utc),
            paid_amount_cent=100000,  # 1000 yuan
            total_amount_cent=100000,
            transaction_status=TransactionStatus.PAID,
        )
        db_session.add(bill)
        await db_session.flush()

        svc = ContributionService()
        record = await svc.create_from_bill(db_session, bill)
        await db_session.flush()
        original_points = record.points  # "1000.00"

        # Partial refund: 300 yuan out of 1000 yuan
        reversal = await svc.reverse_on_refund(
            db_session,
            original_contribution_id=record.id,
            refund_amount_cent=30000,
        )
        await db_session.flush()

        assert reversal.points == "-300.00"
        assert reversal.reversed_record_id == record.id


# =========================================================================
# Monthly settlement
# =========================================================================
class TestMonthlySettlement:
    """Test monthly settlement batch processing."""

    @pytest.mark.asyncio
    async def test_batch_settle_pending_contributions(self, db_session):
        """Pending contributions are settled in batch for a given month."""
        from src.services.contribution_service import ContributionService

        # Setup
        node = await seed_hierarchy_node(
            db_session, name="Settle Node", node_type="promoter", level=1, parent_id=None
        )
        user = await seed_user(db_session, openid="wx_settle", user_type="promoter")
        promoter = await seed_promoter(db_session, user_id=user, node_id=node)

        customer = Customer(
            promoter_id=promoter,
            rutai_user_id="hrb_settle",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        svc = ContributionService()

        # Create multiple pending contributions
        for i in range(5):
            bill = Bill(
                customer_id=customer.id,
                rutai_user_id="hrb_settle",
                transaction_id=f"txn_settle_{i:03d}",
                transaction_time=datetime(2026, 7, i + 1, 10, 0, tzinfo=timezone.utc),
                paid_amount_cent=20000,
                total_amount_cent=20000,
                transaction_status=TransactionStatus.PAID,
            )
            db_session.add(bill)
            await db_session.flush()
            await svc.create_from_bill(db_session, bill)

        await db_session.flush()

        # Count pending before settlement
        q_pending = select(ContributionRecord).where(
            ContributionRecord.status == ContributionStatus.PENDING,
            ContributionRecord.promoter_id == promoter,
        )
        result_before = await db_session.execute(q_pending)
        pending_before = result_before.scalars().all()
        assert len(pending_before) == 5

        # Run settlement
        result = await svc.batch_settle(db_session, month="2026-07")
        await db_session.flush()

        assert result["settled_count"] == 5
        assert result["total_processed"] == 5

        # Verify all settled
        q_settled = select(ContributionRecord).where(
            ContributionRecord.status == ContributionStatus.SETTLED,
            ContributionRecord.promoter_id == promoter,
        )
        result_after = await db_session.execute(q_settled)
        settled = result_after.scalars().all()
        assert len(settled) == 5

        # Verify SettlementLog created
        q_log = select(SettlementLog).where(SettlementLog.period == "2026-07")
        result_log = await db_session.execute(q_log)
        logs = result_log.scalars().all()
        assert len(logs) == 1
        assert logs[0].status == SettlementStatus.COMPLETED
        assert logs[0].settled_records == 5

    @pytest.mark.asyncio
    async def test_settlement_skips_already_settled(self, db_session):
        """Batch settlement skips contributions that are already settled."""
        from src.services.contribution_service import ContributionService

        node = await seed_hierarchy_node(
            db_session, name="Skip Node", node_type="promoter", level=1, parent_id=None
        )
        user = await seed_user(db_session, openid="wx_skip", user_type="promoter")
        promoter = await seed_promoter(db_session, user_id=user, node_id=node)

        customer = Customer(
            promoter_id=promoter,
            rutai_user_id="hrb_skip",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        svc = ContributionService()

        # Create 3 pending + 1 already-settled contribution
        for i in range(3):
            bill = Bill(
                customer_id=customer.id,
                rutai_user_id="hrb_skip",
                transaction_id=f"txn_skip_{i:03d}",
                transaction_time=datetime(2026, 7, i + 1, 10, 0, tzinfo=timezone.utc),
                paid_amount_cent=10000,
                total_amount_cent=10000,
                transaction_status=TransactionStatus.PAID,
            )
            db_session.add(bill)
            await db_session.flush()
            await svc.create_from_bill(db_session, bill)

        # Manually set one as already settled
        from sqlalchemy import update
        q_all = select(ContributionRecord).where(
            ContributionRecord.promoter_id == promoter,
            ContributionRecord.status == ContributionStatus.PENDING,
        ).limit(1)
        result_all = await db_session.execute(q_all)
        first = result_all.scalars().first()
        if first:
            first.status = ContributionStatus.SETTLED
            first.settled_at = datetime.now(timezone.utc)
            await db_session.flush()

        # Run settlement
        result = await svc.batch_settle(db_session, month="2026-07")

        # Only settled 2 (the other was already settled)
        assert result["settled_count"] == 2

    @pytest.mark.asyncio
    async def test_settlement_idempotent(self, db_session):
        """Running settlement twice does not double-settle."""
        from src.services.contribution_service import ContributionService

        node = await seed_hierarchy_node(
            db_session, name="Idem Node", node_type="promoter", level=1, parent_id=None
        )
        user = await seed_user(db_session, openid="wx_idem", user_type="promoter")
        promoter = await seed_promoter(db_session, user_id=user, node_id=node)

        customer = Customer(
            promoter_id=promoter,
            rutai_user_id="hrb_idem",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        svc = ContributionService()

        bill = Bill(
            customer_id=customer.id,
            rutai_user_id="hrb_idem",
            transaction_id="txn_idem_001",
            transaction_time=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
            paid_amount_cent=50000,
            total_amount_cent=50000,
            transaction_status=TransactionStatus.PAID,
        )
        db_session.add(bill)
        await db_session.flush()
        await svc.create_from_bill(db_session, bill)
        await db_session.flush()

        # First settlement
        result1 = await svc.batch_settle(db_session, month="2026-07")
        assert result1["settled_count"] == 1

        # Second settlement: should skip
        result2 = await svc.batch_settle(db_session, month="2026-07")
        assert result2["settled_count"] == 0
