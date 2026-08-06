"""Integration tests for 消费业绩 view flow（业绩贡献=消费金额，分）.

Full flow: seed bills -> verify overview -> trend -> list/detail -> team drill.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token
from src.models.bill import Bill, TransactionStatus
from src.models.binding import BindingStatus, Customer
from tests.conftest import seed_hierarchy_node, seed_promoter, seed_user


def _auth_headers(user_id: int, user_type: str = "promoter") -> dict:
    token = create_access_token(data={"sub": str(user_id), "user_type": user_type})
    return {"Authorization": f"Bearer {token}"}


async def seed_bill(
    db: AsyncSession,
    customer_id: int,
    paid_cent: int,
    source_id: str,
    occurred_at: datetime | None = None,
) -> int:
    bill = Bill(
        customer_id=customer_id, transaction_id=source_id,
        transaction_time=occurred_at or datetime.now(timezone.utc),
        paid_amount_cent=paid_cent, total_amount_cent=paid_cent,
        transaction_status=TransactionStatus.PAID,
    )
    db.add(bill)
    await db.flush()
    await db.refresh(bill)
    return bill.id


async def seed_bound_customer(db: AsyncSession, distributor_id: int, rutai_user_id: str) -> int:
    customer = Customer(
        distributor_id=distributor_id, name="患者", phone="13800138000", phone_masked="138****8000",
        id_card_encrypted="x", id_card_masked="y", rutai_user_id=rutai_user_id,
        binding_status=BindingStatus.BOUND, version=1,
    )
    db.add(customer)
    await db.flush()
    await db.refresh(customer)
    return customer.id


class TestContributionViewFullFlow:
    @pytest.mark.asyncio
    async def test_full_flow_overview_trend_list_detail(self, client: AsyncClient, db_session: AsyncSession):
        node = await seed_hierarchy_node(db_session, name="FlowNode", node_type="promoter", level=1, parent_id=None)
        user_id = await seed_user(db_session, openid="wx_flow", user_type="promoter", name="流量测试")
        distributor_id = await seed_promoter(db_session, user_id=user_id, node_id=node)
        customer_id = await seed_bound_customer(db_session, distributor_id, "hrb_flow")

        await seed_bill(db_session, customer_id, 30000, "txn_flow_1", datetime(2026, 7, 5, tzinfo=timezone.utc))
        await seed_bill(db_session, customer_id, 15000, "txn_flow_2", datetime(2026, 7, 10, tzinfo=timezone.utc))
        await seed_bill(db_session, customer_id, 5000, "txn_flow_3", datetime(2026, 7, 15, tzinfo=timezone.utc))
        await seed_bill(db_session, customer_id, 20000, "txn_flow_jun", datetime(2026, 6, 20, tzinfo=timezone.utc))

        headers = _auth_headers(user_id)

        # Overview
        resp = await client.get("/api/v1/contributions/overview?month=2026-07", headers=headers)
        assert resp.status_code == 200
        overview = resp.json()["data"]
        assert overview["monthlyAmountCent"] == 50000  # 300+150+50
        assert overview["totalAmountCent"] == 70000
        assert "growthRate" in overview

        # Trend
        resp = await client.get("/api/v1/contributions/trend?period=6m", headers=headers)
        assert resp.status_code == 200
        trend = resp.json()["data"]
        assert "2026-06" in trend["categories"]
        assert "2026-07" in trend["categories"]
        assert len(trend["values"]) == 6

        # List
        resp = await client.get("/api/v1/contributions?month=2026-07", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 3

        # Detail of one bill
        first_id = items[0]["id"]
        resp = await client.get(f"/api/v1/contributions/{first_id}", headers=headers)
        assert resp.status_code == 200
        detail = resp.json()["data"]
        assert "amountCent" in detail
        assert detail["id"] == first_id

    @pytest.mark.asyncio
    async def test_team_view_shows_consumption_amounts(self, client: AsyncClient, db_session: AsyncSession):
        node_l2 = await seed_hierarchy_node(db_session, name="Lead L2", node_type="promoter", level=2, parent_id=None)
        node_l3 = await seed_hierarchy_node(db_session, name="Member L3", node_type="promoter", level=3, parent_id=node_l2)
        user_l2 = await seed_user(db_session, openid="wx_tm_l2", user_type="promoter", name="上级")
        user_l3 = await seed_user(db_session, openid="wx_tm_l3", user_type="promoter", name="下级")
        promoter_l2 = await seed_promoter(db_session, user_id=user_l2, node_id=node_l2)
        promoter_l3 = await seed_promoter(db_session, user_id=user_l3, node_id=node_l3)
        customer_id = await seed_bound_customer(db_session, promoter_l3, "hrb_tm")
        await seed_bill(db_session, customer_id, 50000, "txn_tm_1", datetime(2026, 7, 15, tzinfo=timezone.utc))

        resp = await client.get("/api/v1/team/contributions?month=2026-07", headers=_auth_headers(user_l2))
        assert resp.status_code == 200
        team_data = resp.json()["data"]
        assert team_data["teamMonthlyAmountCent"] == 50000
        assert team_data["directMemberCount"] == 1
        assert team_data["members"][0]["monthlyAmountCent"] == 50000

    @pytest.mark.asyncio
    async def test_full_team_drill_down_flow(self, client: AsyncClient, db_session: AsyncSession):
        node_l3 = await seed_hierarchy_node(db_session, name="Branch L3", node_type="promoter", level=3, parent_id=None)
        node_l4 = await seed_hierarchy_node(db_session, name="Team L4", node_type="promoter", level=4, parent_id=node_l3)
        node_l5 = await seed_hierarchy_node(db_session, name="Distributor L5", node_type="promoter", level=5, parent_id=node_l4)

        user_l3 = await seed_user(db_session, openid="wx_dd_l3", user_type="promoter", name="分部经理")
        user_l4 = await seed_user(db_session, openid="wx_dd_l4", user_type="promoter", name="团队长")
        user_l5 = await seed_user(db_session, openid="wx_dd_l5", user_type="promoter", name="推广员")
        promoter_l3 = await seed_promoter(db_session, user_id=user_l3, node_id=node_l3)
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5 = await seed_promoter(db_session, user_id=user_l5, node_id=node_l5)

        customer_id = await seed_bound_customer(db_session, promoter_l5, "hrb_dd")
        await seed_bill(db_session, customer_id, 40000, "txn_dd_1", datetime(2026, 7, 10, tzinfo=timezone.utc))

        headers_l3 = _auth_headers(user_l3)
        resp = await client.get("/api/v1/team/contributions?month=2026-07", headers=headers_l3)
        assert resp.status_code == 200
        assert resp.json()["data"]["directMemberCount"] >= 1

        resp = await client.get(f"/api/v1/team/contributions/{promoter_l4}?month=2026-07", headers=headers_l3)
        assert resp.status_code == 200
        assert resp.json()["data"]["directMemberCount"] >= 1

        resp = await client.get(f"/api/v1/team/contributions/{promoter_l5}?month=2026-07", headers=headers_l3)
        assert resp.status_code == 200
        assert resp.json()["data"]["directMemberCount"] == 0

        headers_l5 = _auth_headers(user_l5)
        resp = await client.get(f"/api/v1/team/contributions/{promoter_l4}?month=2026-07", headers=headers_l5)
        assert resp.status_code == 403
