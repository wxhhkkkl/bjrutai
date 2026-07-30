"""Unit tests for sharing service calculation logic.

Tests the business logic in isolation without database dependencies.
"""

from unittest.mock import MagicMock

import pytest

from src.models.sharing import RuleType


class TestFixedRatioCalculation:
    """Tests for fixed_ratio rule type calculations."""

    @pytest.mark.asyncio
    async def test_ratio_70_percent_on_10000_cents(self):
        """70% ratio on 10000 cents (100.00 yuan) = 7000 cents."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.FIXED_RATIO
        rule.value = "0.70"

        result = await apply_rule(rule, 10000)
        assert result == 7000

    @pytest.mark.asyncio
    async def test_ratio_100_percent_on_5000_cents(self):
        """100% ratio on 5000 cents = 5000 cents."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.FIXED_RATIO
        rule.value = "1.0"

        result = await apply_rule(rule, 5000)
        assert result == 5000

    @pytest.mark.asyncio
    async def test_ratio_0_percent_on_10000_cents(self):
        """0% ratio on 10000 cents = 0 cents."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.FIXED_RATIO
        rule.value = "0.0"

        result = await apply_rule(rule, 10000)
        assert result == 0

    @pytest.mark.asyncio
    async def test_ratio_50_percent_on_9999_cents(self):
        """50% ratio on 9999 cents = floor(4999.5) = 4999 cents."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.FIXED_RATIO
        rule.value = "0.50"

        result = await apply_rule(rule, 9999)
        assert result == 4999  # int truncates toward zero


class TestFixedAmountCalculation:
    """Tests for fixed_amount rule type calculations."""

    @pytest.mark.asyncio
    async def test_fixed_amount_5000_cents(self):
        """Fixed amount rule returns the configured amount regardless of base."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.FIXED_AMOUNT
        rule.value = "5000"

        result = await apply_rule(rule, 10000)
        assert result == 5000

    @pytest.mark.asyncio
    async def test_fixed_amount_100_cents(self):
        """Fixed amount of 100 cents (1 yuan)."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.FIXED_AMOUNT
        rule.value = "100"

        result = await apply_rule(rule, 99999)
        assert result == 100


class TestTieredCalculation:
    """Tests for tiered rule type calculations."""

    @pytest.mark.asyncio
    async def test_tiered_base_amount_below_lowest_threshold(self):
        """Amount below all thresholds returns 0."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.TIERED
        rule.value = '[{"threshold": 10000, "ratio": 0.10}, {"threshold": 50000, "ratio": 0.15}]'

        result = await apply_rule(rule, 5000)
        assert result == 0

    @pytest.mark.asyncio
    async def test_tiered_base_amount_exceeds_first_threshold(self):
        """Amount over first threshold: 15000 * 0.10 = 1500."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.TIERED
        rule.value = '[{"threshold": 10000, "ratio": 0.10}, {"threshold": 50000, "ratio": 0.15}]'

        result = await apply_rule(rule, 15000)
        assert result == 1500

    @pytest.mark.asyncio
    async def test_tiered_base_amount_exceeds_highest_threshold(self):
        """Amount over highest threshold: 60000 * 0.15 = 9000."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.TIERED
        rule.value = '[{"threshold": 10000, "ratio": 0.10}, {"threshold": 50000, "ratio": 0.15}]'

        result = await apply_rule(rule, 60000)
        assert result == 9000

    @pytest.mark.asyncio
    async def test_tiered_single_tier(self):
        """Single tier: 20000 * 0.10 = 2000."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.TIERED
        rule.value = '[{"threshold": 10000, "ratio": 0.10}]'

        result = await apply_rule(rule, 20000)
        assert result == 2000

    @pytest.mark.asyncio
    async def test_tiered_exactly_at_threshold(self):
        """Amount exactly at threshold: 10000 > 10000? No, 10000 is not > 10000, falls to next."""
        from src.services.sharing_service import apply_rule

        rule = MagicMock()
        rule.rule_type = RuleType.TIERED
        rule.value = '[{"threshold": 5000, "ratio": 0.05}, {"threshold": 10000, "ratio": 0.10}]'

        result = await apply_rule(rule, 10000)
        # 10000 > 10000? False. 10000 > 5000? True -> 10000 * 0.05 = 500
        # Actually sorted descending: threshold 10000 ratio 0.10, then 5000 ratio 0.05
        # 10000 > 10000 is false. 10000 > 5000 is true -> 500
        assert result == 500
