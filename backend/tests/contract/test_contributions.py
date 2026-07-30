"""Contract tests for contribution view endpoints (US6).

Tests ensure contribution query and team endpoints conform to the unified
response format {code, message, data, requestId, serverTime} and behave
correctly under all documented scenarios.

TDD: These tests are written FIRST and are expected to FAIL until the
implementation is complete.
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
from src.models.hierarchy import HierarchyNode, NodeType, Promoter
from src.models.user import User, UserType, ActivationStatus
from tests.conftest import (
    assert_response_envelope,
    seed_admin,
    seed_hierarchy_node,
    seed_promoter,
    seed_user,
)


def _user_token(user_id: int = 1, user_type: str = "promoter") -> str:
    return create_access_token(data={"sub": str(user_id), "user_type": user_type})


def _admin_token(user_id: int = 99) -> str:
    return create_access_token(data={"sub": str(user_id), "user_type": "admin"})


def _auth_headers(user_id: int = 1, user_type: str = "promoter") -> dict:
    return {"Authorization": f"Bearer {_user_token(user_id, user_type)}"}


def _admin_headers(user_id: int = 99) -> dict:
    return {"Authorization": f"Bearer {_admin_token(user_id)}"}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------
async def seed_contribution_record(
    db: AsyncSession,
    *,
    promoter_id: int,
    customer_id: int,
    bill_id: int | None = None,
    points: str = "100.00",
    status: str = "pending",
    category: str = "bill",
    title: str = "测试贡献",
    source_type: str = "bill",
    source_id: str = "txn_test_001",
    rule_version: str = "1.0",
    occurred_at: datetime | None = None,
    adjustment_reason: str | None = None,
) -> int:
    """Insert a ContributionRecord row and return its id."""
    record = ContributionRecord(
        promoter_id=promoter_id,
        customer_id=customer_id,
        bill_id=bill_id,
        points=points,
        status=ContributionStatus(status),
        category=ContributionCategory(category),
        title=title,
        source_type=source_type,
        source_id=source_id,
        rule_version=rule_version,
        occurred_at=occurred_at or datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc),
        adjustment_reason=adjustment_reason,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record.id


async def setup_promoter_with_hierarchy(
    db: AsyncSession,
    *,
    openid: str = "wx_test",
    name: str = "测试推广员",
    node_name: str = "TestNode",
    level: int = 5,
    parent_id: int | None = None,
) -> tuple[int, int, int]:
    """Create user + node + promoter and return (user_id, node_id, promoter_id)."""
    node_id = await seed_hierarchy_node(
        db, name=node_name, node_type="promoter", level=level, parent_id=parent_id
    )
    user_id = await seed_user(db, openid=openid, user_type="promoter", name=name)
    promoter_id = await seed_promoter(db, user_id=user_id, node_id=node_id)
    return user_id, node_id, promoter_id


# ============================================================================
# GET /api/v1/contributions/overview
# ============================================================================
class TestContributionOverview:
    """GET /api/v1/contributions/overview?month=YYYY-MM"""

    async def test_overview_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Overview returns properly enveloped response."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_overview",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        # Seed a contribution for July 2026
        await seed_contribution_record(
            db_session,
            promoter_id=promoter_id,
            customer_id=customer.id,
            points="250.00",
            status="settled",
            category="bill",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions/overview?month=2026-07",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "monthlyPoints" in data
        assert "totalPoints" in data
        assert "growthRate" in data
        assert "statusCounts" in data

    async def test_overview_returns_correct_monthly_points(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Overview monthlyPoints matches sum of contributions for the month."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_mp",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        # Seed multiple contributions
        for i in range(3):
            await seed_contribution_record(
                db_session,
                promoter_id=promoter_id,
                customer_id=customer.id,
                points="100.00",
                status="settled",
                category="bill",
                source_id=f"txn_mp_{i}",
                occurred_at=datetime(2026, 7, i + 1, tzinfo=timezone.utc),
            )

        resp = await client.get(
            "/api/v1/contributions/overview?month=2026-07",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        # 3 x 100.00 = 300.00 (settled contributions are counted)
        assert data["monthlyPoints"] == "300.00"

    async def test_overview_returns_zero_for_empty_month(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Overview returns zero for a month with no contributions."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)

        resp = await client.get(
            "/api/v1/contributions/overview?month=2026-08",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["monthlyPoints"] == "0.00"

    async def test_overview_status_counts(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Overview breaks down counts by contribution status."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_sc",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="100.00", status="settled", source_id="txn_sc_1",
            occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="50.00", status="pending", source_id="txn_sc_2",
            occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions/overview?month=2026-07",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        counts = data["statusCounts"]
        assert counts["settled"] == 1
        assert counts["pending"] == 1

    async def test_overview_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/contributions/overview?month=2026-07")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/contributions/trend
# ============================================================================
class TestContributionTrend:
    """GET /api/v1/contributions/trend?period=6m"""

    async def test_trend_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Trend returns properly enveloped response with categories and values."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_trend",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="200.00", status="settled", source_id="txn_trend_1",
            occurred_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions/trend?period=6m",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "categories" in data
        assert "values" in data
        assert isinstance(data["categories"], list)
        assert isinstance(data["values"], list)
        assert len(data["categories"]) == len(data["values"])

    async def test_trend_returns_correct_monthly_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Trend returns monthly points for the last 6 months."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_trend2",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        # Seed contributions in March and June 2026
        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="150.00", status="settled", source_id="txn_trend_mar",
            occurred_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        )
        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="300.00", status="settled", source_id="txn_trend_jun",
            occurred_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions/trend?period=6m",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        # Should have 6 categories (months from Feb 2026 to Jul 2026)
        assert len(data["categories"]) == 6
        # March and June should have values
        assert "2026-03" in data["categories"]
        assert "2026-06" in data["categories"]

    async def test_trend_defaults_to_6_months(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Trend defaults to 6 months if period is not specified."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)

        resp = await client.get(
            "/api/v1/contributions/trend",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["categories"]) == 6

    async def test_trend_supports_custom_period(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Trend supports 3m and 12m periods."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)

        resp = await client.get(
            "/api/v1/contributions/trend?period=12m",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["categories"]) == 12

    async def test_trend_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/contributions/trend?period=6m")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/contributions/composition
# ============================================================================
class TestContributionComposition:
    """GET /api/v1/contributions/composition?month=YYYY-MM"""

    async def test_composition_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Composition returns properly enveloped response with categories."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_comp",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="300.00", status="settled", category="bill",
            source_id="txn_comp_1",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions/composition?month=2026-07",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "categories" in data
        assert isinstance(data["categories"], list)
        for cat in data["categories"]:
            assert "label" in cat
            assert "points" in cat
            assert "percent" in cat

    async def test_composition_percentages_sum_to_100(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Composition category percentages sum to 100."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_comp2",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="200.00", status="settled", category="bill",
            source_id="txn_comp_bill",
            occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="50.00", status="settled", category="binding",
            source_id="txn_comp_bind",
            occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="50.00", status="settled", category="followup",
            source_id="txn_comp_fu",
            occurred_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions/composition?month=2026-07",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        total_percent = sum(cat["percent"] for cat in data["categories"])
        assert abs(total_percent - 100) < 1

    async def test_composition_empty_month(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Composition returns empty categories for month with no data."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)

        resp = await client.get(
            "/api/v1/contributions/composition?month=2026-07",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["categories"]) == 0

    async def test_composition_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/contributions/composition?month=2026-07")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/contributions (list)
# ============================================================================
class TestContributionList:
    """GET /api/v1/contributions?month=&status=&category=&cursor=&pageSize="""

    async def test_list_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """List returns properly enveloped response with cursor pagination."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_list",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="100.00", source_id="txn_list_1",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions?month=2026-07",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "items" in data
        assert "nextCursor" in data
        assert "hasMore" in data
        assert isinstance(data["items"], list)

    async def test_list_filter_by_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """List filters by contribution status."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_list_s",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="100.00", status="settled", source_id="txn_list_s1",
            occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="50.00", status="pending", source_id="txn_list_s2",
            occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions?month=2026-07&status=pending",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "pending"

    async def test_list_filter_by_category(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """List filters by contribution category."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_list_c",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="100.00", category="bill", source_id="txn_list_c1",
            occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            points="50.00", category="binding", source_id="txn_list_c2",
            occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/contributions?month=2026-07&category=bill",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["category"] == "bill"

    async def test_list_cursor_pagination(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """List supports cursor-based pagination with nextCursor."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_list_pag",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        for i in range(25):
            await seed_contribution_record(
                db_session, promoter_id=promoter_id, customer_id=customer.id,
                points=f"{i * 10}.00", source_id=f"txn_pag_{i}",
                occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )

        resp = await client.get(
            "/api/v1/contributions?month=2026-07&pageSize=10",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 10
        assert data["hasMore"] is True
        assert data["nextCursor"] is not None

    async def test_list_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """List returns empty items for a month with no contributions."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)

        resp = await client.get(
            "/api/v1/contributions?month=2026-07",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == []
        assert data["hasMore"] is False

    async def test_list_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/contributions?month=2026-07")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/contributions/{id}
# ============================================================================
class TestContributionDetail:
    """GET /api/v1/contributions/{id}"""

    async def test_detail_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Detail returns properly enveloped response with full info."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_detail",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        bill = Bill(
            customer_id=customer.id,
            rutai_user_id="hrb_detail",
            transaction_id="txn_detail_001",
            transaction_time=datetime(2026, 7, 15, tzinfo=timezone.utc),
            paid_amount_cent=50000,
            total_amount_cent=50000,
            transaction_status=TransactionStatus.PAID,
        )
        db_session.add(bill)
        await db_session.flush()

        record_id = await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            bill_id=bill.id, points="500.00", rule_version="1.0",
            source_id="txn_detail_001",
            adjustment_reason="初始计算",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(
            f"/api/v1/contributions/{record_id}",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "id" in data
        assert "points" in data
        assert "calculationBase" in data
        assert "coefficient" in data
        assert "calculationDescription" in data
        assert "adjustmentReason" in data

    async def test_detail_includes_calculation_info(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Detail response includes calculation base, coefficient, and description."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)
        customer = Customer(
            promoter_id=promoter_id,
            rutai_user_id="hrb_detail2",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        bill = Bill(
            customer_id=customer.id,
            rutai_user_id="hrb_detail2",
            transaction_id="txn_detail_002",
            transaction_time=datetime(2026, 7, 15, tzinfo=timezone.utc),
            paid_amount_cent=80000,
            total_amount_cent=80000,
            transaction_status=TransactionStatus.PAID,
        )
        db_session.add(bill)
        await db_session.flush()

        record_id = await seed_contribution_record(
            db_session, promoter_id=promoter_id, customer_id=customer.id,
            bill_id=bill.id, points="800.00", rule_version="1.0",
            source_id="txn_detail_002",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(
            f"/api/v1/contributions/{record_id}",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["calculationBase"] == "800.00"
        assert data["coefficient"] == "1.0"
        assert "800.00" in data["calculationDescription"]
        assert "1.0" in data["calculationDescription"]

    async def test_detail_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Non-existent contribution returns 404."""
        user_id, node_id, promoter_id = await setup_promoter_with_hierarchy(db_session)

        resp = await client.get(
            "/api/v1/contributions/99999",
            headers=_auth_headers(user_id),
        )

        assert resp.status_code == 404

    async def test_detail_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/contributions/1")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/team/contributions
# ============================================================================
class TestTeamContributions:
    """GET /api/v1/team/contributions?month=YYYY-MM"""

    async def test_team_summary_returns_envelope(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Team summary returns properly enveloped response."""
        # Build L4 → L5 hierarchy: L4 is parent, L5 is child
        node_l4 = await seed_hierarchy_node(
            db_session, name="Team Lead", node_type="promoter", level=4, parent_id=None
        )
        node_l5 = await seed_hierarchy_node(
            db_session, name="Team Member", node_type="promoter", level=5, parent_id=node_l4
        )

        user_l4 = await seed_user(db_session, openid="wx_team_l4", user_type="promoter", name="队长")
        user_l5 = await seed_user(db_session, openid="wx_team_l5", user_type="promoter", name="队员")
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5 = await seed_promoter(db_session, user_id=user_l5, node_id=node_l5)

        customer = Customer(
            promoter_id=promoter_l5,
            rutai_user_id="hrb_team",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_l5, customer_id=customer.id,
            points="200.00", status="settled", source_id="txn_team_1",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/team/contributions?month=2026-07",
            headers=_auth_headers(user_l4),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        assert body["code"] == 0
        data = body["data"]
        assert "teamMonthlyPoints" in data
        assert "directMemberCount" in data
        assert "members" in data
        assert isinstance(data["members"], list)

    async def test_team_summary_no_monetary_amounts(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Team summary does NOT expose monetary amounts, only contribution points."""
        node_l4 = await seed_hierarchy_node(
            db_session, name="Lead", node_type="promoter", level=4, parent_id=None
        )
        node_l5 = await seed_hierarchy_node(
            db_session, name="Member", node_type="promoter", level=5, parent_id=node_l4
        )
        user_l4 = await seed_user(db_session, openid="wx_noamount", user_type="promoter", name="队长")
        user_l5 = await seed_user(db_session, openid="wx_noamount_m", user_type="promoter", name="队员")
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5 = await seed_promoter(db_session, user_id=user_l5, node_id=node_l5)

        customer = Customer(
            promoter_id=promoter_l5,
            rutai_user_id="hrb_noamount",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_l5, customer_id=customer.id,
            points="300.00", status="settled", source_id="txn_noamount",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/team/contributions?month=2026-07",
            headers=_auth_headers(user_l4),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        # Check no monetary fields present
        response_str = str(data).lower()
        forbidden_fields = ["amount", "money", "yuan", "cent", "rmb", "revenue", "discount"]
        for field in forbidden_fields:
            assert field not in response_str, f"Team response should not contain '{field}'"

    async def test_team_summary_aggregates_members(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Team monthlyPoints is the sum of all direct members' points."""
        node_l4 = await seed_hierarchy_node(
            db_session, name="Lead2", node_type="promoter", level=4, parent_id=None
        )
        node_l5a = await seed_hierarchy_node(
            db_session, name="Member A", node_type="promoter", level=5, parent_id=node_l4
        )
        node_l5b = await seed_hierarchy_node(
            db_session, name="Member B", node_type="promoter", level=5, parent_id=node_l4
        )
        user_l4 = await seed_user(db_session, openid="wx_agg_l4", user_type="promoter", name="队长")
        user_l5a = await seed_user(db_session, openid="wx_agg_a", user_type="promoter", name="队员A")
        user_l5b = await seed_user(db_session, openid="wx_agg_b", user_type="promoter", name="队员B")
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5a = await seed_promoter(db_session, user_id=user_l5a, node_id=node_l5a)
        promoter_l5b = await seed_promoter(db_session, user_id=user_l5b, node_id=node_l5b)

        cust_a = Customer(promoter_id=promoter_l5a, rutai_user_id="hrb_agg_a", binding_status=BindingStatus.BOUND)
        cust_b = Customer(promoter_id=promoter_l5b, rutai_user_id="hrb_agg_b", binding_status=BindingStatus.BOUND)
        db_session.add_all([cust_a, cust_b])
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_l5a, customer_id=cust_a.id,
            points="150.00", status="settled", source_id="txn_agg_a",
            occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        await seed_contribution_record(
            db_session, promoter_id=promoter_l5b, customer_id=cust_b.id,
            points="250.00", status="settled", source_id="txn_agg_b",
            occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        resp = await client.get(
            "/api/v1/team/contributions?month=2026-07",
            headers=_auth_headers(user_l4),
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["teamMonthlyPoints"] == "400.00"
        assert data["directMemberCount"] == 2

    async def test_team_summary_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/team/contributions?month=2026-07")
        assert resp.status_code == 401


# ============================================================================
# GET /api/v1/team/contributions/{promoterId}
# ============================================================================
class TestTeamDrillDown:
    """GET /api/v1/team/contributions/{promoterId}?month=YYYY-MM"""

    async def test_drill_down_returns_member_team_view(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Drill-down returns team view for a specific member in the branch."""
        # L4 (requester) → L5 (target) → L6 (grandchild)
        node_l4 = await seed_hierarchy_node(
            db_session, name="DrillLead", node_type="promoter", level=4, parent_id=None
        )
        node_l5 = await seed_hierarchy_node(
            db_session, name="DrillMember", node_type="promoter", level=5, parent_id=node_l4
        )
        node_l6 = await seed_hierarchy_node(
            db_session, name="Grandchild", node_type="promoter", level=6, parent_id=node_l5
        )
        user_l4 = await seed_user(db_session, openid="wx_drill_l4", user_type="promoter", name="队长")
        user_l5 = await seed_user(db_session, openid="wx_drill_l5", user_type="promoter", name="队员")
        user_l6 = await seed_user(db_session, openid="wx_drill_l6", user_type="promoter", name="孙子")
        promoter_l4 = await seed_promoter(db_session, user_id=user_l4, node_id=node_l4)
        promoter_l5 = await seed_promoter(db_session, user_id=user_l5, node_id=node_l5)
        promoter_l6 = await seed_promoter(db_session, user_id=user_l6, node_id=node_l6)

        customer = Customer(
            promoter_id=promoter_l6,
            rutai_user_id="hrb_drill",
            binding_status=BindingStatus.BOUND,
        )
        db_session.add(customer)
        await db_session.flush()

        await seed_contribution_record(
            db_session, promoter_id=promoter_l6, customer_id=customer.id,
            points="100.00", status="settled", source_id="txn_drill",
            occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        resp = await client.get(
            f"/api/v1/team/contributions/{promoter_l5}?month=2026-07",
            headers=_auth_headers(user_l4),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert_response_envelope(body)
        data = body["data"]
        assert "teamMonthlyPoints" in data
        assert "members" in data

    async def test_drill_down_unauthorized_branch_returns_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Drill-down returns 403 when target is not in requester's branch."""
        # Create two independent branches
        node_a = await seed_hierarchy_node(
            db_session, name="BranchA", node_type="promoter", level=4, parent_id=None
        )
        node_b = await seed_hierarchy_node(
            db_session, name="BranchB", node_type="promoter", level=4, parent_id=None
        )
        node_a_child = await seed_hierarchy_node(
            db_session, name="ChildA", node_type="promoter", level=5, parent_id=node_a
        )
        node_b_child = await seed_hierarchy_node(
            db_session, name="ChildB", node_type="promoter", level=5, parent_id=node_b
        )

        user_a = await seed_user(db_session, openid="wx_branch_a", user_type="promoter", name="分支A")
        user_b = await seed_user(db_session, openid="wx_branch_b", user_type="promoter", name="分支B")
        user_a_child = await seed_user(db_session, openid="wx_branch_ac", user_type="promoter", name="子A")
        user_b_child = await seed_user(db_session, openid="wx_branch_bc", user_type="promoter", name="子B")

        promoter_a = await seed_promoter(db_session, user_id=user_a, node_id=node_a)
        promoter_b = await seed_promoter(db_session, user_id=user_b, node_id=node_b)
        promoter_a_child = await seed_promoter(db_session, user_id=user_a_child, node_id=node_a_child)
        promoter_b_child = await seed_promoter(db_session, user_id=user_b_child, node_id=node_b_child)

        # User A (branch A leader) tries to drill down into branch B's child
        resp = await client.get(
            f"/api/v1/team/contributions/{promoter_b_child}?month=2026-07",
            headers=_auth_headers(user_a),
        )

        assert resp.status_code == 403

    async def test_drill_down_requires_auth(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Calling without auth returns 401."""
        resp = await client.get("/api/v1/team/contributions/1?month=2026-07")
        assert resp.status_code == 401
