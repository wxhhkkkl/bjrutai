"""Unit tests for ContributionService.

Tests calculation formula, tree-walk aggregation algorithm, and edge cases.
No database dependency – pure logic tests with mocks.

TDD: These tests are written FIRST and are expected to FAIL until the
implementation is complete.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------
def make_mock_bill(
    bill_id: int = 1,
    transaction_id: str = "txn_001",
    paid_amount_cent: int = 10000,  # 100.00 yuan
    transaction_status: str = "paid",
    customer_id: int = 1,
    rutai_user_id: str = "hrb_user_001",
):
    bill = MagicMock()
    bill.id = bill_id
    bill.transaction_id = transaction_id
    bill.paid_amount_cent = paid_amount_cent
    bill.total_amount_cent = paid_amount_cent
    bill.transaction_status = transaction_status
    bill.customer_id = customer_id
    bill.rutai_user_id = rutai_user_id
    bill.transaction_time = datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)
    bill.created_at = datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)
    return bill


def make_mock_promoter(promoter_id: int, user_id: int, node_id: int):
    p = MagicMock()
    p.id = promoter_id
    p.user_id = user_id
    p.node_id = node_id
    return p


def make_mock_node(node_id: int, parent_id: int | None, level: int, name: str = "Node"):
    n = MagicMock()
    n.id = node_id
    n.parent_id = parent_id
    n.level = level
    n.name = name
    return n


# =========================================================================
# Calculation formula tests
# =========================================================================
class TestCalculationFormula:
    """Unit tests for contribution calculation formula."""

    def test_zero_amount_returns_zero_points(self):
        """Bill with zero paid amount yields zero contribution points."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        # paid_amount_cent=0, coefficient="1.0" => points="0.00"
        points = svc._calc_points(0, "1.0")
        assert points == "0.00"

    def test_normal_amount_calculation(self):
        """100 yuan (10000 fen) at coefficient 1.0 = 100.00 points."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        points = svc._calc_points(10000, "1.0")
        assert points == "100.00"

    def test_huge_amount_calculation(self):
        """Very large amounts are calculated correctly."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        points = svc._calc_points(999999999, "1.0")
        # 999999999 / 100 * 1.0 = 9999999.99
        assert points == "9999999.99"

    def test_fractional_points_rounding(self):
        """Fractional results round to 2 decimal places."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        # 1 fen (0.01 yuan) * 1.0 = 0.01 points
        points = svc._calc_points(1, "1.0")
        assert points == "0.01"

        # 3 fen (0.03 yuan) * 0.3333 coefficient = 0.009999 → rounds to 0.01
        points = svc._calc_points(3, "0.3333")
        assert points == "0.01"

    def test_custom_coefficient(self):
        """Non-default coefficient changes point calculation."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        # 100 yuan * 2.0 = 200.00 points
        points = svc._calc_points(10000, "2.0")
        assert points == "200.00"

        # 50 yuan * 0.5 = 25.00 points
        points = svc._calc_points(5000, "0.5")
        assert points == "25.00"

    def test_coefficient_with_many_decimals(self):
        """Coefficient with many decimals is handled correctly."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        points = svc._calc_points(10000, "1.2345")
        assert points == "123.45"

    def test_negative_amount_not_allowed(self):
        """Negative paid amounts should not occur for bill contributions."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        # Even with negative (should not happen in bills), it calculates
        points = svc._calc_points(-5000, "1.0")
        assert points == "-50.00"


# =========================================================================
# Contribution creation from bill
# =========================================================================
class TestContributionCreation:
    """Tests for creating ContributionRecords from bills."""

    @pytest.mark.asyncio
    async def test_create_from_bill(self):
        """Bill creates a ContributionRecord with correct values."""
        from src.services.contribution_service import ContributionService
        from src.models.contribution import ContributionCategory, ContributionStatus

        svc = ContributionService()
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.execute = AsyncMock()

        bill = make_mock_bill(bill_id=1, paid_amount_cent=10000)

        # Mock: find customer → returns customer with distributor_id
        mock_customer = MagicMock()
        mock_customer.distributor_id = 5
        mock_customer.rutai_user_id = "hrb_user_001"

        # Mock: get coefficient → returns "1.0"
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None  # no existing record

        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            # First call: check existing contribution (returns None)
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
            # Second call: find customer
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_customer)))),
            # Third call: get coefficient
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
        ]

        record = await svc.create_from_bill(mock_db, bill)

        assert record is not None
        assert record.distributor_id == 5
        assert record.bill_id == 1
        assert record.points == "100.00"
        assert record.category == ContributionCategory.BILL
        assert record.status == ContributionStatus.PENDING
        assert record.title is not None
        assert record.source_id == bill.transaction_id


# =========================================================================
# Tree-walk aggregation algorithm
# =========================================================================
class TestTreeWalkAggregation:
    """Unit tests for up-tree contribution aggregation."""

    @pytest.mark.asyncio
    async def test_walks_entire_ancestor_chain(self):
        """Aggregation walks from L5 up to L1, adding to each ancestor."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        mock_db = AsyncMock()

        # Build ancestor chain: L5 → L4 → L3 → L2 → L1
        ancestor_chain = [
            {"distributor_id": 5, "node_id": 5, "level": 5},
            {"distributor_id": 4, "node_id": 4, "level": 4},
            {"distributor_id": 3, "node_id": 3, "level": 3},
            {"distributor_id": 2, "node_id": 2, "level": 2},
            {"distributor_id": 1, "node_id": 1, "level": 1},
        ]

        with patch.object(
            svc, "_get_ancestor_chain",
            new_callable=AsyncMock,
            return_value=ancestor_chain,
        ), patch.object(
            svc, "_upsert_team_contribution",
            new_callable=AsyncMock,
        ) as mock_upsert:
            await svc.aggregate_up_tree(mock_db, distributor_id=5, month="2026-07")

            assert mock_upsert.call_count == 4  # L4, L3, L2, L1 (not self)

    @pytest.mark.asyncio
    async def test_root_node_stops_aggregation(self):
        """L1 node (no parent) results in zero ancestor upserts."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        mock_db = AsyncMock()

        # L1 node has no ancestors
        ancestor_chain = [{"distributor_id": 1, "node_id": 1, "level": 1}]

        with patch.object(
            svc, "_get_ancestor_chain",
            new_callable=AsyncMock,
            return_value=ancestor_chain,
        ), patch.object(
            svc, "_upsert_team_contribution",
            new_callable=AsyncMock,
        ) as mock_upsert:
            await svc.aggregate_up_tree(mock_db, distributor_id=1, month="2026-07")

            # Only one entry in chain (self) → zero ancestor upserts
            assert mock_upsert.call_count == 0

    @pytest.mark.asyncio
    async def test_no_promoter_for_ancestor_skips(self):
        """Ancestor node without promoter is skipped gracefully."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        mock_db = AsyncMock()

        # Ancestor chain with a node that has no distributor_id
        ancestor_chain = [
            {"distributor_id": 2, "node_id": 2, "level": 2},
            {"distributor_id": None, "node_id": 1, "level": 1},  # no distributor
        ]

        with patch.object(
            svc, "_get_ancestor_chain",
            new_callable=AsyncMock,
            return_value=ancestor_chain,
        ), patch.object(
            svc, "_upsert_team_contribution",
            new_callable=AsyncMock,
        ) as mock_upsert:
            await svc.aggregate_up_tree(mock_db, distributor_id=2, month="2026-07")

            # The only ancestor has distributor_id=None → skipped. Self is excluded.
            # Total upserts = 0 (None is skipped, self is not aggregated)
            assert mock_upsert.call_count == 0


# =========================================================================
# Refund reversal tests
# =========================================================================
class TestRefundReversal:
    """Unit tests for refund reversal logic."""

    @pytest.mark.asyncio
    async def test_reverse_creates_negated_record(self):
        """Refund creates a reversed ContributionRecord with negated points."""
        from src.services.contribution_service import ContributionService
        from src.models.contribution import ContributionStatus

        svc = ContributionService()
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        original = MagicMock()
        original.id = 100
        original.points = "50.00"
        original.distributor_id = 5
        original.customer_id = 1
        original.bill_id = 1
        original.category = "bill"
        original.title = "消费贡献 - txn_001"
        original.status = "confirmed"
        original.source_type = "bill"
        original.source_id = "txn_001"
        original.occurred_at = datetime(2026, 7, 15, tzinfo=timezone.utc)

        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            # First call: find original contribution
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=original)))),
            # Second call: get coefficient (returns None → defaults to "1.0")
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
        ]

        record = await svc.reverse_on_refund(
            mock_db,
            original_contribution_id=100,
            refund_amount_cent=5000,  # 50 yuan refund → -50.00 points
        )

        assert record is not None
        assert record.distributor_id == 5
        assert record.bill_id == 1
        assert record.category == "bill"
        assert record.status == ContributionStatus.REVERSED
        # Refund of 50 yuan → -50.00 points (at coefficient 1.0)
        assert record.points == "-50.00"
        assert record.reversed_record_id == 100

    @pytest.mark.asyncio
    async def test_partial_refund_reversal(self):
        """Partial refund creates proportional reversal."""
        from src.services.contribution_service import ContributionService

        svc = ContributionService()
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        original = MagicMock()
        original.id = 100
        original.points = "100.00"
        original.distributor_id = 5
        original.customer_id = 1
        original.bill_id = 1
        original.category = "bill"
        original.title = "消费贡献"
        original.status = "confirmed"
        original.source_type = "bill"
        original.source_id = "txn_001"
        original.occurred_at = datetime(2026, 7, 15, tzinfo=timezone.utc)

        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            # First call: find original contribution
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=original)))),
            # Second call: get coefficient (returns None → defaults to "1.0")
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
        ]

        record = await svc.reverse_on_refund(
            mock_db,
            original_contribution_id=100,
            refund_amount_cent=3000,  # 30 yuan refund = 30% of original 100 yuan
        )

        # 30 yuan * 1.0 coefficient = -30.00 points
        assert record.points == "-30.00"
