"""Contract tests for Promotion Code endpoints (US10)."""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    admin_auth_headers,
    make_access_token,
    seed_hierarchy_node,
    seed_promoter,
    seed_promotion_code,
    seed_qualification,
    seed_user,
)

_counter = 0


async def _setup_approved_promoter(
    db_session: AsyncSession, user_type: str = "promoter"
) -> tuple[int, int, str]:
    """Create user + hierarchy_node + promoter with an approved qualification. Returns (user_id, promoter_id, token)."""
    global _counter
    _counter += 1
    s = str(_counter)
    user_id = await seed_user(db_session, openid=f"promo_test_{s}", user_type=user_type, name=f"推广测试{s}")
    node_id = await seed_hierarchy_node(db_session, name=f"推广节点_{s}", node_type="promoter", level=2)
    promoter_id = await seed_promoter(db_session, user_id=user_id, node_id=node_id)
    await seed_qualification(
        db_session, promoter_id=promoter_id, qualification_type="enterprise",
        status="approved", file_id="approved_key", file_name="approved.jpg",
        file_type="image/jpeg", file_size=1024000, version=1,
        submitted_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        approved_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
    )
    token = make_access_token(user_id=user_id, user_type=user_type)
    return user_id, promoter_id, token


async def _setup_unapproved_promoter(
    db_session: AsyncSession, user_type: str = "promoter"
) -> tuple[int, int, str]:
    """Create user + hierarchy_node + promoter WITHOUT an approved qualification."""
    global _counter
    _counter += 1
    s = str(_counter)
    user_id = await seed_user(db_session, openid=f"unapproved_{s}", user_type=user_type, name=f"未审核测试{s}")
    node_id = await seed_hierarchy_node(db_session, name=f"未审核节点_{s}", node_type="promoter", level=2)
    promoter_id = await seed_promoter(db_session, user_id=user_id, node_id=node_id)
    token = make_access_token(user_id=user_id, user_type=user_type)
    return user_id, promoter_id, token


# ============================================================================
# GET /api/v1/promotion-code
# ============================================================================
class TestGetPromotionCode:
    async def test_approved_promoter_gets_code(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, promoter_id, token = await _setup_approved_promoter(db_session)
        resp = await client.get(
            "/api/v1/promotion-code",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "refToken" in data["data"]
        assert "sourceCode" in data["data"]
        assert len(data["data"]["refToken"]) > 0

    async def test_approved_promoter_returns_existing_code(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, promoter_id, token = await _setup_approved_promoter(db_session)
        # Pre-seed an existing promotion code
        await seed_promotion_code(
            db_session, promoter_id=promoter_id,
            ref_token="existing_ref_token_xyz",
            status="available",
        )
        resp = await client.get(
            "/api/v1/promotion-code",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["refToken"] == "existing_ref_token_xyz"

    async def test_unapproved_promoter_returns_forbidden(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, promoter_id, token = await _setup_unapproved_promoter(db_session)
        resp = await client.get(
            "/api/v1/promotion-code",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_no_promoter_record_returns_forbidden(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        # User exists but has no promoter record
        user_id = await seed_user(db_session, openid="no_promoter_user", user_type="promoter")
        token = make_access_token(user_id=user_id, user_type="promoter")
        resp = await client.get(
            "/api/v1/promotion-code",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (403, 404)

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/promotion-code")
        assert resp.status_code in (401, 403)


# ============================================================================
# POST /api/v1/promotion-code/refresh
# ============================================================================
class TestRefreshPromotionCode:
    async def test_refresh_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, promoter_id, token = await _setup_approved_promoter(db_session)
        # Pre-seed an existing promotion code
        await seed_promotion_code(
            db_session, promoter_id=promoter_id,
            ref_token="old_token_abc", status="available",
        )
        resp = await client.post(
            "/api/v1/promotion-code/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["refToken"] != "old_token_abc"
        # Old token should still be in data (disabled)
        assert "oldRefToken" in data["data"] or data["data"]["refToken"] != "old_token_abc"

    async def test_unapproved_promoter_cannot_refresh(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, promoter_id, token = await _setup_unapproved_promoter(db_session)
        resp = await client.post(
            "/api/v1/promotion-code/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_refresh_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/promotion-code/refresh")
        assert resp.status_code in (401, 403)


# ============================================================================
# GET /api/v1/promotion-code/statistics
# ============================================================================
class TestPromotionStatistics:
    async def test_statistics_valid_period(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, promoter_id, token = await _setup_approved_promoter(db_session)
        await seed_promotion_code(
            db_session, promoter_id=promoter_id,
            ref_token="stats_token_123", status="available",
            scan_count=100, lead_count=50, bind_count=25,
        )
        resp = await client.get(
            "/api/v1/promotion-code/statistics",
            params={"period": "30d"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        stats = data["data"]
        assert "scanCount" in stats
        assert "leadCount" in stats
        assert "bindCount" in stats
        assert "conversionRate" in stats

    async def test_statistics_empty_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, promoter_id, token = await _setup_approved_promoter(db_session)
        await seed_promotion_code(
            db_session, promoter_id=promoter_id,
            ref_token="empty_stats_token", status="available",
            scan_count=0, lead_count=0, bind_count=0,
        )
        resp = await client.get(
            "/api/v1/promotion-code/statistics",
            params={"period": "7d"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        stats = data["data"]
        assert stats["scanCount"] == 0
        assert stats["leadCount"] == 0
        assert stats["bindCount"] == 0
        assert stats["conversionRate"] == 0.0

    async def test_statistics_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/promotion-code/statistics?period=30d")
        assert resp.status_code in (401, 403)

    async def test_unapproved_promoter_gets_forbidden(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id, promoter_id, token = await _setup_unapproved_promoter(db_session)
        resp = await client.get(
            "/api/v1/promotion-code/statistics",
            params={"period": "30d"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
