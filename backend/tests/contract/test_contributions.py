"""Contract tests for 消费业绩 view endpoints (业绩贡献=消费金额).

Tests ensure consumption query and team endpoints conform to the unified
response format and behave correctly. Amounts are integer cents.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from tests.conftest import (
    assert_response_envelope,
    seed_hierarchy_node,
    seed_promoter,
    seed_user,
)


def _auth_headers(user_id: int = 1, user_type: str = "promoter") -> dict:
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_id), 'user_type': user_type})}"}


async def setup_promoter_with_hierarchy(
    db: AsyncSession,
    *,
    openid: str = "wx_test",
    name: str = "测试推广员",
    node_name: str = "TestNode",
    level: int = 5,
    parent_id: int | None = None,
) -> tuple[int, int, int]:
    node_id = await seed_hierarchy_node(db, name=node_name, node_type="promoter", level=level, parent_id=parent_id)
    user_id = await seed_user(db, openid=openid, user_type="promoter", name=name)
    distributor_id = await seed_promoter(db, user_id=user_id, node_id=node_id)
    return user_id, node_id, distributor_id


async def seed_customer_bill(
    db: AsyncSession,
    *,
    distributor_id: int,
    paid_cent: int,
    txn_id: str,
    occurred_at: datetime | None = None,
    status: str = "paid",
) -> int:
    """Create a bound customer + bill; return bill id."""
    customer = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000", phone_masked="138****8000",
        id_card_encrypted="x", id_card_masked="y", rutai_user_id=f"hrb_{txn_id}",
        binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(customer)
    await db.flush()
    bill = Bill(
        customer_id=customer.id, transaction_id=txn_id,
        transaction_time=occurred_at or datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc),
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent,
        transaction_status=TransactionStatus(status),
    )
    db.add(bill)
    await db.flush()
    return bill.id


# ============================================================================
# GET /api/v1/contributions/overview
# ============================================================================
class TestContributionOverview:
    async def test_overview_returns_envelope(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, distributor_id = await setup_promoter_with_hierarchy(db_session)
        await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=25000, txn_id="txn_ov")

        resp = await client.get("/api/v1/contributions/overview?month=2026-07", headers=_auth_headers(user_id))
        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "monthlyAmountCent" in data
        assert "totalAmountCent" in data
        assert "growthRate" in data

    async def test_overview_returns_correct_monthly_amount(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, distributor_id = await setup_promoter_with_hierarchy(db_session)
        for i in range(3):
            await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=10000,
                                     txn_id=f"txn_mp_{i}", occurred_at=datetime(2026, 7, i + 1, tzinfo=timezone.utc))

        resp = await client.get("/api/v1/contributions/overview?month=2026-07", headers=_auth_headers(user_id))
        data = resp.json()["data"]
        assert data["monthlyAmountCent"] == 30000
        assert data["totalAmountCent"] == 30000

    async def test_overview_returns_zero_for_empty_month(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, _distributor_id = await setup_promoter_with_hierarchy(db_session)
        resp = await client.get("/api/v1/contributions/overview?month=2026-08", headers=_auth_headers(user_id))
        data = resp.json()["data"]
        assert data["monthlyAmountCent"] == 0

    async def test_overview_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        resp = await client.get("/api/v1/contributions/overview?month=2026-07")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/contributions/trend
# ============================================================================
class TestContributionTrend:
    async def test_trend_returns_envelope(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, distributor_id = await setup_promoter_with_hierarchy(db_session)
        await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=20000,
                                 txn_id="txn_trend_1", occurred_at=datetime(2026, 5, 10, tzinfo=timezone.utc))

        resp = await client.get("/api/v1/contributions/trend?period=6m", headers=_auth_headers(user_id))
        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        data = body["data"]
        assert "categories" in data
        assert "values" in data
        assert len(data["categories"]) == len(data["values"]) == 6

    async def test_trend_returns_correct_monthly_data(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, distributor_id = await setup_promoter_with_hierarchy(db_session)
        await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=15000,
                                 txn_id="txn_trend_mar", occurred_at=datetime(2026, 3, 10, tzinfo=timezone.utc))
        await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=30000,
                                 txn_id="txn_trend_jun", occurred_at=datetime(2026, 6, 20, tzinfo=timezone.utc))

        resp = await client.get("/api/v1/contributions/trend?period=6m", headers=_auth_headers(user_id))
        data = resp.json()["data"]
        assert len(data["categories"]) == 6
        values = dict(zip(data["categories"], data["values"]))
        assert values.get("2026-03") == 15000
        assert values.get("2026-06") == 30000

    async def test_trend_defaults_to_6_months(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, _distributor_id = await setup_promoter_with_hierarchy(db_session)
        resp = await client.get("/api/v1/contributions/trend", headers=_auth_headers(user_id))
        assert len(resp.json()["data"]["categories"]) == 6

    async def test_trend_supports_custom_period(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, _distributor_id = await setup_promoter_with_hierarchy(db_session)
        resp = await client.get("/api/v1/contributions/trend?period=12m", headers=_auth_headers(user_id))
        assert len(resp.json()["data"]["categories"]) == 12

    async def test_trend_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        resp = await client.get("/api/v1/contributions/trend?period=6m")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/contributions (list)
# ============================================================================
class TestContributionList:
    async def test_list_returns_envelope(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, distributor_id = await setup_promoter_with_hierarchy(db_session)
        await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=10000, txn_id="txn_list_1")

        resp = await client.get("/api/v1/contributions?month=2026-07", headers=_auth_headers(user_id))
        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        data = body["data"]
        assert "items" in data
        assert "nextCursor" in data
        assert "hasMore" in data
        assert isinstance(data["items"], list)
        assert data["items"][0]["amountCent"] == 10000

    async def test_list_filter_by_status(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, distributor_id = await setup_promoter_with_hierarchy(db_session)
        await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=10000,
                                 txn_id="txn_ls_1", status="paid")
        await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=5000,
                                 txn_id="txn_ls_2", status="refunded")

        resp = await client.get("/api/v1/contributions?month=2026-07&status=refunded", headers=_auth_headers(user_id))
        data = resp.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "refunded"

    async def test_list_cursor_pagination(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, distributor_id = await setup_promoter_with_hierarchy(db_session)
        for i in range(25):
            await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=i * 1000,
                                     txn_id=f"txn_pag_{i}")

        resp = await client.get("/api/v1/contributions?month=2026-07&pageSize=10", headers=_auth_headers(user_id))
        data = resp.json()["data"]
        assert len(data["items"]) == 10
        assert data["hasMore"] is True
        assert data["nextCursor"] is not None

    async def test_list_empty(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, _distributor_id = await setup_promoter_with_hierarchy(db_session)
        resp = await client.get("/api/v1/contributions?month=2026-07", headers=_auth_headers(user_id))
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["hasMore"] is False

    async def test_list_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        resp = await client.get("/api/v1/contributions?month=2026-07")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/contributions/{id}
# ============================================================================
class TestContributionDetail:
    async def test_detail_returns_envelope(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, distributor_id = await setup_promoter_with_hierarchy(db_session)
        bill_id = await seed_customer_bill(db_session, distributor_id=distributor_id, paid_cent=50000, txn_id="txn_detail_001")

        resp = await client.get(f"/api/v1/contributions/{bill_id}", headers=_auth_headers(user_id))
        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        data = body["data"]
        assert data["id"] == bill_id
        assert data["amountCent"] == 50000

    async def test_detail_not_found(self, client: AsyncClient, db_session: AsyncSession):
        user_id, _node_id, _distributor_id = await setup_promoter_with_hierarchy(db_session)
        resp = await client.get("/api/v1/contributions/99999", headers=_auth_headers(user_id))
        assert resp.status_code == 404

    async def test_detail_is_scoped_to_current_distributor(self, client: AsyncClient, db_session: AsyncSession):
        owner_id, _node_id, owner_distributor_id = await setup_promoter_with_hierarchy(
            db_session, openid="wx_bill_owner", name="账单所属人"
        )
        other_id, _node_id, _other_distributor_id = await setup_promoter_with_hierarchy(
            db_session, openid="wx_bill_other", name="其他推广员"
        )
        bill_id = await seed_customer_bill(
            db_session, distributor_id=owner_distributor_id, paid_cent=50000, txn_id="txn_scope_001"
        )

        resp = await client.get(f"/api/v1/contributions/{bill_id}", headers=_auth_headers(other_id))
        assert resp.status_code == 404

    async def test_detail_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        resp = await client.get("/api/v1/contributions/1")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/team/contributions
# ============================================================================
class TestTeamContributions:
    async def test_team_summary_returns_envelope(self, client: AsyncClient, db_session: AsyncSession):
        node_l4 = await seed_hierarchy_node(db_session, name="Team Lead", node_type="promoter", level=4, parent_id=None)
        node_l5 = await seed_hierarchy_node(db_session, name="Team Member", node_type="promoter", level=5, parent_id=node_l4)
        user_l4 = await seed_user(db_session, openid="wx_team_l4", user_type="promoter", name="队长")
        user_l5 = await seed_user(db_session, openid="wx_team_l5", user_type="promoter", name="队员")
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5 = await seed_promoter(db_session, user_id=user_l5, node_id=node_l5)

        await seed_customer_bill(db_session, distributor_id=promoter_l5, paid_cent=20000, txn_id="txn_team_1")

        resp = await client.get("/api/v1/team/contributions?month=2026-07", headers=_auth_headers(user_l4))
        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        data = body["data"]
        assert "teamMonthlyAmountCent" in data
        assert "directMemberCount" in data
        assert "members" in data

    async def test_team_summary_aggregates_members(self, client: AsyncClient, db_session: AsyncSession):
        node_l4 = await seed_hierarchy_node(db_session, name="Lead2", node_type="promoter", level=4, parent_id=None)
        node_l5a = await seed_hierarchy_node(db_session, name="Member A", node_type="promoter", level=5, parent_id=node_l4)
        node_l5b = await seed_hierarchy_node(db_session, name="Member B", node_type="promoter", level=5, parent_id=node_l4)
        user_l4 = await seed_user(db_session, openid="wx_agg_l4", user_type="promoter", name="队长")
        user_l5a = await seed_user(db_session, openid="wx_agg_a", user_type="promoter", name="队员A")
        user_l5b = await seed_user(db_session, openid="wx_agg_b", user_type="promoter", name="队员B")
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5a = await seed_promoter(db_session, user_id=user_l5a, node_id=node_l5a)
        promoter_l5b = await seed_promoter(db_session, user_id=user_l5b, node_id=node_l5b)

        await seed_customer_bill(db_session, distributor_id=promoter_l5a, paid_cent=15000, txn_id="txn_agg_a")
        await seed_customer_bill(db_session, distributor_id=promoter_l5b, paid_cent=25000, txn_id="txn_agg_b")

        resp = await client.get("/api/v1/team/contributions?month=2026-07", headers=_auth_headers(user_l4))
        data = resp.json()["data"]
        assert data["teamMonthlyAmountCent"] == 40000
        assert data["directMemberCount"] == 2

    async def test_team_summary_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        resp = await client.get("/api/v1/team/contributions?month=2026-07")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/team/contributions/{promoterId}
# ============================================================================
class TestTeamDrillDown:
    async def test_drill_down_returns_member_team_view(self, client: AsyncClient, db_session: AsyncSession):
        node_l4 = await seed_hierarchy_node(db_session, name="DrillLead", node_type="promoter", level=4, parent_id=None)
        node_l5 = await seed_hierarchy_node(db_session, name="DrillMember", node_type="promoter", level=5, parent_id=node_l4)
        node_l6 = await seed_hierarchy_node(db_session, name="Grandchild", node_type="promoter", level=6, parent_id=node_l5)
        user_l4 = await seed_user(db_session, openid="wx_drill_l4", user_type="promoter", name="队长")
        user_l5 = await seed_user(db_session, openid="wx_drill_l5", user_type="promoter", name="队员")
        user_l6 = await seed_user(db_session, openid="wx_drill_l6", user_type="promoter", name="孙子")
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5 = await seed_promoter(db_session, user_id=user_l5, node_id=node_l5)
        promoter_l6 = await seed_promoter(db_session, user_id=user_l6, node_id=node_l6)

        await seed_customer_bill(db_session, distributor_id=promoter_l6, paid_cent=10000, txn_id="txn_drill")

        resp = await client.get(f"/api/v1/team/contributions/{promoter_l5}?month=2026-07", headers=_auth_headers(user_l4))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "teamMonthlyAmountCent" in data
        assert "members" in data

    async def test_drill_down_unauthorized_branch_returns_403(self, client: AsyncClient, db_session: AsyncSession):
        node_a = await seed_hierarchy_node(db_session, name="BranchA", node_type="promoter", level=4, parent_id=None)
        node_b = await seed_hierarchy_node(db_session, name="BranchB", node_type="promoter", level=4, parent_id=None)
        node_a_child = await seed_hierarchy_node(db_session, name="ChildA", node_type="promoter", level=5, parent_id=node_a)
        node_b_child = await seed_hierarchy_node(db_session, name="ChildB", node_type="promoter", level=5, parent_id=node_b)
        user_a = await seed_user(db_session, openid="wx_branch_a", user_type="promoter", name="分支A")
        user_b = await seed_user(db_session, openid="wx_branch_b", user_type="promoter", name="分支B")
        user_a_child = await seed_user(db_session, openid="wx_branch_ac", user_type="promoter", name="子A")
        user_b_child = await seed_user(db_session, openid="wx_branch_bc", user_type="promoter", name="子B")
        promoter_a = await seed_promoter(db_session, user_id=user_a, node_id=node_a)
        promoter_b = await seed_promoter(db_session, user_id=user_b, node_id=node_b)
        await seed_promoter(db_session, user_id=user_a_child, node_id=node_a_child)
        promoter_b_child = await seed_promoter(db_session, user_id=user_b_child, node_id=node_b_child)

        resp = await client.get(f"/api/v1/team/contributions/{promoter_b_child}?month=2026-07", headers=_auth_headers(user_a))
        assert resp.status_code == 403

    async def test_drill_down_requires_auth(self, client: AsyncClient, db_session: AsyncSession):
        resp = await client.get("/api/v1/team/contributions/1?month=2026-07")
        assert resp.status_code == 401
