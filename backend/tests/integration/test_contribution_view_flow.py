"""Integration tests for contribution view flow (US6).

Full flow: calculate contributions -> verify overview -> verify trend ->
drill team -> verify no monetary amounts in team views.

Uses real SQLite test database via conftest.py fixtures.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from src.models.contribution import (
    ContributionCategory,
    ContributionRecord,
    ContributionStatus,
)
from src.models.hierarchy import HierarchyNode, NodeType
from tests.conftest import (
    seed_hierarchy_node,
    seed_promoter,
    seed_user,
)


def _auth_headers(user_id: int, user_type: str = "promoter") -> dict:
    token = create_access_token(data={"sub": str(user_id), "user_type": user_type})
    return {"Authorization": f"Bearer {token}"}


async def seed_contribution(
    db: AsyncSession,
    promoter_id: int,
    customer_id: int,
    points: str,
    status: str = "settled",
    category: str = "bill",
    source_id: str = "txn_test",
    occurred_at: datetime | None = None,
) -> int:
    record = ContributionRecord(
        promoter_id=promoter_id,
        customer_id=customer_id,
        points=points,
        status=ContributionStatus(status),
        category=ContributionCategory(category),
        title=f"贡献 - {source_id}",
        source_type="bill",
        source_id=source_id,
        rule_version="1.0",
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record.id


# ============================================================================
# Full Flow: calculate -> overview -> trend -> team -> no amounts
# ============================================================================
class TestContributionViewFullFlow:
    """End-to-end contribution view flow verifying all US6 endpoints work together."""

    @pytest.mark.asyncio
    async def test_full_flow_overview_trend_composition(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calculate contributions, then verify overview / trend / composition."""
        # ---- Setup hierarchy ----
        node = await seed_hierarchy_node(
            db_session, name="FlowNode", node_type="promoter", level=1, parent_id=None
        )
        user_id = await seed_user(db_session, openid="wx_flow", user_type="promoter", name="流量测试")
        promoter_id = await seed_promoter(db_session, user_id=user_id, node_id=node)

        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_flow",
            binding_status=BindingStatus.BOUND,
            bound_at=datetime.now(timezone.utc),
        )
        db_session.add(customer)
        await db_session.flush()

        # ---- Seed contributions across categories ----
        await seed_contribution(
            db_session, promoter_id, customer.id, "300.00",
            category="bill", source_id="txn_flow_1",
            occurred_at=datetime(2026, 7, 5, tzinfo=timezone.utc),
        )
        await seed_contribution(
            db_session, promoter_id, customer.id, "150.00",
            category="binding", source_id="txn_flow_2",
            occurred_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        )
        await seed_contribution(
            db_session, promoter_id, customer.id, "50.00",
            category="followup", source_id="txn_flow_3",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        # Also seed in June for trend verification
        await seed_contribution(
            db_session, promoter_id, customer.id, "200.00",
            category="bill", source_id="txn_flow_jun",
            occurred_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        )

        await db_session.flush()
        headers = _auth_headers(user_id)

        # ---- Step 1: Overview ----
        resp = await client.get("/api/v1/contributions/overview?month=2026-07", headers=headers)
        assert resp.status_code == 200
        overview = resp.json()["data"]
        assert overview["monthlyPoints"] == "500.00"  # 300 + 150 + 50
        assert overview["totalPoints"] == "700.00"    # 300+150+50+200
        assert "growthRate" in overview
        assert isinstance(overview["statusCounts"], dict)

        # ---- Step 2: Trend ----
        resp = await client.get("/api/v1/contributions/trend?period=6m", headers=headers)
        assert resp.status_code == 200
        trend = resp.json()["data"]
        assert "2026-06" in trend["categories"]
        assert "2026-07" in trend["categories"]
        assert len(trend["values"]) == 6

        # ---- Step 3: Composition ----
        resp = await client.get("/api/v1/contributions/composition?month=2026-07", headers=headers)
        assert resp.status_code == 200
        comp = resp.json()["data"]
        categories = {c["label"]: c for c in comp["categories"]}
        assert "消费贡献" in categories or "bill" in str(categories)
        # Percentages should exist
        for cat in comp["categories"]:
            assert isinstance(cat["percent"], (int, float))

        # ---- Step 4: Detail list ----
        resp = await client.get("/api/v1/contributions?month=2026-07", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 3

        # ---- Step 5: Detail of one record ----
        first_id = items[0]["id"]
        resp = await client.get(f"/api/v1/contributions/{first_id}", headers=headers)
        assert resp.status_code == 200
        detail = resp.json()["data"]
        assert "calculationBase" in detail
        assert "coefficient" in detail
        assert "calculationDescription" in detail

    @pytest.mark.asyncio
    async def test_team_view_no_monetary_amounts(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Team contribution views do not expose any monetary amounts."""
        # Build L2 -> L3 hierarchy
        node_l2 = await seed_hierarchy_node(
            db_session, name="Lead L2", node_type="promoter", level=2, parent_id=None
        )
        node_l3 = await seed_hierarchy_node(
            db_session, name="Member L3", node_type="promoter", level=3, parent_id=node_l2
        )
        user_l2 = await seed_user(db_session, openid="wx_tm_l2", user_type="promoter", name="上级")
        user_l3 = await seed_user(db_session, openid="wx_tm_l3", user_type="promoter", name="下级")
        promoter_l2 = await seed_promoter(db_session, user_id=user_l2, node_id=node_l2)
        promoter_l3 = await seed_promoter(db_session, user_id=user_l3, node_id=node_l3)

        customer = Customer(
            promoter_id=promoter_l3,
            rutai_user_id="hrb_tm",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution(
            db_session, promoter_l3, customer.id, "500.00",
            source_id="txn_tm_1",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        headers = _auth_headers(user_l2)

        # Team summary
        resp = await client.get("/api/v1/team/contributions?month=2026-07", headers=headers)
        assert resp.status_code == 200
        team_data = resp.json()["data"]

        # Verify: no monetary amounts anywhere in the response
        def check_no_monetary(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    assert "amount" not in k.lower(), f"amount field at {path}.{k}"
                    assert "money" not in k.lower(), f"money field at {path}.{k}"
                    assert "revenue" not in k.lower(), f"revenue field at {path}.{k}"
                    assert "discount" not in k.lower(), f"discount field at {path}.{k}"
                    check_no_monetary(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    check_no_monetary(v, f"{path}[{i}]")

        check_no_monetary(team_data)

        # Verify the expected fields exist
        assert "teamMonthlyPoints" in team_data
        assert "directMemberCount" in team_data
        assert "members" in team_data

    @pytest.mark.asyncio
    async def test_full_team_drill_down_flow(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Full team view flow: summary -> drill down -> verify branch access."""
        # L3 -> L4 -> L5 hierarchy
        node_l3 = await seed_hierarchy_node(
            db_session, name="Branch L3", node_type="promoter", level=3, parent_id=None
        )
        node_l4 = await seed_hierarchy_node(
            db_session, name="Team L4", node_type="promoter", level=4, parent_id=node_l3
        )
        node_l5 = await seed_hierarchy_node(
            db_session, name="Promoter L5", node_type="promoter", level=5, parent_id=node_l4
        )

        user_l3 = await seed_user(db_session, openid="wx_dd_l3", user_type="promoter", name="分部经理")
        user_l4 = await seed_user(db_session, openid="wx_dd_l4", user_type="promoter", name="团队长")
        user_l5 = await seed_user(db_session, openid="wx_dd_l5", user_type="promoter", name="推广员")
        promoter_l3 = await seed_promoter(db_session, user_id=user_l3, node_id=node_l3)
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5 = await seed_promoter(db_session, user_id=user_l5, node_id=node_l5)

        customer = Customer(
            promoter_id=promoter_l5,
            rutai_user_id="hrb_dd",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution(
            db_session, promoter_l5, customer.id, "400.00",
            source_id="txn_dd_1",
            occurred_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        )

        await db_session.flush()

        # ---- L3 (branch manager) views own team ----
        headers_l3 = _auth_headers(user_l3)
        resp = await client.get("/api/v1/team/contributions?month=2026-07", headers=headers_l3)
        assert resp.status_code == 200
        summary_l3 = resp.json()["data"]
        # L3 has 1 direct child (L4), and L4's subtree includes L5
        assert summary_l3["directMemberCount"] >= 1

        # ---- L3 drills down to L4 ----
        resp = await client.get(
            f"/api/v1/team/contributions/{promoter_l4}?month=2026-07",
            headers=headers_l3,
        )
        assert resp.status_code == 200
        dd_l4 = resp.json()["data"]
        # L4's team should include L5
        assert dd_l4["directMemberCount"] >= 1

        # ---- L3 drills down to L5 ----
        resp = await client.get(
            f"/api/v1/team/contributions/{promoter_l5}?month=2026-07",
            headers=headers_l3,
        )
        assert resp.status_code == 200
        dd_l5 = resp.json()["data"]
        # L5 has no direct children (leaf node)
        assert dd_l5["directMemberCount"] == 0

        # ---- L5 (leaf promoter) tries to drill into L4 (not in subtree) ----
        headers_l5 = _auth_headers(user_l5)
        resp = await client.get(
            f"/api/v1/team/contributions/{promoter_l4}?month=2026-07",
            headers=headers_l5,
        )
        # L5 is below L4 in hierarchy, so L4 is an ancestor, not descendant
        # L5 should NOT be able to see L4's team view
        assert resp.status_code == 403
